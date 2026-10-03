"""
StockMind AI — US Paper Trading Ledger & Tax Estimation
Simulated-only: no real brokerage call, no live quote to fill against. Orders
are an append-only ledger (app/models/paper_trading.py::PaperOrder); positions,
realized P&L and estimated tax are all computed on read here, from a single
FIFO lot-matching pass over the ledger, so every view (open positions, closed
trade history, tax summary) reconciles with the others instead of using two
different accounting methods.

Tax estimate is deliberately simplified and clearly labeled as such everywhere
it's surfaced (see TAX_DISCLAIMER): it applies flat short-term/long-term rates
per closed lot, mirroring the US short vs. long-term capital gains distinction
(held > 365 days = long-term) but ignoring the user's actual income bracket,
filing status, state taxes, wash-sale rules and loss offsetting across trades.
This is for paper-trading practice, not real tax guidance.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading import PaperOrder

# Illustrative flat rates only — see module docstring. 24% approximates a
# common US federal ordinary-income bracket (short-term gains are taxed as
# ordinary income); 15% is the most common long-term capital-gains bracket.
SHORT_TERM_TAX_RATE = 0.24
LONG_TERM_TAX_RATE = 0.15
LONG_TERM_HOLDING_DAYS = 365  # IRS rule is "more than one year" — approximated here

TAX_DISCLAIMER = (
    "ESTIMATED using simplified flat tax rates (24% short-term, 15% long-term) on a "
    "FIFO lot basis — not tax advice. Real US capital gains tax depends on your total "
    "income, filing status, state taxes, wash-sale rules and loss offsetting across "
    "trades, none of which are modeled here. For paper-trading practice only."
)


class PaperTradingError(Exception):
    pass


def _match_fifo(orders: list[PaperOrder]) -> tuple[list[dict], dict[str, list[dict]]]:
    """
    Single source of truth for all position/P&L/tax views. `orders` must be
    sorted oldest-first. Returns (closed_trades, open_lots_by_symbol):
      - closed_trades: one entry per matched BUY-lot-vs-SELL portion, oldest
        buy lots consumed first (FIFO, the IRS default method absent an
        election otherwise) — carries holding period, ST/LT term, and the
        estimated tax on that portion's gain.
      - open_lots_by_symbol: remaining unmatched BUY lots per symbol.
    """
    open_lots: dict[str, list[dict]] = {}
    closed_trades: list[dict] = []

    for o in orders:
        lots = open_lots.setdefault(o.symbol, [])
        if o.side == "BUY":
            lots.append({"quantity": o.quantity, "cost_basis": o.fill_price, "buy_date": o.created_at})
            continue

        # SELL — consume oldest lots first. place_paper_order() validates against
        # overselling before insert, so `lots` should always cover `o.quantity`;
        # if history was somehow inserted out of order, stop cleanly rather than
        # going negative.
        remaining = o.quantity
        while remaining > 0 and lots:
            lot = lots[0]
            qty = min(remaining, lot["quantity"])
            holding_days = (o.created_at - lot["buy_date"]).days
            term = "long_term" if holding_days > LONG_TERM_HOLDING_DAYS else "short_term"
            rate = LONG_TERM_TAX_RATE if term == "long_term" else SHORT_TERM_TAX_RATE
            cost_basis = qty * lot["cost_basis"]
            proceeds = qty * o.fill_price
            gain = proceeds - cost_basis
            estimated_tax = max(0.0, gain) * rate  # losses aren't taxed (loss offsetting itself isn't modeled)

            closed_trades.append({
                "symbol": o.symbol,
                "quantity": qty,
                "buy_date": lot["buy_date"].isoformat(),
                "sell_date": o.created_at.isoformat(),
                "holding_days": holding_days,
                "term": term,
                "cost_basis": cost_basis,
                "proceeds": proceeds,
                "gain": gain,
                "tax_rate": rate,
                "estimated_tax": estimated_tax,
                "after_tax_gain": gain - estimated_tax,
            })

            lot["quantity"] -= qty
            remaining -= qty
            if lot["quantity"] == 0:
                lots.pop(0)

    return closed_trades, open_lots


async def _ordered_orders(db: AsyncSession, user_id, symbol: Optional[str] = None) -> list[PaperOrder]:
    query = select(PaperOrder).where(PaperOrder.user_id == user_id)
    if symbol:
        query = query.where(PaperOrder.symbol == symbol.strip().upper())
    result = await db.execute(query.order_by(PaperOrder.created_at.asc()))
    return list(result.scalars().all())


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

    if side == "SELL":
        # No real brokerage to reject an invalid sell, so this app enforces
        # long-only paper trading itself — same as the real Indian order flow,
        # which also doesn't support shorting.
        existing = await _ordered_orders(db, user_id, symbol)
        _, open_lots = _match_fifo(existing)
        held = sum(lot["quantity"] for lot in open_lots.get(symbol, []))
        if quantity > held:
            raise PaperTradingError(
                f"Can't paper-sell {quantity} shares of {symbol} — you only hold {held}. "
                "Paper trading here is long-only (no short selling)."
            )

    order = PaperOrder(
        user_id=user_id, symbol=symbol, side=side, quantity=quantity,
        fill_price=fill_price, notes=notes,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def list_paper_orders(db: AsyncSession, user_id, symbol: Optional[str] = None) -> list[PaperOrder]:
    orders = await _ordered_orders(db, user_id, symbol)
    return list(reversed(orders))  # newest first for display


async def compute_positions(db: AsyncSession, user_id) -> list[dict]:
    """
    Per symbol: open quantity + weighted-average cost of the remaining open
    FIFO lots, plus realized P&L and estimated tax summed from every closed
    trade for that symbol (see _match_fifo) — reconciles exactly with
    compute_closed_trades()/compute_tax_summary() since they share one pass.
    No unrealized P&L — that needs a current price, which this app has no
    live source for.
    """
    orders = await _ordered_orders(db, user_id)
    closed_trades, open_lots = _match_fifo(orders)

    positions: dict[str, dict] = {}
    for symbol, lots in open_lots.items():
        qty = sum(lot["quantity"] for lot in lots)
        if qty == 0:
            continue
        cost = sum(lot["quantity"] * lot["cost_basis"] for lot in lots)
        positions[symbol] = {"symbol": symbol, "quantity": qty, "avg_cost": cost / qty, "realized_pnl": 0.0, "estimated_tax": 0.0}

    for t in closed_trades:
        pos = positions.setdefault(t["symbol"], {"symbol": t["symbol"], "quantity": 0, "avg_cost": 0.0, "realized_pnl": 0.0, "estimated_tax": 0.0})
        pos["realized_pnl"] += t["gain"]
        pos["estimated_tax"] += t["estimated_tax"]

    return [p for p in positions.values() if p["quantity"] != 0 or p["realized_pnl"] != 0]


async def compute_closed_trades(db: AsyncSession, user_id, symbol: Optional[str] = None) -> list[dict]:
    """Every FIFO-matched closed lot (buy/sell pair), newest sell first — the
    detailed buy/sell/tax history for the Trade History view."""
    orders = await _ordered_orders(db, user_id, symbol)
    closed_trades, _ = _match_fifo(orders)
    return sorted(closed_trades, key=lambda t: t["sell_date"], reverse=True)


async def compute_tax_summary(db: AsyncSession, user_id) -> dict:
    """Aggregate realized-gain/tax totals across every symbol — the single
    call the Dashboard card and the US Stocks summary strip both use."""
    orders = await _ordered_orders(db, user_id)
    closed_trades, open_lots = _match_fifo(orders)

    total_realized_gain = sum(t["gain"] for t in closed_trades)
    total_estimated_tax = sum(t["estimated_tax"] for t in closed_trades)
    short_term_gain = sum(t["gain"] for t in closed_trades if t["term"] == "short_term")
    long_term_gain = sum(t["gain"] for t in closed_trades if t["term"] == "long_term")
    short_term_tax = sum(t["estimated_tax"] for t in closed_trades if t["term"] == "short_term")
    long_term_tax = sum(t["estimated_tax"] for t in closed_trades if t["term"] == "long_term")
    open_cost_basis = sum(lot["quantity"] * lot["cost_basis"] for lots in open_lots.values() for lot in lots)
    open_positions_count = sum(1 for lots in open_lots.values() if sum(l["quantity"] for l in lots) > 0)

    return {
        "total_realized_gain": total_realized_gain,
        "total_estimated_tax": total_estimated_tax,
        "net_after_tax": total_realized_gain - total_estimated_tax,
        "short_term_gain": short_term_gain,
        "short_term_tax": short_term_tax,
        "long_term_gain": long_term_gain,
        "long_term_tax": long_term_tax,
        "closed_trade_count": len(closed_trades),
        "open_positions_count": open_positions_count,
        "open_cost_basis": open_cost_basis,
        "tax_rates": {"short_term": SHORT_TERM_TAX_RATE, "long_term": LONG_TERM_TAX_RATE},
        "disclaimer": TAX_DISCLAIMER,
    }
