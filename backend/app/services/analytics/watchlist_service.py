"""
StockMind AI — Scanner Watchlist Service
Auto-tracks symbols the scanner flags (first-seen date, never overwritten)
and lets the user manually add/reclassify/remove symbols regardless of
whether they currently pass the live technical screen.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.watchlist import TERMS, WatchlistItem

logger = get_logger(__name__)

# Maps each scanner bucket to the holding-period it's actually designed for,
# based on the screen criteria in app/services/analytics/signals.py:
#   - momentum_breakout: volume-driven breakout already underway (ADX>25, RSI 55-70)
#     -> played out over days, not held long. Short term.
#   - breakout_retest: waiting for a pullback entry inside a recent breakout
#     -> days to a couple weeks once it triggers. Short term.
#   - early_stage_breakout: a volatility-compression base just starting to break
#     -> position-building, typically weeks to a couple months. Mid term.
#   - quality_pullback: requires the 200-day trend intact — a dip-buy inside a
#     structural uptrend, meant to be held while that trend plays out. Long term.
BUCKET_TERM_MAP = {
    "momentum_breakout": "short",
    "breakout_retest": "short",
    "early_stage_breakout": "mid",
    "quality_pullback": "long",
}
DEFAULT_TERM = "mid"


class WatchlistError(Exception):
    pass


async def sync_from_scan(db: AsyncSession, rows: list[dict]) -> int:
    """
    Registers any newly-flagged symbol (non-empty `buckets`) as first-seen now.
    Idempotent — never touches a symbol already tracked, so added_at always
    reflects the date it was *first* flagged, however many times this runs.
    """
    flagged = {r["symbol"]: (r.get("buckets") or [None])[0] for r in rows if r.get("buckets")}
    if not flagged:
        return 0

    existing = await db.execute(select(WatchlistItem.symbol).where(WatchlistItem.symbol.in_(flagged)))
    existing_symbols = {row[0] for row in existing.all()}

    new_count = 0
    for symbol, bucket in flagged.items():
        if symbol in existing_symbols:
            continue
        db.add(WatchlistItem(
            symbol=symbol,
            term=BUCKET_TERM_MAP.get(bucket, DEFAULT_TERM),
            source="auto",
            bucket=bucket,
        ))
        new_count += 1

    if new_count:
        await db.commit()
        logger.info("watchlist_auto_synced", new_symbols=new_count)
    return new_count


async def list_all(db: AsyncSession) -> list[WatchlistItem]:
    result = await db.execute(select(WatchlistItem).order_by(WatchlistItem.added_at.desc()))
    return list(result.scalars().all())


async def add_manual(db: AsyncSession, symbol: str, term: str, added_by: Optional[str]) -> WatchlistItem:
    symbol = symbol.strip().upper()
    if term not in TERMS:
        raise WatchlistError(f"term must be one of {TERMS}")

    existing = await db.execute(select(WatchlistItem).where(WatchlistItem.symbol == symbol))
    row = existing.scalar_one_or_none()
    if row is not None:
        # Already tracked (likely auto-flagged earlier) — a manual add re-classifies
        # it but keeps the original first-seen date; that's still the honest answer
        # to "when did this idea first show up".
        row.term = term
        row.source = "manual"
        row.added_by = added_by
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = WatchlistItem(symbol=symbol, term=term, source="manual", bucket=None, added_by=added_by)
        db.add(row)

    await db.commit()
    await db.refresh(row)
    logger.info("watchlist_manual_add", symbol=symbol, term=term, added_by=added_by)
    return row


async def set_term(db: AsyncSession, symbol: str, term: str) -> WatchlistItem:
    if term not in TERMS:
        raise WatchlistError(f"term must be one of {TERMS}")
    result = await db.execute(select(WatchlistItem).where(WatchlistItem.symbol == symbol.strip().upper()))
    row = result.scalar_one_or_none()
    if row is None:
        raise WatchlistError(f"{symbol} is not on the watchlist.")
    row.term = term
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def remove(db: AsyncSession, symbol: str) -> None:
    result = await db.execute(select(WatchlistItem).where(WatchlistItem.symbol == symbol.strip().upper()))
    row = result.scalar_one_or_none()
    if row is None:
        raise WatchlistError(f"{symbol} is not on the watchlist.")
    await db.delete(row)
    await db.commit()
