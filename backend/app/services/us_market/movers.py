"""
StockMind AI — US Movers
Ranks the approved ~24-symbol US universe by today's change% / volume, using
one Alpaca multi-symbol snapshot call (not one request per symbol). Returns
the same honest {"data_available": False, ...} shape as the rest of the US
pipeline when Alpaca isn't configured or the call fails — never fabricated.
"""

from typing import Optional

from app.services.us_market.alpaca_client import AlpacaAPIError, AlpacaClient
from app.services.us_market.universe import us_symbol_sector_lookup

_SECTOR_LOOKUP = us_symbol_sector_lookup()
_UNIVERSE_SYMBOLS = sorted(_SECTOR_LOOKUP)


def _row_from_snapshot(symbol: str, snap: dict) -> Optional[dict]:
    daily = snap.get("dailyBar") or {}
    prev = snap.get("prevDailyBar") or {}
    trade = snap.get("latestTrade") or {}
    ltp = trade.get("p") if trade.get("p") is not None else daily.get("c")
    prev_close = prev.get("c")
    if ltp is None or not prev_close:
        return None
    change = ltp - prev_close
    return {
        "symbol": symbol,
        "name": symbol,
        "sector": _SECTOR_LOOKUP.get(symbol, ""),
        "ltp": ltp,
        "change": change,
        "change_pct": round(change / prev_close * 100, 2),
        "volume": daily.get("v"),
    }


async def compute_us_movers(alpaca: Optional[AlpacaClient], top_n: int = 5) -> dict:
    if not alpaca:
        return {
            "data_available": False,
            "reason": "No Alpaca API key configured — add a free key in Settings → Broker API Credentials.",
            "gainers": [], "losers": [], "most_active": [],
        }
    try:
        snapshots = await alpaca.get_snapshots(_UNIVERSE_SYMBOLS)
    except AlpacaAPIError as e:
        return {"data_available": False, "reason": str(e), "gainers": [], "losers": [], "most_active": []}

    rows = [r for symbol, snap in snapshots.items() if (r := _row_from_snapshot(symbol, snap)) is not None]
    gainers = sorted(rows, key=lambda r: r["change_pct"], reverse=True)[:top_n]
    losers = sorted(rows, key=lambda r: r["change_pct"])[:top_n]
    most_active = sorted((r for r in rows if r["volume"] is not None), key=lambda r: r["volume"], reverse=True)[:top_n]

    return {
        "data_available": True,
        "gainers": gainers, "losers": losers, "most_active": most_active,
        "metadata": {"source": "alpaca", "universe_size": len(_UNIVERSE_SYMBOLS), "resolved": len(rows)},
    }
