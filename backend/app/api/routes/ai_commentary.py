"""
StockMind AI — AI Commentary Routes
Multi-provider (Anthropic Claude + Google Gemini) API settings — each
provider's key is stored separately and never returned — plus on-demand
commentary generation. Every /commentary call either returns a cached result
or spends real API credits; there is no automatic/background generation.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_optional_user
from app.database import get_db
from app.models.user import User
from app.services.ai.ai_config import AIConfigError, PROVIDERS, get_settings_public, set_active_model, set_provider_key
from app.services.ai.commentary_service import (
    CommentaryError, MAX_BATCH_SYMBOLS, MODEL_PRICING, generate_batch_commentary, generate_commentary,
    list_recent_commentary,
)

router = APIRouter(tags=["AI Commentary"])


class AIModelUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=100)


class AIProviderKeyUpdate(BaseModel):
    api_key: str = Field(max_length=500)  # blank clears the stored key


class BatchCommentaryRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=MAX_BATCH_SYMBOLS)


@router.get("/api/settings/ai")
async def get_ai_settings(db: AsyncSession = Depends(get_db)):
    """Current AI provider configuration status (keys never returned) plus model pricing for the UI."""
    status = await get_settings_public(db)
    return {**status, "pricing": MODEL_PRICING}


@router.put("/api/settings/ai")
async def update_ai_model(
    body: AIModelUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Switch the active model (and therefore which stored provider key gets used)."""
    if body.model not in MODEL_PRICING:
        raise HTTPException(status_code=400, detail=f"Unknown model '{body.model}'.")
    try:
        return await set_active_model(db, body.model, user.email)
    except AIConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/settings/ai/{provider}")
async def update_ai_provider_key(
    provider: str,
    body: AIProviderKeyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save (or clear, with a blank value) one provider's API key."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'. Must be one of {PROVIDERS}.")
    return await set_provider_key(db, provider, body.api_key, user.email)


@router.get("/api/ai/commentary/recent")
async def get_recent_commentary(limit: int = 5, db: AsyncSession = Depends(get_db)):
    """Most recently generated Indian AI commentary, one per distinct symbol —
    for the Dashboard's "Recent Indian Analysis" panel."""
    return {"items": await list_recent_commentary(db, min(max(limit, 1), 20))}


@router.post("/api/ai/commentary/batch")
async def get_batch_commentary(
    body: BatchCommentaryRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """One combined, cheaper call (whichever provider is active) covering several stocks with a condensed verdict each."""
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
