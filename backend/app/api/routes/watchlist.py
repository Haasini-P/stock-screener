"""
StockMind AI — Scanner Watchlist Routes
Read-only listing is open to any session (mirrors the rest of market data);
adding, reclassifying or removing a tracked symbol requires login, same as
every other settings-mutating route in this app.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_optional_user
from app.database import get_db
from app.models.user import User
from app.models.watchlist import TERMS
from app.services.analytics.watchlist_service import WatchlistError, add_manual, list_all, remove, set_term

router = APIRouter(prefix="/api/watchlist", tags=["Watchlist"])


class WatchlistAdd(BaseModel):
    symbol: str = Field(min_length=1, max_length=50)
    term: str = Field(min_length=1, max_length=10)


class WatchlistTermUpdate(BaseModel):
    term: str = Field(min_length=1, max_length=10)


def _serialize(row) -> dict:
    return {
        "symbol": row.symbol,
        "term": row.term,
        "source": row.source,
        "bucket": row.bucket,
        "added_by": row.added_by,
        "added_at": row.added_at.isoformat() if row.added_at else None,
    }


@router.get("")
async def get_watchlist(user: Optional[User] = Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    """Every tracked symbol — auto-flagged by the scanner or manually added — with its first-seen date and term."""
    rows = await list_all(db)
    return {"items": [_serialize(r) for r in rows], "terms": list(TERMS)}


@router.post("")
async def add_watchlist_item(
    body: WatchlistAdd,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually track a symbol regardless of whether it currently passes the live scanner screen."""
    try:
        row = await add_manual(db, body.symbol, body.term, user.email)
    except WatchlistError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _serialize(row)


@router.put("/{symbol}")
async def update_watchlist_term(
    symbol: str,
    body: WatchlistTermUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reclassify a tracked symbol's term (short/mid/long)."""
    try:
        row = await set_term(db, symbol, body.term)
    except WatchlistError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _serialize(row)


@router.delete("/{symbol}")
async def remove_watchlist_item(
    symbol: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop tracking a symbol."""
    try:
        await remove(db, symbol)
    except WatchlistError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "removed", "symbol": symbol.upper()}
