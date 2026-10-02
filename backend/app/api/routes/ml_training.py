"""
StockMind AI — Model Training Routes
Manually-triggered training (never scheduled) plus challenger/champion
management. Open to any authenticated user — this app has no admin-promotion
UI, so gating this behind admin would lock the user themselves out (the same
reasoning applied to broker credentials).
"""

import asyncio
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.routes.market import get_market_provider
from app.config import get_settings
from app.core.logging import get_logger
from app.database import async_session_factory, get_db
from app.models.prediction import ModelVersion, TrainingRun
from app.models.user import User
from app.services.analytics.screener import SECTOR_UNIVERSE
from app.services.ml.training_pipeline import TrainingError, promote_model, run_training

router = APIRouter(prefix="/api/ml", tags=["Model Training"])
logger = get_logger(__name__)
settings = get_settings()


class TrainRequest(BaseModel):
    symbols: Optional[list[str]] = None
    lookback_days: Optional[int] = None


def _all_symbols() -> list[str]:
    return [s for stocks in SECTOR_UNIVERSE.values() for s in stocks]


async def _run_training_background(run_id: UUID, symbols: list[str], lookback_days: int, access_token: Optional[str]) -> None:
    from app.services.upstox.provider import UpstoxDataProvider

    token = access_token or settings.upstox_analytics_token
    provider = UpstoxDataProvider(access_token=token)
    async with async_session_factory() as db:
        try:
            await run_training(db, run_id, provider, symbols, lookback_days)
        except Exception as e:
            logger.error("background_training_failed", run_id=str(run_id), error=str(e))


@router.post("/train")
async def start_training(
    body: TrainRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kick off a training run in the background; poll GET /api/ml/train/{id} for status."""
    symbols = body.symbols or _all_symbols()
    lookback_days = body.lookback_days or settings.ml_training_lookback_days

    provider = await get_market_provider(user, db)
    access_token = provider._access_token  # reuse the same token the background task will use

    # Pre-create the run row synchronously so the caller gets an id immediately.
    run = TrainingRun(run_type="manual", status="running", config={"symbols": symbols, "lookback_days": lookback_days})
    db.add(run)
    await db.commit()
    await db.refresh(run)

    asyncio.create_task(_run_training_background(run.id, symbols, lookback_days, access_token))
    return {"run_id": str(run.id), "status": "running", "symbols": len(symbols), "lookback_days": lookback_days}


@router.get("/train/{run_id}")
async def get_training_status(run_id: UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(TrainingRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found.")
    return {
        "id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "training_data_rows": run.training_data_rows,
        "test_data_rows": run.test_data_rows,
        "metrics": run.metrics,
        "error_message": run.error_message,
        "model_version_id": str(run.model_version_id) if run.model_version_id else None,
    }


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(50))
    return [
        {
            "id": str(m.id),
            "version": m.version,
            "status": m.status,
            "is_champion": m.is_champion,
            "accuracy": m.accuracy,
            "log_loss_score": m.log_loss_score,
            "brier_score": m.brier_score,
            "training_data_start": m.training_data_start.isoformat() if m.training_data_start else None,
            "training_data_end": m.training_data_end.isoformat() if m.training_data_end else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "promoted_at": m.promoted_at.isoformat() if m.promoted_at else None,
            "metrics_by_horizon": (m.hyperparameters or {}).get("metrics_by_horizon"),
        }
        for m in result.scalars().all()
    ]


@router.post("/models/{model_version_id}/promote")
async def promote(model_version_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Make a challenger the live champion — the only thing that activates a trained model."""
    try:
        model = await promote_model(db, model_version_id)
    except TrainingError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": str(model.id), "status": model.status, "is_champion": model.is_champion}
