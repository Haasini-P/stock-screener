"""
StockMind AI — ML Prediction Engine
Ensemble-based prediction system with calibration and explainability.
Uses champion/challenger model architecture.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.services.analytics.features import FeatureEngine
from app.services.ml.champion_registry import manifest_path, read_manifest

logger = get_logger(__name__)

# Shared across all EnsemblePredictionEngine instances (it's constructed fresh
# per request) — reloaded only when champion.json's mtime changes, same
# lightweight-cache pattern as _instrument_cache in upstox/provider.py.
_champion_cache: dict[str, Any] = {"mtime": None, "manifest": {}, "boosters": {}}


# ============================================================
# PREDICTION OUTPUT
# ============================================================

class PredictionResult:
    """
    Structured prediction output.
    Never represents a prediction as certainty.
    """

    def __init__(
        self,
        instrument_key: str,
        symbol: str = "",
        horizon: str = "1D",
    ):
        self.id = str(uuid.uuid4())
        self.instrument_key = instrument_key
        self.symbol = symbol
        self.horizon = horizon
        self.timestamp = datetime.now(timezone.utc).isoformat()

        # Direction probabilities (must sum to ~1.0)
        self.prob_up: float = 0.0
        self.prob_flat: float = 0.0
        self.prob_down: float = 0.0

        # Expected return
        self.expected_return: float = 0.0
        self.prediction_interval_lower: float = 0.0
        self.prediction_interval_upper: float = 0.0

        # Scenarios
        self.bull_scenario: str = ""
        self.base_scenario: str = ""
        self.bear_scenario: str = ""

        # Meta
        self.confidence: str = "low"
        self.risk: str = "medium"
        self.signal: str = "no_signal"
        self.market_regime: str = ""
        self.model_version: str = ""
        self.data_timestamp: str = ""

        # Evidence
        self.key_positive_factors: list[dict] = []
        self.key_negative_factors: list[dict] = []

        # Feature snapshot for audit
        self.feature_snapshot: Optional[dict] = None

        # SHAP explanation
        self.shap_values: Optional[dict] = None
        self.explanation_text: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "instrument": self.instrument_key,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "horizon": self.horizon,
            "direction_probabilities": {
                "up": round(self.prob_up, 4),
                "flat": round(self.prob_flat, 4),
                "down": round(self.prob_down, 4),
            },
            "expected_return": round(self.expected_return, 6),
            "prediction_interval": {
                "lower": round(self.prediction_interval_lower, 6),
                "upper": round(self.prediction_interval_upper, 6),
            },
            "scenarios": {
                "bull": self.bull_scenario,
                "base": self.base_scenario,
                "bear": self.bear_scenario,
            },
            "confidence": self.confidence,
            "risk": self.risk,
            "market_regime": self.market_regime,
            "signal": self.signal,
            "key_positive_factors": self.key_positive_factors,
            "key_negative_factors": self.key_negative_factors,
            "model_version": self.model_version,
            "data_timestamp": self.data_timestamp,
            "explanation": self.explanation_text,
            "feature_snapshot": self.feature_snapshot,
            "_disclaimer": (
                "This is a model estimate with inherent uncertainty. "
                "Probabilities reflect statistical patterns, not certainties. "
                "Past patterns may not repeat. Use for analysis only."
            ),
        }


# ============================================================
# ENSEMBLE PREDICTION ENGINE
# ============================================================

class EnsemblePredictionEngine:
    """
    Multi-layer ensemble prediction engine.

    Layer 1: Statistical models (Logistic Regression, Ridge)
    Layer 2: Tree models (LightGBM, XGBoost, CatBoost)
    Layer 3: Time-series models (optional, only if proven)
    Layer 4: Regime detection (HMM, clustering)
    Layer 5: Meta-ensemble with calibration

    The engine uses a statistical baseline when ML models are not yet trained.
    """

    HORIZONS = ["1D", "3D", "5D", "10D", "20D"]

    def __init__(self, model_registry_path: str = "./model_registry"):
        self.model_registry_path = model_registry_path

    @property
    def _is_trained(self) -> bool:
        """True if at least one horizon has a promoted champion model."""
        return bool(self._load_champion_manifest())

    def _load_champion_manifest(self) -> dict[str, Any]:
        """The champion.json manifest, reloaded only when the file changes on disk."""
        path = manifest_path(self.model_registry_path)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            _champion_cache.update(mtime=None, manifest={}, boosters={})
            return {}
        if _champion_cache["mtime"] != mtime:
            _champion_cache["manifest"] = read_manifest(self.model_registry_path)
            _champion_cache["boosters"] = {}
            _champion_cache["mtime"] = mtime
        return _champion_cache["manifest"]

    def _load_champion_boosters(self, horizon: str):
        """(classifier, regressor) LightGBM boosters for a horizon, or None if no champion covers it."""
        manifest = self._load_champion_manifest()
        entry = manifest.get(horizon)
        if not entry:
            return None
        if horizon not in _champion_cache["boosters"]:
            import lightgbm as lgb
            _champion_cache["boosters"][horizon] = (
                lgb.Booster(model_file=entry["classifier"]),
                lgb.Booster(model_file=entry["regressor"]),
                entry["model_version_id"],
            )
        return _champion_cache["boosters"][horizon]

    def predict(
        self,
        features: dict[str, Any],
        horizon: str = "1D",
        market_regime: str = "",
    ) -> PredictionResult:
        """
        Generate a prediction for a single instrument. Uses the promoted
        champion model for this horizon if one exists; otherwise (or if
        inference fails) falls back to the statistical baseline.
        """
        result = PredictionResult(
            instrument_key=features.get("instrument_key", ""),
            symbol=features.get("symbol", ""),
            horizon=horizon,
        )
        result.data_timestamp = features.get("timestamp", "")
        result.market_regime = market_regime
        result.feature_snapshot = {
            k: float(v) if isinstance(v, (int, float, np.floating)) else str(v)
            for k, v in features.items()
            if k not in ("timestamp", "instrument_key", "symbol", "name")
            and v is not None and not (isinstance(v, float) and np.isnan(v))
        }

        result = self._predict_ensemble(features, result)
        result = self._generate_scenarios(features, result)
        result = self._generate_explanation(features, result)

        return result

    def _predict_statistical_baseline(
        self,
        features: dict[str, Any],
        result: PredictionResult,
    ) -> PredictionResult:
        """
        Statistical baseline prediction using technical indicators.
        Used when ML models are not yet trained.

        This combines multiple signals into a probability estimate
        using a principled scoring approach.
        """
        scores = []

        # --- Trend signals ---
        close = features.get("close", 0)
        sma_20 = features.get("sma_20")
        sma_50 = features.get("sma_50")
        sma_200 = features.get("sma_200")

        if sma_20 and close:
            scores.append(0.6 if close > sma_20 else 0.4)
        if sma_50 and close:
            scores.append(0.6 if close > sma_50 else 0.4)
        if sma_200 and close:
            scores.append(0.6 if close > sma_200 else 0.4)

        # --- Momentum signals ---
        rsi = features.get("rsi_14")
        if rsi:
            if rsi > 70:
                scores.append(0.35)  # Overbought → slight bearish lean
            elif rsi > 50:
                scores.append(0.55 + (rsi - 50) * 0.003)
            elif rsi < 30:
                scores.append(0.55)  # Oversold → slight bullish lean (mean reversion)
            else:
                scores.append(0.45)

        macd_hist = features.get("macd_histogram")
        if macd_hist:
            scores.append(0.58 if macd_hist > 0 else 0.42)

        # --- Volume signals ---
        vol_ratio = features.get("volume_ratio")
        if vol_ratio:
            if vol_ratio > 2.0:
                # High volume amplifies existing direction
                return_1d = features.get("return_1d", 0)
                if return_1d and return_1d > 0:
                    scores.append(0.62)
                else:
                    scores.append(0.38)

        # --- Volatility ---
        vol_pct = features.get("volatility_percentile")
        if vol_pct is not None:
            # Higher vol = more uncertainty → push toward 0.5
            uncertainty_factor = vol_pct * 0.1
            scores = [s * (1 - uncertainty_factor) + 0.5 * uncertainty_factor for s in scores]

        # --- Compute aggregate probability ---
        if scores:
            raw_prob = np.mean(scores)
            # Shrink toward 0.5 (conservative)
            shrinkage = 0.3
            prob_up = raw_prob * (1 - shrinkage) + 0.5 * shrinkage
        else:
            prob_up = 0.5  # No data → maximum uncertainty

        # Adjust for horizon
        horizon_adjustment = {
            "1D": 1.0,
            "3D": 0.95,
            "5D": 0.90,
            "10D": 0.85,
            "20D": 0.80,
        }
        adj = horizon_adjustment.get(result.horizon, 1.0)
        prob_up = prob_up * adj + 0.5 * (1 - adj)

        result.prob_up = round(np.clip(prob_up, 0.15, 0.85), 4)
        result.prob_down = round(1 - result.prob_up - 0.05, 4)
        result.prob_flat = round(1 - result.prob_up - result.prob_down, 4)

        # Expected return estimation
        volatility = features.get("volatility_20d", 0.25)
        horizon_days = int(result.horizon.replace("D", "") or 1)
        daily_vol = volatility / np.sqrt(252) if volatility else 0.015

        result.expected_return = round(
            (result.prob_up - 0.5) * 2 * daily_vol * np.sqrt(horizon_days), 6
        )

        # Prediction interval (roughly 80% CI)
        interval_width = daily_vol * np.sqrt(horizon_days) * 1.28
        result.prediction_interval_lower = round(-interval_width, 6)
        result.prediction_interval_upper = round(interval_width, 6)

        # Confidence
        n_signals = len(scores)
        if n_signals >= 6 and abs(prob_up - 0.5) > 0.1:
            result.confidence = "moderate"
        elif n_signals >= 4:
            result.confidence = "low-moderate"
        else:
            result.confidence = "low"

        result.risk = self._assess_risk(features)

        # Signal classification
        if result.prob_up > 0.6:
            result.signal = "potential_upside"
        elif result.prob_up < 0.4:
            result.signal = "potential_downside"
        else:
            result.signal = "neutral"

        result.model_version = "v0.1.0-statistical-baseline"
        return result

    def _predict_ensemble(
        self,
        features: dict[str, Any],
        result: PredictionResult,
    ) -> PredictionResult:
        """
        Prediction from the promoted champion model for this horizon, if one
        exists and inference succeeds; otherwise the statistical baseline.
        """
        boosters = self._load_champion_boosters(result.horizon)
        if boosters is None:
            return self._predict_statistical_baseline(features, result)
        cls_booster, reg_booster, model_version_id = boosters

        x = np.array([[
            float(features[f]) if features.get(f) is not None and not (
                isinstance(features.get(f), float) and np.isnan(features[f])
            ) else 0.0
            for f in FeatureEngine.get_feature_names()
        ]])

        try:
            proba = cls_booster.predict(x)[0]  # [p_down, p_flat, p_up]
            expected_return = float(reg_booster.predict(x)[0])
        except Exception as e:
            logger.warning("ensemble_predict_failed", horizon=result.horizon, error=str(e))
            return self._predict_statistical_baseline(features, result)

        result.prob_down, result.prob_flat, result.prob_up = [round(float(p), 4) for p in proba]
        result.expected_return = round(expected_return, 6)

        volatility = features.get("volatility_20d") or 0.25
        horizon_days = int(result.horizon.replace("D", "") or 1)
        daily_vol = volatility / np.sqrt(252) if volatility else 0.015
        interval_width = daily_vol * np.sqrt(horizon_days) * 1.28
        result.prediction_interval_lower = round(expected_return - interval_width, 6)
        result.prediction_interval_upper = round(expected_return + interval_width, 6)

        max_proba = float(max(proba))
        result.confidence = "high" if max_proba > 0.65 else "moderate" if max_proba > 0.5 else "low"
        result.risk = self._assess_risk(features)

        if result.prob_up > 0.6:
            result.signal = "potential_upside"
        elif result.prob_down > 0.6:
            result.signal = "potential_downside"
        else:
            result.signal = "neutral"

        result.model_version = f"champion:{model_version_id}"
        return result

    def _assess_risk(self, features: dict) -> str:
        """Assess risk level from feature data."""
        vol_pct = features.get("volatility_percentile", 0.5)
        atr_pct = features.get("atr_14", 0) / features.get("close", 1) if features.get("close") else 0

        risk_score = vol_pct * 0.5 + min(atr_pct * 10, 1) * 0.5

        if risk_score > 0.7:
            return "high"
        elif risk_score > 0.5:
            return "medium-high"
        elif risk_score > 0.3:
            return "medium"
        return "low"

    def _generate_scenarios(
        self,
        features: dict[str, Any],
        result: PredictionResult,
    ) -> PredictionResult:
        """Generate bull/base/bear scenarios."""
        vol = features.get("volatility_20d", 0.25)
        horizon_days = int(result.horizon.replace("D", "") or 1)
        daily_vol = vol / np.sqrt(252) if vol else 0.015

        bull_move = daily_vol * np.sqrt(horizon_days) * 1.5
        bear_move = -daily_vol * np.sqrt(horizon_days) * 1.5

        close = features.get("close", 0)
        resistance = features.get("resistance_1")
        support = features.get("support_1")

        result.bull_scenario = (
            f"Strong momentum continuation with volume confirmation. "
            f"Potential move to ₹{close * (1 + bull_move):.2f} "
            f"({bull_move*100:.1f}%)"
            + (f" targeting resistance near ₹{resistance:.2f}" if resistance else "")
        )

        result.base_scenario = (
            f"Trend continuation within normal volatility range. "
            f"Expected to trade between ₹{close * (1 + result.prediction_interval_lower):.2f} "
            f"and ₹{close * (1 + result.prediction_interval_upper):.2f}"
        )

        result.bear_scenario = (
            f"Momentum reversal or market weakness. "
            f"Potential decline to ₹{close * (1 + bear_move):.2f} "
            f"({bear_move*100:.1f}%)"
            + (f" with support near ₹{support:.2f}" if support else "")
        )

        return result

    def _generate_explanation(
        self,
        features: dict[str, Any],
        result: PredictionResult,
    ) -> PredictionResult:
        """Generate human-readable explanation from actual feature values."""
        positive = []
        negative = []

        # Trend
        close = features.get("close", 0)
        sma_50 = features.get("sma_50")
        sma_200 = features.get("sma_200")

        if sma_50 and close > sma_50:
            positive.append({"factor": "Above 50-day MA", "type": "FACT", "impact": "medium"})
        elif sma_50:
            negative.append({"factor": "Below 50-day MA", "type": "FACT", "impact": "medium"})

        if sma_200 and close > sma_200:
            positive.append({"factor": "Above 200-day MA", "type": "FACT", "impact": "high"})
        elif sma_200:
            negative.append({"factor": "Below 200-day MA", "type": "FACT", "impact": "high"})

        # RSI
        rsi = features.get("rsi_14")
        if rsi:
            if 55 <= rsi <= 70:
                positive.append({"factor": f"RSI {rsi:.1f} — healthy momentum", "type": "FACT", "impact": "medium"})
            elif rsi > 75:
                negative.append({"factor": f"RSI {rsi:.1f} — overbought", "type": "FACT", "impact": "medium"})

        # Volume
        vol_ratio = features.get("volume_ratio")
        if vol_ratio and vol_ratio > 1.5:
            positive.append({"factor": f"Volume {vol_ratio:.1f}x average", "type": "FACT", "impact": "medium"})

        # MACD
        macd_hist = features.get("macd_histogram")
        if macd_hist:
            if macd_hist > 0:
                positive.append({"factor": "Bullish MACD", "type": "FACT", "impact": "medium"})
            else:
                negative.append({"factor": "Bearish MACD", "type": "FACT", "impact": "medium"})

        # Relative strength
        rs = features.get("relative_return_nifty")
        if rs and rs > 0.01:
            positive.append({"factor": f"Outperforming NIFTY by {rs*100:.1f}%", "type": "FACT", "impact": "medium"})
        elif rs and rs < -0.01:
            negative.append({"factor": f"Underperforming NIFTY by {abs(rs)*100:.1f}%", "type": "FACT", "impact": "medium"})

        # Volatility
        vol_pct = features.get("volatility_percentile")
        if vol_pct and vol_pct > 0.7:
            negative.append({"factor": "High volatility environment", "type": "FACT", "impact": "medium"})

        result.key_positive_factors = positive
        result.key_negative_factors = negative

        # Text explanation
        pos_text = ", ".join(f["factor"] for f in positive[:4])
        neg_text = ", ".join(f["factor"] for f in negative[:4])
        parts = []
        if pos_text:
            parts.append(f"Positive factors: {pos_text}")
        if neg_text:
            parts.append(f"Negative factors: {neg_text}")
        parts.append(
            f"The model estimates a {result.prob_up*100:.0f}% probability of positive return "
            f"over {result.horizon} with {result.confidence} confidence."
        )
        result.explanation_text = ". ".join(parts)

        return result
