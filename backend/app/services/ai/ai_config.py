"""
StockMind AI — Claude API Settings
Get/set the Claude API key and chosen model, encrypted at rest. Mirrors
app/services/broker_config.py's pattern exactly (DB row wins, env var is not
used here since there's no equivalent env default — this is purely UI-configured).
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_token, encrypt_token
from app.models.ai_commentary import AISettings

DEFAULT_MODEL = "claude-opus-5-5"


async def _get_row(db: AsyncSession) -> Optional[AISettings]:
    result = await db.execute(select(AISettings).limit(1))
    return result.scalar_one_or_none()


async def get_settings(db: AsyncSession) -> dict:
    """Resolved {api_key, model, configured}. `api_key` is only for internal use — never return it to the browser."""
    row = await _get_row(db)
    api_key = decrypt_token(row.api_key_encrypted) if row and row.api_key_encrypted else ""
    model = (row.model if row else None) or DEFAULT_MODEL
    return {"api_key": api_key, "model": model, "configured": bool(api_key)}


async def get_settings_public(db: AsyncSession) -> dict:
    """Same as get_settings but never includes the secret — safe to return to the browser."""
    s = await get_settings(db)
    return {"has_key": bool(s["api_key"]), "model": s["model"], "configured": s["configured"]}


async def set_settings(db: AsyncSession, api_key: Optional[str], model: str, updated_by: str) -> dict:
    """Save the Claude API key/model. A blank api_key keeps whatever is already stored."""
    row = await _get_row(db)
    if row is None:
        row = AISettings(model=model)
        db.add(row)

    row.model = model
    if api_key:
        row.api_key_encrypted = encrypt_token(api_key.strip())
    row.updated_by = updated_by

    await db.commit()
    return await get_settings_public(db)
