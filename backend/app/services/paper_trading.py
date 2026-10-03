"""
StockMind AI — US Paper Trading Ledger
Simulated-only: no real brokerage call, no live quote to fill against. Orders
are an append-only ledger (app/models/paper_trading.py::PaperOrder); positions
and realized P&L are computed on read here rather than stored denormalized,
so there's nothing to keep in sync.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading import PaperOrder


class PaperTradingError(Exception):
    pass


async def place_paper_order(
    db: AsyncSession, user_id, symbol: str, side: str, quantity: int, fill_price: float,
    notes: Optional[str] = None,
) -> PaperOrder:
    symbol = symbol.strip().upper()
    side = side.strip().upper()
    if side not in ("BUY", "SELL"):
        raise PaperTradingError("side must be BUY or SELL.")
    if quantity <= 0:
        raise PaperTradingError("quantity must be positive.")
    if fill_price <= 0:
        raise PaperTradingError("fill_price must be positive.")

    order = PaperOrder(
        user_id=user_id, symbol=symbol, side=side, quantity=quantity,
        fill_price=fill_price, notes=notes,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def list_paper_orders(db: AsyncSession, user_id, symbol: Optional[str] = None) -> list[PaperOrder]:
    query = select(PaperOrder).where(PaperOrder.user_id == user_id)
    if symbol:
        query = query.where(PaperOrder.symbol == symbol.strip().upper())
    result = await db.execute(query.order_by(PaperOrder.created_at.desc()))
    return list(result.scalars().all())


async def compute_positions(db: AsyncSession, user_id) -> list[dict]:
    """
    Aggregates every symbol's orders (oldest first) into a running position:
    net quantity, weighted-average cost of the currently-open quantity, and
    realized P&L on whatever portion has been sold/closed so far. There is no
    unrealized P&L here — that needs a current price, which this app has no
    live source for (the frontend lets the user enter their own "mark price"
    to see an unrealized number, clearly labeled as self-reported).
    """
    result = await db.execute(
        select(PaperOrder).where(PaperOrder.user_id == user_id).order_by(PaperOrder.created_at.asc())
    )
    orders = result.scalars().all()

    by_symbol: dict[str, dict] = {}
    for o in orders:
        pos = by_symbol.setdefault(o.symbol, {"symbol": o.symbol, "quantity": 0, "avg_cost": 0.0, "realized_pnl": 0.0})
        if o.side == "BUY":
            total_cost = pos["avg_cost"] * pos["quantity"] + o.fill_price * o.quantity
            pos["quantity"] += o.quantity
            pos["avg_cost"] = total_cost / pos["quantity"] if pos["quantity"] else 0.0
        else:  # SELL
            closed_qty = min(o.quantity, pos["quantity"])
            pos["realized_pnl"] += (o.fill_price - pos["avg_cost"]) * closed_qty
            pos["quantity"] -= closed_qty
            if pos["quantity"] == 0:
                pos["avg_cost"] = 0.0

    return [p for p in by_symbol.values() if p["quantity"] != 0 or p["realized_pnl"] != 0]
