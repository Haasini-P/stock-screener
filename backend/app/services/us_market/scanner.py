"""
StockMind AI — US Scanner
Runs the same per-symbol analysis as the Stock Report (FeatureEngine ->
SignalEngine -> EnsemblePredictionEngine, all confirmed market-agnostic) across
the default US watchlist, surfacing favorable setups first. Mirrors the
Indian Market Scanner's role: like that scanner, this does NOT scan every
possible US security — it's bounded to a default candidate list for the same
reason (an unbounded multi-thousand-symbol technical scan isn't feasible on a
free-tier rate-limited API). Searching/analyzing an individual stock outside
this list still works fine via resolve_instrument's permissive validation —
only the *scanner's* candidate pool is bounded, not what you can look up.

Never places an order — this only classifies and ranks; Buy/Sell on the
frontend opens the existing PaperOrderDialog pre-filled for the user to
confirm, same as everywhere else in this app.
"""

import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.us_market.analysis import analyze_us_stock
from app.services.us_market.provider import USMarketProvider
from app.services.us_market.universe import us_symbol_sector_lookup

_FAVORABLE_ENTRIES = {"BUY_NOW", "BUY_ON_RETEST", "BUY_ON_DIP", "BREAKOUT_WATCH"}
_CONCURRENCY = 8


async def run_us_scanner(provider: USMarketProvider, user: Optional[User], db: AsyncSession) -> dict:
    symbols = sorted(us_symbol_sector_lookup())
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def scan_one(symbol: str) -> Optional[dict]:
        async with semaphore:
            try:
                result = await analyze_us_stock(provider, symbol, user, db)
            except Exception:
                return None
        if not result.get("data_available"):
            return None
        s = result.get("signal") or {}
        tech = s.get("technical") or {}
        ee = s.get("entry_exit") or {}
        holding = s.get("holding") or {}
        entry = (s.get("signal") or {}).get("entry")
        return {
            "symbol": symbol,
            "sector": result.get("sector"),
            "ltp": (result.get("quote") or {}).get("ltp"),
            "entry": entry,
            "favorable": entry in _FAVORABLE_ENTRIES,
            "is_holding": holding.get("is_holding", False),
            "holding_action": holding.get("action"),
            "rsi": tech.get("rsi"),
            "adx": tech.get("adx"),
            "trend": tech.get("trend"),
            "volume_ratio": tech.get("volume_ratio"),
            "entry_zone": ee.get("entry_zone"),
            "stop_loss": ee.get("stop_loss"),
            "target_1": ee.get("target_1"),
            "target_2": ee.get("target_2"),
            "risk_reward": ee.get("risk_reward"),
        }

    rows = [r for r in await asyncio.gather(*(scan_one(sym) for sym in symbols)) if r is not None]
    rows.sort(key=lambda r: (not r["favorable"], r["symbol"]))

    return {
        "data_available": bool(rows),
        "rows": rows,
        "scanned": len(symbols),
        "resolved": len(rows),
        "reason": None if rows else "No Alpaca API key configured, or no symbols returned enough data to analyze.",
    }
