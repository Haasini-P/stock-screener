"""
StockMind AI — Portfolio Routes
REST API endpoints for portfolio holdings, positions, analysis, and risk.
User data is strictly isolated — User A cannot access User B's portfolio.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.routes.signals import CapitalQuery, RiskQuery, analyze_stock
from app.core.logging import get_logger
from app.database import get_db
from app.models.user import User
from app.services.upstox.auth import UpstoxAuthService
from app.services.upstox.provider import UpstoxDataProvider
from app.services.upstox.client import UpstoxDataUnavailableError, UpstoxAPIError

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])
logger = get_logger(__name__)


async def _get_user_provider(user: User, db: AsyncSession) -> UpstoxDataProvider:
    """Get provider with user's Upstox token. Strictly user-scoped."""
    auth_service = UpstoxAuthService(db)
    token = await auth_service.get_access_token(user.id)

    if not token:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Upstox account not connected.",
                "action": "Connect your Upstox account via Settings → Connect Upstox.",
            },
        )

    return UpstoxDataProvider(access_token=token)


@router.get("")
async def portfolio_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get complete portfolio overview.
    Holdings + Positions + P&L + Risk metrics.
    """
    try:
        provider = await _get_user_provider(user, db)

        holdings = await provider.get_holdings()
        positions = await provider.get_positions()

        holdings_data = holdings.get("data", [])
        positions_data = positions.get("data", [])

        # Calculate portfolio-level metrics
        total_invested = 0.0
        total_current = 0.0
        sector_allocation = {}
        holdings_list = []

        if isinstance(holdings_data, list):
            for h in holdings_data:
                qty = h.get("quantity", 0)
                avg_price = h.get("average_price", 0)
                ltp = h.get("last_price", 0)

                invested = qty * avg_price
                current = qty * ltp
                pnl = current - invested
                pnl_pct = (pnl / invested * 100) if invested else 0

                total_invested += invested
                total_current += current

                holding_item = {
                    "symbol": h.get("trading_symbol", ""),
                    "instrument_key": h.get("instrument_key", ""),
                    "isin": h.get("isin", ""),
                    "exchange": h.get("exchange", ""),
                    "quantity": qty,
                    "average_price": avg_price,
                    "last_price": ltp,
                    "invested_value": round(invested, 2),
                    "current_value": round(current, 2),
                    "pnl": round(pnl, 2),
                    "pnl_percentage": round(pnl_pct, 2),
                    "day_change": h.get("day_change", 0),
                    "day_change_percentage": h.get("day_change_percentage", 0),
                }
                holdings_list.append(holding_item)

        total_pnl = total_current - total_invested
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0

        # Calculate allocation percentages
        for h in holdings_list:
            h["allocation_pct"] = round(
                (h["current_value"] / total_current * 100) if total_current else 0, 2
            )

        # Concentration risk (Herfindahl index)
        allocations = [h["allocation_pct"] / 100 for h in holdings_list]
        hhi = sum(a ** 2 for a in allocations) if allocations else 0

        return {
            "summary": {
                "total_invested": round(total_invested, 2),
                "total_current_value": round(total_current, 2),
                "total_pnl": round(total_pnl, 2),
                "total_pnl_percentage": round(total_pnl_pct, 2),
                "holdings_count": len(holdings_list),
                "positions_count": len(positions_data) if isinstance(positions_data, list) else 0,
            },
            "risk": {
                "concentration_hhi": round(hhi, 4),
                "concentration_level": (
                    "High" if hhi > 0.25 else "Moderate" if hhi > 0.15 else "Low"
                ),
                "top_holding_pct": max(
                    (h["allocation_pct"] for h in holdings_list), default=0
                ),
            },
            "holdings": holdings_list,
            "positions": positions_data,
            "metadata": holdings.get("metadata"),
        }

    except UpstoxDataUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Portfolio data unavailable. Upstox connection issue.",
        )
    except UpstoxAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/holdings")
async def get_holdings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed holdings list."""
    try:
        provider = await _get_user_provider(user, db)
        holdings = await provider.get_holdings()
        return holdings

    except UpstoxDataUnavailableError:
        raise HTTPException(status_code=503, detail="Holdings data unavailable.")


@router.get("/recommendations")
async def portfolio_recommendations(
    capital: float = CapitalQuery,
    risk_pct: float = RiskQuery,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    For every real holding in the user's connected Upstox account, runs the
    exact same signal analysis used everywhere else in the app (Scanner,
    Daily Signals, Stock Report) and returns ADD/HOLD/REDUCE guidance —
    "should I buy more of what I already own, or trim it" — instead of the
    old behaviour of silently excluding holdings from analysis entirely.
    """
    try:
        provider = await _get_user_provider(user, db)
        holdings = await provider.get_holdings()
    except UpstoxDataUnavailableError:
        raise HTTPException(status_code=503, detail="Holdings data unavailable.")

    rows = holdings.get("data") or []
    items = []
    for h in rows:
        symbol = h.get("trading_symbol")
        if not symbol:
            continue
        qty = h.get("quantity", 0)
        avg_price = h.get("average_price", 0)
        ltp = h.get("last_price", 0)
        invested = qty * avg_price
        current = qty * ltp
        pnl = current - invested
        item = {
            "symbol": symbol,
            "quantity": qty,
            "average_price": avg_price,
            "last_price": ltp,
            "invested_value": round(invested, 2),
            "current_value": round(current, 2),
            "pnl": round(pnl, 2),
            "pnl_percentage": round(pnl / invested * 100, 2) if invested else 0,
            "action": None,
            "error": None,
        }
        try:
            analysis = await analyze_stock(symbol, capital, risk_pct, user, db)
            s = analysis["signal"]
            item.update({
                "action": s["holding"]["action"],
                "entry": s["signal"]["entry"],
                "trend": s["technical"]["trend"],
                "rsi": s["technical"]["rsi"],
                "entry_zone": s["entry_exit"]["entry_zone"],
                "stop_loss": s["entry_exit"]["stop_loss"],
                "target_1": s["entry_exit"]["target_1"],
                "confidence": s["prediction"]["confidence"],
                "risk": s["prediction"]["risk"],
                "explanation": s.get("explanation") or analysis.get("technical_summary"),
            })
        except Exception as e:
            logger.warning("portfolio_recommendation_failed", symbol=symbol, error=str(e))
            item["error"] = f"Could not analyze {symbol}: {e}"
        items.append(item)

    return {"items": items, "count": len(items)}


@router.get("/positions")
async def get_positions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current day positions."""
    try:
        provider = await _get_user_provider(user, db)
        positions = await provider.get_positions()
        return positions

    except UpstoxDataUnavailableError:
        raise HTTPException(status_code=503, detail="Positions data unavailable.")


@router.get("/mtf-positions")
async def get_mtf_positions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get MTF (Margin Trading Facility) positions."""
    try:
        provider = await _get_user_provider(user, db)
        mtf = await provider.get_mtf_positions()
        return mtf

    except UpstoxDataUnavailableError:
        raise HTTPException(status_code=503, detail="MTF positions data unavailable.")


@router.get("/pnl")
async def get_pnl(
    from_date: str,
    to_date: str,
    segment: str = "EQ",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trade-wise profit and loss report."""
    try:
        provider = await _get_user_provider(user, db)
        pnl = await provider.get_pnl(from_date, to_date, segment)
        return pnl

    except UpstoxAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/funds")
async def get_funds(
    segment: str = "SEC",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get fund balance and margin details."""
    try:
        provider = await _get_user_provider(user, db)
        funds = await provider.get_funds_and_margin(segment)
        return funds

    except UpstoxAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
