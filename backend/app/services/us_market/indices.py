"""
StockMind AI — US Index Proxies (ticker strip + Market Overview chart)
Alpaca has no direct "index" quote — S&P 500 / Nasdaq 100 / Dow Jones are
shown via their standard ETF proxies (SPY/QQQ/DIA), labeled as such rather
than presented as if they were the index itself. Confirmed live: real quotes
and real daily bars both work for all three on the free tier.
"""

from datetime import date, timedelta
from typing import Optional

from app.services.us_market.alpaca_client import AlpacaAPIError, AlpacaClient

US_INDEX_PROXIES = [
    {"name": "S&P 500", "symbol": "SPY"},
    {"name": "Nasdaq 100", "symbol": "QQQ"},
    {"name": "Dow Jones", "symbol": "DIA"},
]

_RANGE_DAYS = {"1W": 7, "1M": 30, "3M": 90, "1Y": 365}


async def get_us_indices_latest(alpaca: Optional[AlpacaClient]) -> dict:
    if not alpaca:
        return {"data_available": False, "reason": "No Alpaca API key configured.", "indices": []}
    symbols = [p["symbol"] for p in US_INDEX_PROXIES]
    try:
        snapshots = await alpaca.get_snapshots(symbols)
    except AlpacaAPIError as e:
        return {"data_available": False, "reason": str(e), "indices": []}

    indices = []
    for proxy in US_INDEX_PROXIES:
        snap = snapshots.get(proxy["symbol"]) or {}
        daily = snap.get("dailyBar") or {}
        prev = snap.get("prevDailyBar") or {}
        trade = snap.get("latestTrade") or {}
        ltp = trade.get("p") if trade.get("p") is not None else daily.get("c")
        prev_close = prev.get("c")
        change = (ltp - prev_close) if (ltp is not None and prev_close) else None
        indices.append({
            "name": proxy["name"], "symbol": proxy["symbol"], "price": ltp,
            "change": change, "change_pct": round(change / prev_close * 100, 2) if change is not None and prev_close else None,
        })
    return {"data_available": True, "indices": indices, "source": "alpaca (ETF proxy)"}


async def get_us_indices_history(alpaca: Optional[AlpacaClient], range_key: str) -> dict:
    if not alpaca:
        return {"data_available": False, "reason": "No Alpaca API key configured.", "series": []}
    days = _RANGE_DAYS.get(range_key, 30)
    start = (date.today() - timedelta(days=days)).isoformat()
    end = date.today().isoformat()

    series = []
    for proxy in US_INDEX_PROXIES:
        try:
            bars = await alpaca.get_daily_bars(proxy["symbol"], start, end)
        except AlpacaAPIError as e:
            return {"data_available": False, "reason": str(e), "series": []}
        if not bars:
            continue
        base = bars[0]["c"]
        points = [{"t": b["t"], "value": round((b["c"] - base) / base * 100, 2)} for b in bars if base]
        series.append({"name": proxy["name"], "symbol": proxy["symbol"], "points": points})

    return {"data_available": bool(series), "series": series, "range": range_key, "source": "alpaca (ETF proxy)"}
