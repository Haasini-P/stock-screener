"""
StockMind AI — India Index Strip (Dashboard ticker strip + Market Overview chart)
Deliberately separate from app/services/analytics/market_state.py (used by the
regime/signal pipeline) so this Dashboard-only addition can't affect regime
classification — NIFTY 50 and NIFTY BANK already flow through market_state.py,
but SENSEX does not (its INDEX_KEYS list is NSE-only). Confirmed live that
BSE_INDEX|SENSEX is a real, valid Upstox instrument key.
"""

from datetime import date, timedelta

from app.services.upstox.provider import UpstoxDataProvider

INDIA_INDICES = [
    {"name": "NIFTY 50", "key": "NSE_INDEX|Nifty 50"},
    {"name": "SENSEX", "key": "BSE_INDEX|SENSEX"},
    {"name": "NIFTY BANK", "key": "NSE_INDEX|Nifty Bank"},
]

_RANGE_DAYS = {"1W": 7, "1M": 30, "3M": 90, "1Y": 365}


async def get_india_indices_latest(provider: UpstoxDataProvider) -> dict:
    keys = [idx["key"] for idx in INDIA_INDICES]
    quotes = (await provider.get_quotes(keys)).get("data") or {}

    indices = []
    for idx in INDIA_INDICES:
        # Upstox echoes quote keys back with ":" instead of "|" — confirmed live.
        row = quotes.get(idx["key"].replace("|", ":")) or {}
        price = row.get("last_price")
        change = row.get("net_change")
        prev_close = (price - change) if (price is not None and change is not None) else None
        indices.append({
            "name": idx["name"], "key": idx["key"], "price": price, "change": change,
            "change_pct": round(change / prev_close * 100, 2) if change is not None and prev_close else None,
        })
    return {"data_available": True, "indices": indices, "source": "upstox"}


async def get_india_indices_history(provider: UpstoxDataProvider, range_key: str) -> dict:
    days = _RANGE_DAYS.get(range_key, 30)
    from_date = (date.today() - timedelta(days=days)).isoformat()

    series = []
    for idx in INDIA_INDICES:
        try:
            resp = await provider.get_historical_candles(idx["key"], "day", from_date=from_date)
        except Exception:
            continue
        candles = (resp.get("data") or {}).get("candles") or []
        if not candles:
            continue
        candles = sorted(candles, key=lambda c: c[0])
        base = candles[0][4]  # close
        points = [{"t": c[0], "value": round((c[4] - base) / base * 100, 2)} for c in candles if base]
        series.append({"name": idx["name"], "key": idx["key"], "points": points})

    return {"data_available": bool(series), "series": series, "range": range_key, "source": "upstox"}
