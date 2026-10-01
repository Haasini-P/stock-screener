"""
StockMind AI — Market Data Routes
REST API endpoints for market overview, quotes, candles, fundamentals, news,
scanner, sector map and movers.

Upstox errors raised here are translated to HTTP responses by the
exception handlers registered in app.main.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_optional_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.analytics.market_state import get_market_state
from app.services.analytics.screener import SECTOR_UNIVERSE, MarketScreener, sector_summary
from app.services.upstox.auth import UpstoxAuthService
from app.services.upstox.client import UpstoxAPIError
from app.services.upstox.provider import UpstoxDataProvider

router = APIRouter(prefix="/api", tags=["Market Data"])
settings = get_settings()

# One provider (and HTTP connection pool) per token, reused across requests
_providers: dict[str, UpstoxDataProvider] = {}

BUCKETS = ["momentum_breakout", "breakout_retest", "early_stage_breakout", "quality_pullback"]
ENTRY_TYPES = ["BUY_NOW", "BUY_ON_RETEST", "BUY_ON_DIP", "BREAKOUT_WATCH", "WAIT", "AVOID", "EXTENDED"]
SORT_FIELDS = {
    "symbol", "ltp", "change_pct", "volume_ratio", "rsi", "adx", "return_5d",
    "return_20d", "dist_52w_high", "probability_up",
}


async def get_market_provider(user: Optional[User], db: AsyncSession) -> UpstoxDataProvider:
    """Provider using the user's Upstox OAuth token, falling back to the analytics token."""
    token = None
    if user:
        token = await UpstoxAuthService(db).get_access_token(user.id)
    if not token:
        token = settings.upstox_analytics_token

    if not token:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Upstox data currently unavailable — no valid credentials configured.",
                "action": "Set UPSTOX_ANALYTICS_TOKEN in backend/.env or connect your Upstox account.",
            },
        )

    if token not in _providers:
        _providers[token] = UpstoxDataProvider(access_token=token)
    return _providers[token]


async def get_screener_rows(
    provider: UpstoxDataProvider, force: bool = False
) -> tuple[list[dict], dict[str, Any]]:
    """Screener rows for the approved universe plus snapshot metadata."""
    state = await get_market_state(provider)
    snapshot = await MarketScreener(provider, state["regime"].get("regime")).snapshot(force=force)
    generated_at = snapshot["generated_at"]
    meta = {
        "generated_at": (
            datetime.fromtimestamp(generated_at, tz=timezone.utc).isoformat() if generated_at else None
        ),
        "universe_size": sum(len(v) for v in SECTOR_UNIVERSE.values()),
        "analyzed": len(snapshot["rows"]),
        "errors": snapshot["errors"],
        "regime": state["regime"].get("regime"),
    }
    return snapshot["rows"], meta


def _first_quote(data: Optional[dict]) -> dict:
    """Upstox keys quote payloads by 'EXCHANGE:SYMBOL'; single-instrument calls have one entry."""
    if not data:
        return {}
    return next(iter(data.values()), {}) or {}


def _without_evidence(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in ("evidence", "explanation")}


# ============================================================
# SYSTEM / MARKET STATUS
# ============================================================

@router.get("/system/status")
async def system_status(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Configuration and connectivity status for the settings page and status badges."""
    upstox_connected = False
    if user:
        upstox_connected = await UpstoxAuthService(db).is_connected(user.id)

    analytics = "not_configured"
    if settings.upstox_analytics_token:
        try:
            provider = await get_market_provider(None, db)
            await get_market_state(provider)
            analytics = "valid"
        except UpstoxAPIError as e:
            analytics = "invalid" if e.status_code in (401, 403) else "error"
        except Exception:
            analytics = "error"

    return {
        "analytics_token": analytics,
        "oauth_configured": settings.has_upstox_credentials,
        "user_upstox_connected": upstox_connected,
        "environment": settings.app_env,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/market/status")
async def market_status(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Exchange status plus upcoming trading holidays."""
    provider = await get_market_provider(user, db)
    status, holidays = await asyncio.gather(
        provider.get_market_status("NSE"),
        provider.get_market_holidays(),
        return_exceptions=True,
    )
    today = date.today().isoformat()
    upcoming = []
    if not isinstance(holidays, Exception):
        upcoming = [
            h for h in (holidays.get("data") or [])
            if h.get("date", "") >= today and h.get("holiday_type") == "TRADING_HOLIDAY"
        ][:10]
    return {
        "status": None if isinstance(status, Exception) else status.get("data"),
        "upcoming_holidays": upcoming,
    }


# ============================================================
# MARKET OVERVIEW
# ============================================================

@router.get("/market/overview")
async def market_overview(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Market overview: index quotes, FII/DII flows, market status, regime."""
    provider = await get_market_provider(user, db)
    return await get_market_state(provider)


# ============================================================
# STOCK QUOTES & CANDLES
# ============================================================

@router.get("/stocks/{symbol}/quote")
async def get_stock_quote(
    symbol: str,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Full market quote for a stock, normalised."""
    provider = await get_market_provider(user, db)
    inst = await provider.resolve_instrument(symbol)
    quote = await provider.get_quote(inst["instrument_key"])
    q = _first_quote(quote.get("data"))

    ltp = q.get("last_price")
    net_change = q.get("net_change")
    prev_close = ltp - net_change if ltp is not None and net_change is not None else None

    return {
        "symbol": symbol.upper(),
        "name": inst.get("name"),
        "short_name": inst.get("short_name"),
        "isin": inst.get("isin"),
        "instrument_key": inst["instrument_key"],
        "exchange": inst.get("exchange"),
        "ltp": ltp,
        "change": net_change,
        "change_pct": round(net_change / prev_close * 100, 2) if prev_close else None,
        "prev_close": prev_close,
        "ohlc": q.get("ohlc"),
        "volume": q.get("volume"),
        "average_price": q.get("average_price"),
        "lower_circuit": q.get("lower_circuit_limit"),
        "upper_circuit": q.get("upper_circuit_limit"),
        "depth": q.get("depth"),
        "timestamp": q.get("timestamp"),
        "quote": quote.get("data"),
        "metadata": quote.get("metadata"),
    }


RANGE_DAYS = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "3Y": 1096, "5Y": 1827}


@router.get("/stocks/{symbol}/candles")
async def get_stock_candles(
    symbol: str,
    interval: str = Query("day", pattern="^(1minute|30minute|day|week|month)$"),
    range: Optional[str] = Query(None, pattern="^(1D|1M|3M|6M|1Y|3Y|5Y)$"),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    OHLCV candles in ascending time order.
    Use `range` (1D = today's intraday) or explicit from/to dates.
    """
    provider = await get_market_provider(user, db)
    instrument_key = await provider.resolve_instrument_key(symbol)

    if range == "1D":
        interval = "1minute" if interval not in ("1minute", "30minute") else interval
        candles = await provider.get_intraday_candles(instrument_key, interval)
    elif interval in ("1minute", "30minute") and not from_date and not range:
        candles = await provider.get_intraday_candles(instrument_key, interval)
    else:
        if range and not from_date:
            from_date = (date.today() - timedelta(days=RANGE_DAYS[range])).isoformat()
        candles = await provider.get_historical_candles(instrument_key, interval, to_date, from_date)

    raw = (candles.get("data") or {}).get("candles") or []
    rows = sorted(
        (
            {"time": c[0], "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]}
            for c in raw
        ),
        key=lambda r: r["time"],
    )
    return {
        "symbol": symbol.upper(),
        "instrument_key": instrument_key,
        "interval": interval,
        "range": range,
        "candles": rows,
        "metadata": candles.get("metadata"),
    }


# ============================================================
# STOCK FUNDAMENTALS
# ============================================================

@router.get("/stocks/{symbol}/fundamentals")
async def get_stock_fundamentals(
    symbol: str,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Company profile, ratios, financial statements, shareholding, corporate actions, peers."""
    provider = await get_market_provider(user, db)
    inst = await provider.resolve_instrument(symbol)
    isin = inst.get("isin")
    if not isin:
        raise HTTPException(status_code=404, detail=f"No ISIN available for {symbol.upper()}.")

    parts = {
        "profile": provider.get_company_profile(isin),
        "key_ratios": provider.get_key_ratios(isin),
        "income_statement": provider.get_income_statement(isin),
        "balance_sheet": provider.get_balance_sheet(isin),
        "cash_flow": provider.get_cash_flow(isin),
        "shareholding": provider.get_shareholding(isin),
        "corporate_actions": provider.get_corporate_actions(isin),
        "competitors": provider.get_competitors(inst["instrument_key"]),
    }
    results = await asyncio.gather(*parts.values(), return_exceptions=True)

    out: dict[str, Any] = {"symbol": symbol.upper(), "isin": isin, "name": inst.get("name"), "unavailable": []}
    for name, result in zip(parts, results):
        if isinstance(result, Exception):
            out[name] = None
            out["unavailable"].append(name)
        else:
            out[name] = result.get("data")
    out["metadata"] = {
        "source": "upstox_fundamentals",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return out


# ============================================================
# NEWS
# ============================================================

def _normalise_news(data: Optional[dict], symbol_by_key: dict[str, str]) -> list[dict]:
    items: dict[str, dict] = {}
    for key, articles in (data or {}).items():
        for a in articles or []:
            link = a.get("article_link") or a.get("heading")
            entry = items.setdefault(link, {
                "heading": a.get("heading"),
                "summary": a.get("summary"),
                "thumbnail": a.get("thumbnail"),
                "url": a.get("article_link"),
                "published_at": (
                    datetime.fromtimestamp(a["published_time"] / 1000, tz=timezone.utc).isoformat()
                    if a.get("published_time") else None
                ),
                "symbols": [],
                "source": "Upstox",
            })
            sym = symbol_by_key.get(key)
            if sym and sym not in entry["symbols"]:
                entry["symbols"].append(sym)
    return sorted(items.values(), key=lambda n: n["published_at"] or "", reverse=True)


@router.get("/stocks/{symbol}/news")
async def get_stock_news(
    symbol: str,
    page: int = Query(1, ge=1),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """News articles for a stock. Never fabricates news."""
    provider = await get_market_provider(user, db)
    instrument_key = await provider.resolve_instrument_key(symbol)
    news = await provider.get_news(instrument_keys=[instrument_key], page=page)
    return {
        "symbol": symbol.upper(),
        "news": _normalise_news(news.get("data"), {instrument_key: symbol.upper()}),
        "metadata": news.get("metadata"),
    }


@router.get("/market/news")
async def get_market_news(
    sector: Optional[str] = None,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated news across the approved universe (optionally one sector)."""
    provider = await get_market_provider(user, db)
    rows, _ = await get_screener_rows(provider)
    if sector:
        rows = [r for r in rows if r["sector"] == sector]
    symbol_by_key = {r["instrument_key"]: r["symbol"] for r in rows}
    keys = list(symbol_by_key)

    # Upstox accepts up to 30 instrument keys per news request
    batches = [keys[i:i + 30] for i in range(0, len(keys), 30)]
    results = await asyncio.gather(
        *(provider.get_news(instrument_keys=b) for b in batches), return_exceptions=True
    )
    merged: dict[str, list] = {}
    for result in results:
        if not isinstance(result, Exception):
            for key, articles in (result.get("data") or {}).items():
                merged.setdefault(key, []).extend(articles or [])

    news = _normalise_news(merged, symbol_by_key)
    sector_by_symbol = {r["symbol"]: r["sector"] for r in rows}
    for item in news:
        item["sectors"] = sorted({sector_by_symbol[s] for s in item["symbols"] if s in sector_by_symbol})
    return {
        "news": news,
        "sector": sector,
        "metadata": {"source": "upstox_news", "timestamp": datetime.now(timezone.utc).isoformat()},
    }


# ============================================================
# PREDICTION
# ============================================================

@router.get("/stocks/{symbol}/prediction")
async def get_stock_prediction(
    symbol: str,
    horizon: str = Query("1D", pattern="^(1D|3D|5D|10D|20D)$"),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ML prediction for a stock: probabilities, confidence intervals, explanations.
    Never returns a deterministic future price.
    """
    import pandas as pd
    from app.services.analytics.features import FeatureEngine
    from app.services.ml.prediction_engine import EnsemblePredictionEngine

    provider = await get_market_provider(user, db)
    instrument_key = await provider.resolve_instrument_key(symbol)
    candles = await provider.get_historical_candles(instrument_key, "day")
    candle_list = (candles.get("data") or {}).get("candles") or []

    if len(candle_list) < 50:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Insufficient historical data for reliable prediction "
                f"({len(candle_list)} candles). Need at least 50."
            ),
        )

    df = pd.DataFrame(candle_list, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = FeatureEngine.compute_all_features(df.sort_values("timestamp").reset_index(drop=True))

    latest = df.iloc[-1].to_dict()
    latest["instrument_key"] = instrument_key
    latest["symbol"] = symbol.upper()

    return EnsemblePredictionEngine().predict(latest, horizon=horizon).to_dict()


# ============================================================
# SCANNER
# ============================================================

@router.get("/market/scanner")
async def market_scanner(
    sector: Optional[str] = None,
    bucket: Optional[str] = None,
    entry: Optional[str] = None,
    q: Optional[str] = None,
    min_volume_ratio: float = Query(0, ge=0),
    min_rsi: float = Query(0, ge=0, le=100),
    max_rsi: float = Query(100, ge=0, le=100),
    min_change: Optional[float] = None,
    max_change: Optional[float] = None,
    sort_by: str = "change_pct",
    order: str = Query("desc", pattern="^(asc|desc)$"),
    refresh: bool = False,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Scan the approved sector universe with technical, volume and signal filters."""
    if sort_by not in SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"sort_by must be one of {sorted(SORT_FIELDS)}")

    provider = await get_market_provider(user, db)
    rows, meta = await get_screener_rows(provider, force=refresh)

    def keep(r: dict) -> bool:
        if sector and r["sector"] != sector:
            return False
        if bucket and bucket not in r["buckets"]:
            return False
        if entry and r["entry"] != entry:
            return False
        if q and q.upper() not in r["symbol"] and q.lower() not in (r["name"] or "").lower():
            return False
        if min_volume_ratio and (r["volume_ratio"] or 0) < min_volume_ratio:
            return False
        rsi = r["rsi"]
        if (min_rsi > 0 or max_rsi < 100) and (rsi is None or not min_rsi <= rsi <= max_rsi):
            return False
        chg = r["change_pct"]
        if min_change is not None and (chg is None or chg < min_change):
            return False
        if max_change is not None and (chg is None or chg > max_change):
            return False
        return True

    filtered = [_without_evidence(r) for r in rows if keep(r)]
    present = [r for r in filtered if r.get(sort_by) is not None]
    missing = [r for r in filtered if r.get(sort_by) is None]
    present.sort(key=lambda r: r[sort_by], reverse=(order == "desc"))

    return {
        "results": present + missing,
        "total": len(filtered),
        "filters": {
            "sector": sector, "bucket": bucket, "entry": entry, "q": q,
            "min_volume_ratio": min_volume_ratio, "rsi_range": [min_rsi, max_rsi],
            "change_range": [min_change, max_change], "sort_by": sort_by, "order": order,
        },
        "options": {
            "sectors": list(SECTOR_UNIVERSE),
            "buckets": BUCKETS,
            "entries": ENTRY_TYPES,
            "sort_fields": sorted(SORT_FIELDS),
        },
        "metadata": meta,
    }


# ============================================================
# SECTORS & MOVERS
# ============================================================

@router.get("/market/sectors")
async def market_sectors(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-sector performance, breadth and constituent stocks."""
    provider = await get_market_provider(user, db)
    rows, meta = await get_screener_rows(provider)
    summary = sector_summary(rows)
    for s in summary:
        s["constituents"] = sorted(
            (_without_evidence(r) for r in rows if r["sector"] == s["sector"]),
            key=lambda r: r["change_pct"] if r["change_pct"] is not None else -999,
            reverse=True,
        )
    return {"sectors": summary, "metadata": meta}


@router.get("/market/movers")
async def market_movers(
    limit: int = Query(5, ge=1, le=20),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Top gainers, losers, volume shockers and market breadth across the universe."""
    provider = await get_market_provider(user, db)
    rows, meta = await get_screener_rows(provider)
    priced = [_without_evidence(r) for r in rows if r["change_pct"] is not None]
    by_change = sorted(priced, key=lambda r: r["change_pct"], reverse=True)
    by_volume = sorted(
        (r for r in priced if r["volume_ratio"] is not None),
        key=lambda r: r["volume_ratio"],
        reverse=True,
    )
    return {
        "gainers": [r for r in by_change if r["change_pct"] > 0][:limit],
        "losers": [r for r in reversed(by_change) if r["change_pct"] < 0][:limit],
        "volume_shockers": by_volume[:limit],
        "breadth": {
            "advances": sum(1 for r in priced if r["change_pct"] > 0),
            "declines": sum(1 for r in priced if r["change_pct"] < 0),
            "unchanged": sum(1 for r in priced if r["change_pct"] == 0),
            "above_200dma": sum(1 for r in rows if r["sma_200"] and r["ltp"] and r["ltp"] > r["sma_200"]),
            "total": len(rows),
        },
        "metadata": meta,
    }


# ============================================================
# INSTRUMENT SEARCH
# ============================================================

@router.get("/instruments/search")
async def search_instruments(
    query: str = Query(..., min_length=1),
    exchange: Optional[str] = "NSE",
    instrument_type: Optional[str] = "EQ",
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Search instruments by name, symbol or ISIN (NSE equities by default)."""
    provider = await get_market_provider(user, db)
    results = await provider.search_instruments(
        query, instrument_type=instrument_type, exchange=exchange, page_size=10
    )
    return {
        "results": [
            {
                "symbol": i.get("trading_symbol"),
                "name": i.get("name"),
                "short_name": i.get("short_name"),
                "exchange": i.get("exchange"),
                "isin": i.get("isin"),
                "instrument_key": i.get("instrument_key"),
            }
            for i in (results.get("data") or [])
            if i.get("segment") == "NSE_EQ" or exchange != "NSE"
        ]
    }
