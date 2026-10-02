"""
StockMind AI — Model Training Pipeline
Trains one LightGBM direction-classifier + one return-regressor per horizon
from stored historical candles, using the exact same FeatureEngine that
live prediction/signal code already uses (so training and serving can never
drift apart). Manually triggered (POST /api/ml/train) — never scheduled.

Every run produces a `challenger` ModelVersion; nothing is activated until a
human calls promote_model(). This is deliberate: a model that merely beats
"no model" isn't automatically good enough to trade on.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import lightgbm as lgb
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.models.market import Candle
from app.models.prediction import ModelVersion, TrainingRun
from app.services.analytics.features import FeatureEngine
from app.services.ml.champion_registry import write_manifest
from app.services.ml.data_collection import collect_historical_data
from app.services.upstox.provider import UpstoxDataProvider

logger = get_logger(__name__)
settings = get_settings()

HORIZON_DAYS = {"1D": 1, "3D": 3, "5D": 5, "10D": 10, "20D": 20}
# Fixed +/-1% bucket for up/flat/down across all horizons — a deliberate v1
# simplification (a real model would scale this with horizon/volatility).
FLAT_BAND = 0.01
FEATURE_NAMES = FeatureEngine.get_feature_names()


class TrainingError(Exception):
    """Raised when a training run fails outright (not enough data, etc)."""


async def _load_symbol_frame(db: AsyncSession, instrument_key: str) -> pd.DataFrame | None:
    result = await db.execute(
        select(Candle).where(Candle.instrument_key == instrument_key, Candle.interval == "day").order_by(Candle.timestamp)
    )
    rows = result.scalars().all()
    if len(rows) < 250:  # need real history for 200-day features + a usable train/test split
        return None

    df = pd.DataFrame([{
        "timestamp": r.timestamp, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume,
    } for r in rows])
    df = FeatureEngine.compute_all_features(df.sort_values("timestamp").reset_index(drop=True))

    for horizon, days in HORIZON_DAYS.items():
        future_return = df["close"].shift(-days) / df["close"] - 1
        df[f"ret_{horizon}"] = future_return
        df[f"label_{horizon}"] = np.where(future_return > FLAT_BAND, 2, np.where(future_return < -FLAT_BAND, 0, 1))

    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    return df


def _directional_metrics(proba: np.ndarray, y_true: np.ndarray) -> dict[str, float]:
    pred_class = proba.argmax(axis=1)
    accuracy = float((pred_class == y_true).mean())
    eps = 1e-9
    true_proba = proba[np.arange(len(y_true)), y_true]
    log_loss = float(-np.mean(np.log(np.clip(true_proba, eps, 1))))
    up_proba = proba[:, 2]
    up_actual = (y_true == 2).astype(float)
    brier = float(np.mean((up_proba - up_actual) ** 2))
    return {"accuracy": accuracy, "log_loss": log_loss, "brier_up": brier}


def _train_one_horizon(
    X_train: pd.DataFrame,
    y_train_cls: pd.Series,
    y_train_reg: pd.Series,
    X_test: pd.DataFrame,
    y_test_cls: pd.Series,
    run_dir: str,
    horizon: str,
) -> dict[str, float]:
    """Synchronous (CPU-bound) — call via asyncio.to_thread, never directly from a coroutine."""
    cls_booster = lgb.train(
        {"objective": "multiclass", "num_class": 3, "metric": "multi_logloss", "verbosity": -1, "seed": 42},
        lgb.Dataset(X_train, label=y_train_cls),
        num_boost_round=200,
    )
    reg_booster = lgb.train(
        {"objective": "regression", "metric": "l2", "verbosity": -1, "seed": 42},
        lgb.Dataset(X_train, label=y_train_reg),
        num_boost_round=200,
    )

    test_proba = cls_booster.predict(X_test)
    metrics = _directional_metrics(test_proba, y_test_cls.to_numpy())

    cls_booster.save_model(os.path.join(run_dir, f"{horizon}_cls.txt"))
    reg_booster.save_model(os.path.join(run_dir, f"{horizon}_reg.txt"))
    return metrics


async def run_training(db: AsyncSession, run_id: UUID, provider: UpstoxDataProvider, symbols: list[str], lookback_days: int) -> TrainingRun:
    """
    Runs the pipeline against an *already-created* TrainingRun row (the
    caller creates it synchronously so it can hand the id back immediately,
    then calls this — usually from a different session/background task).
    """
    run = await db.get(TrainingRun, run_id)
    if run is None:
        raise TrainingError(f"TrainingRun {run_id} not found.")

    try:
        logger.info("training_run_started", run_id=str(run.id), symbols=len(symbols))
        await collect_historical_data(db, provider, symbols, lookback_days)

        instruments = {}
        for symbol in symbols:
            inst = await provider.resolve_instrument(symbol)
            instruments[symbol] = inst["instrument_key"]

        frames = []
        for symbol, instrument_key in instruments.items():
            frame = await _load_symbol_frame(db, instrument_key)
            if frame is not None:
                frame["symbol"] = symbol
                frames.append(frame)

        if len(frames) < 5:
            raise TrainingError(f"Only {len(frames)} symbols had enough history to train on (need at least 5).")

        combined = pd.concat(frames, ignore_index=True)
        unique_dates = sorted(combined["date"].unique())
        cutoff = unique_dates[int(len(unique_dates) * 0.8)]
        train_mask = combined["date"] <= cutoff
        test_mask = combined["date"] > cutoff

        run_dir = os.path.join(settings.model_registry_path, str(run.id))
        os.makedirs(run_dir, exist_ok=True)

        metrics_by_horizon: dict[str, Any] = {}
        for horizon in HORIZON_DAYS:
            label_col, ret_col = f"label_{horizon}", f"ret_{horizon}"
            train_df = combined[train_mask].dropna(subset=[label_col, ret_col] + FEATURE_NAMES)
            test_df = combined[test_mask].dropna(subset=[label_col, ret_col] + FEATURE_NAMES)
            if len(train_df) < 200 or len(test_df) < 20:
                logger.warning("training_horizon_skipped", horizon=horizon, train_rows=len(train_df), test_rows=len(test_df))
                continue

            X_train, y_train_cls, y_train_reg = train_df[FEATURE_NAMES], train_df[label_col].astype(int), train_df[ret_col]
            X_test, y_test_cls = test_df[FEATURE_NAMES], test_df[label_col].astype(int)

            # CPU-bound (can take real time at full universe scale) — run off the
            # event loop so the rest of the app (including other API requests and
            # the trailing-stop monitor) keeps responding while this runs.
            horizon_metrics = await asyncio.to_thread(
                _train_one_horizon, X_train, y_train_cls, y_train_reg, X_test, y_test_cls, run_dir, horizon
            )
            metrics_by_horizon[horizon] = {**horizon_metrics, "train_rows": len(train_df), "test_rows": len(test_df)}

        if not metrics_by_horizon:
            raise TrainingError("No horizon had enough train/test data to fit a model.")

        avg_accuracy = float(np.mean([m["accuracy"] for m in metrics_by_horizon.values()]))
        avg_log_loss = float(np.mean([m["log_loss"] for m in metrics_by_horizon.values()]))
        avg_brier = float(np.mean([m["brier_up"] for m in metrics_by_horizon.values()]))

        model_version = ModelVersion(
            model_name="ensemble",
            version=f"run-{run.id}",
            model_type="lightgbm",
            training_start=run.started_at,
            training_end=datetime.now(timezone.utc),
            training_data_start=datetime.combine(unique_dates[0], datetime.min.time()),
            training_data_end=datetime.combine(unique_dates[-1], datetime.min.time()),
            feature_version="v1",
            features_used=FEATURE_NAMES,
            target="direction (±1% band) + forward return, per horizon",
            hyperparameters={"metrics_by_horizon": metrics_by_horizon, "symbols": list(instruments)},
            accuracy=avg_accuracy,
            log_loss_score=avg_log_loss,
            brier_score=avg_brier,
            status="challenger",
            artifact_path=run_dir,
        )
        db.add(model_version)
        await db.flush()

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.model_version_id = model_version.id
        run.training_data_rows = int(train_mask.sum())
        run.test_data_rows = int(test_mask.sum())
        run.metrics = {"by_horizon": metrics_by_horizon, "avg_accuracy": avg_accuracy}
        await db.commit()

        logger.info("training_run_completed", run_id=str(run.id), model_version_id=str(model_version.id), avg_accuracy=avg_accuracy)
        return run

    except Exception as e:
        logger.error("training_run_failed", run_id=str(run.id), error=str(e))
        run.status = "failed"
        run.error_message = str(e)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise


async def promote_model(db: AsyncSession, model_version_id: UUID) -> ModelVersion:
    """Promote a challenger to champion — the only thing that makes a trained model live."""
    model_version = await db.get(ModelVersion, model_version_id)
    if not model_version:
        raise TrainingError("Model version not found.")

    result = await db.execute(
        select(ModelVersion).where(ModelVersion.model_name == model_version.model_name, ModelVersion.is_champion.is_(True))
    )
    for old in result.scalars().all():
        old.is_champion = False
        old.status = "retired"
        old.retired_at = datetime.now(timezone.utc)

    model_version.is_champion = True
    model_version.status = "champion"
    model_version.promoted_at = datetime.now(timezone.utc)
    await db.commit()

    manifest = {}
    for horizon in HORIZON_DAYS:
        cls_path = os.path.join(model_version.artifact_path, f"{horizon}_cls.txt")
        reg_path = os.path.join(model_version.artifact_path, f"{horizon}_reg.txt")
        if os.path.exists(cls_path) and os.path.exists(reg_path):
            manifest[horizon] = {"classifier": cls_path, "regressor": reg_path, "model_version_id": str(model_version.id)}
    write_manifest(settings.model_registry_path, manifest)

    logger.info("model_promoted", model_version_id=str(model_version.id), horizons=list(manifest))
    return model_version
