"""
StockMind AI — US Paper Trading Routes
Simulated-only orders (app/services/paper_trading.py) — no real brokerage
call. Behind get_current_user since paper P&L is per-user, same as every
other mutating route in this app.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.paper_trading import (
    PaperTradingError, compute_positions, list_paper_orders, place_paper_order,
)

router = APIRouter(prefix="/api/us/paper", tags=["US Paper Trading"])


class PaperOrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: str = Field(min_length=3, max_length=4)
    quantity: int = Field(gt=0)
    fill_price: float = Field(gt=0)
    notes: Optional[str] = Field(default=None, max_length=255)


def _serialize(order) -> dict:
    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "fill_price": order.fill_price,
        "notes": order.notes,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


@router.post("/orders")
async def place_order_route(
    body: PaperOrderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Records a simulated fill — there is no live US quote to execute against, so
    fill_price is whatever the user entered."""
    try:
        order = await place_paper_order(db, user.id, body.symbol, body.side, body.quantity, body.fill_price, body.notes)
    except PaperTradingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _serialize(order)


@router.get("/orders")
async def my_orders(
    symbol: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orders = await list_paper_orders(db, user.id, symbol)
    return {"orders": [_serialize(o) for o in orders]}


@router.get("/positions")
async def my_positions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Net quantity, weighted-average cost and realized P&L per symbol, computed
    from the order ledger. No unrealized P&L — no live price to mark against."""
    return {"positions": await compute_positions(db, user.id)}
