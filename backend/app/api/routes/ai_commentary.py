"""
StockMind AI — AI Commentary Routes
Claude API settings (key never returned) and on-demand commentary generation.
Every /commentary call either returns a cached result or spends real API
credits — there is no automatic/background generation.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_optional_user
from app.database import get_db
from app.models.user import User
from app.services.ai.ai_config import get_settings_public, set_settings
from app.services.ai.commentary_service import (
    CommentaryError, MAX_BATCH_SYMBOLS, MODEL_PRICING, generate_batch_commentary, generate_commentary,
)

router = APIRouter(tags=["AI Commentary"])


class AISettingsUpdate(BaseModel):
    api_key: Optional[str] = Field(None, max_length=500)
    model: str = Field(min_length=1, max_length=100)


class BatchCommentaryRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=MAX_BATCH_SYMBOLS)


@router.get("/api/settings/ai")
async def get_ai_settings(db: AsyncSession = Depends(get_db)):
    """Current Claude API configuration status (key never returned) plus model pricing for the UI."""
    status = await get_settings_public(db)
    return {**status, "pricing": MODEL_PRICING}


@router.put("/api/settings/ai")
async def update_ai_settings(
    body: AISettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the Claude API key/model. A blank key keeps whatever is already stored."""
    if body.model not in MODEL_PRICING:
        raise HTTPException(status_code=400, detail=f"Unknown model '{body.model}'.")
    return await set_settings(db, body.api_key, body.model, user.email)


@router.post("/api/ai/commentary/batch")
async def get_batch_commentary(
    body: BatchCommentaryRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """One combined, cheaper Claude call covering several stocks with a condensed verdict each."""
    try:
        return await generate_batch_commentary(db, user, body.symbols)
    except CommentaryError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/api/ai/commentary/{symbol}")
async def get_commentary(
    symbol: str,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate (or return already-cached) AI commentary for a stock."""
    try:
        return await generate_commentary(db, user, symbol)
    except CommentaryError as e:
        raise HTTPException(status_code=422, detail=str(e))
