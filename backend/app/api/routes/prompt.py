"""StockMind AI — AI System Prompt Routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_optional_user
from app.api.routes.market import get_market_provider
from app.database import get_db
from app.models.user import User
from app.services.analytics.market_state import get_market_state
from app.services.analytics.prompt_service import build_suggested_prompt, get_current_prompt

router = APIRouter(prefix="/api/prompt", tags=["AI Prompt"])

# The merged master prompt is larger than the original 8,000-character limit.
MAX_PROMPT_LENGTH = 20000


class PromptUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)


@router.get("")
async def get_prompt(db: AsyncSession = Depends(get_db)):
    row = await get_current_prompt(db)
    return {
        "content": row.content,
        "source": row.source,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("")
async def update_prompt(
    body: PromptUpdate,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    row = await get_current_prompt(db)
    row.content = body.content
    row.source = "manual"
    row.updated_by = user.email if user else "guest"
    await db.flush()
    await db.refresh(row)
    return {
        "content": row.content,
        "source": row.source,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/suggest")
async def suggest_prompt(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    provider = await get_market_provider(user, db)
    try:
        state = await get_market_state(provider)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read live market data: {e}")
    return build_suggested_prompt(state["regime"])
