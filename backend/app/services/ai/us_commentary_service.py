"""
StockMind AI — US Stock "AI Research Notes"
Mirrors the shape of app/services/ai/commentary_service.py's single-stock flow
(resolve -> build context -> cache-check by context_hash -> call model -> cache)
but reuses only its model-dispatch helper (_call_model) — the system prompt,
cache table (USCommentaryCache, not AICommentary) and context builder are all
separate, so nothing about the live Indian AI commentary path is touched.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.paper_trading import USCommentaryCache
from app.services.ai.ai_config import get_settings
from app.services.ai.commentary_service import CommentaryError, _call_model
from app.services.analytics.us_research_prompt import US_RESEARCH_PROMPT
from app.services.us_market.provider import USDataUnavailableError, get_us_provider

logger = get_logger(__name__)


def _build_us_context(symbol: str, sector: str) -> str:
    return (
        f"Ticker: {symbol}\nSector (StockMind's own classification, not live data): {sector}\n\n"
        "StockMind has no live market data for this ticker (see system prompt). Give the general "
        "business overview described in your instructions."
    )


async def generate_us_research(db: AsyncSession, symbol: str) -> dict:
    """Generate (or return cached) AI Research Notes for a US symbol. Raises
    CommentaryError on failure (not configured, symbol not approved, API error)."""
    provider = get_us_provider()
    try:
        inst = await provider.resolve_instrument(symbol)
    except USDataUnavailableError as e:
        raise CommentaryError(str(e))

    settings = await get_settings(db)
    if not settings["configured"]:
        raise CommentaryError(
            f"{settings['provider'].title()} API key not configured. Add it in Settings → AI Commentary."
        )

    context = _build_us_context(inst["symbol"], inst["sector"])
    context_hash = hashlib.sha256(f"{inst['symbol']}:{US_RESEARCH_PROMPT}:{context}".encode()).hexdigest()

    cached = await db.execute(
        select(USCommentaryCache)
        .where(USCommentaryCache.symbol == inst["symbol"], USCommentaryCache.context_hash == context_hash)
        .order_by(USCommentaryCache.created_at.desc())
        .limit(1)
    )
    row = cached.scalar_one_or_none()
    if row is not None:
        return {"content": row.content, "model": row.model_used, "cached": True, "generated_at": row.created_at.isoformat()}

    try:
        text = await _call_model(
            settings["provider"], settings["model"], settings["api_key"],
            US_RESEARCH_PROMPT, context, None, max_tokens=1024,
        )
    except CommentaryError as e:
        logger.error("us_research_failed", symbol=inst["symbol"], provider=settings["provider"], error=str(e))
        raise

    row = USCommentaryCache(symbol=inst["symbol"], context_hash=context_hash, content=text, model_used=settings["model"])
    db.add(row)
    await db.commit()

    logger.info("us_research_generated", symbol=inst["symbol"], model=settings["model"])
    return {"content": text, "model": settings["model"], "cached": False, "generated_at": datetime.now(timezone.utc).isoformat()}
