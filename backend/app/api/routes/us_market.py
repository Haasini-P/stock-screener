"""
StockMind AI — US Market Routes
Quote/candles/news are real when an Alpaca key is configured (Settings ->
Broker API Credentials), honest "not configured"/"not available" otherwise —
see app/services/us_market/provider.py. Fundamentals are SEC EDGAR-backed
(free, no key, always on). /analyze mirrors /api/signals/analyze/{symbol}'s
shape for US tickers. No scanner/screener/batch-AI for US in this round.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_optional_user
from app.database import get_db
from app.models.user import User
from app.services.ai.commentary_service import CommentaryError
from app.services.ai.us_commentary_service import generate_us_research, list_recent_research
from app.services.us_market.analysis import analyze_us_stock
from app.services.us_market.fx import get_usd_inr_rate
from app.services.us_market.indices import get_us_indices_history, get_us_indices_latest
from app.services.us_market.movers import compute_us_movers
from app.services.us_market.provider import USDataUnavailableError, get_alpaca_client, get_us_provider
from app.services.us_market.scanner import run_us_scanner
from app.services.us_market.sec_compaction import compact_fundamentals
from app.services.us_market.sec_edgar_client import get_company_facts
from app.services.us_market.universe import US_STOCK_UNIVERSE

router = APIRouter(prefix="/api/us", tags=["US Market"])


@router.get("/universe")
async def us_universe():
    """Sector-keyed list of approved US tickers — used for the frontend's symbol
    picker since there's no live instrument search for US stocks."""
    return {"universe": US_STOCK_UNIVERSE}


@router.get("/stocks/{symbol}/quote")
async def us_quote(symbol: str, db: AsyncSession = Depends(get_db)):
    """Resolves the symbol (404 if not in the approved universe) and reports
    the live quote when Alpaca is configured, or plainly why not — never a
    500 for "no data"."""
    provider = await get_us_provider(db)
    try:
        inst = await provider.resolve_instrument(symbol)
    except USDataUnavailableError as e:
        raise HTTPException(status_code=404, detail=str(e))

    quote = await provider.get_quote(inst["instrument_key"])
    return {**inst, **quote}


@router.get("/stocks/{symbol}/candles")
async def us_candles(
    symbol: str, range: str = Query(default="6M"), interval: str = Query(default="day"),
    db: AsyncSession = Depends(get_db),
):
    """Same row shape CandlestickChart.tsx already renders: {time,open,high,low,close,volume}."""
    provider = await get_us_provider(db)
    try:
        inst = await provider.resolve_instrument(symbol)
    except USDataUnavailableError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = await provider.get_historical_candles(inst["instrument_key"], interval)
    rows = sorted(
        (
            {"time": c[0], "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]}
            for c in result.get("candles", [])
        ),
        key=lambda r: r["time"],
    )
    return {
        "symbol": inst["symbol"], "instrument_key": inst["instrument_key"], "interval": interval, "range": range,
        "candles": rows, "data_available": result.get("data_available", False), "reason": result.get("reason"),
    }


@router.get("/stocks/{symbol}/fundamentals")
async def us_fundamentals(symbol: str, db: AsyncSession = Depends(get_db)):
    """SEC EDGAR-backed (free, no key, always on regardless of Alpaca config)."""
    provider = await get_us_provider(db)
    try:
        inst = await provider.resolve_instrument(symbol)
    except USDataUnavailableError as e:
        raise HTTPException(status_code=404, detail=str(e))

    facts = await get_company_facts(inst["symbol"])
    if facts is None:
        return {"data_available": False, "reason": "No SEC EDGAR filings found for this ticker."}
    return {"data_available": True, "source": "sec_edgar", **compact_fundamentals(facts)}


@router.get("/stocks/{symbol}/news")
async def us_news(symbol: str, db: AsyncSession = Depends(get_db)):
    provider = await get_us_provider(db)
    try:
        inst = await provider.resolve_instrument(symbol)
    except USDataUnavailableError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await provider.get_news(instrument_keys=[inst["instrument_key"]])


@router.get("/stocks/{symbol}/analyze")
async def us_analyze(
    symbol: str, user: Optional[User] = Depends(get_optional_user), db: AsyncSession = Depends(get_db),
):
    """Full technical analysis (signal, multi-horizon predictions, trade plan) —
    see analyze_us_stock(). Returns data_available:false cleanly, never a 500,
    when Alpaca isn't configured or this symbol's history is too short."""
    provider = await get_us_provider(db)
    try:
        return await analyze_us_stock(provider, symbol, user, db)
    except USDataUnavailableError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stocks/{symbol}/research")
async def us_research(symbol: str, user: Optional[User] = Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    """Generate (or return cached) AI notes for a US symbol — a full
    institutional-grade take when real Alpaca+SEC data is available for this
    symbol, otherwise the GENERAL_KNOWLEDGE fallback. See us_commentary_service.py."""
    try:
        return await generate_us_research(db, user, symbol)
    except CommentaryError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/fx-rate")
async def fx_rate():
    """Real USD->INR rate (ECB reference, via Frankfurter, hourly-cached) —
    for showing paper-trading amounts in both currencies. Never a guessed rate."""
    return await get_usd_inr_rate()


@router.get("/movers")
async def us_movers(db: AsyncSession = Depends(get_db)):
    """Gainers/losers/most-active across the approved US universe, ranked from
    one Alpaca multi-symbol snapshot call. Honest data_available:false when
    Alpaca isn't configured — never a 500."""
    return await compute_us_movers(await get_alpaca_client(db))


@router.get("/indices/latest")
async def us_indices_latest(db: AsyncSession = Depends(get_db)):
    """S&P 500/Nasdaq 100/Dow Jones via their SPY/QQQ/DIA ETF proxies — Alpaca
    has no direct index quote. For the Dashboard ticker strip."""
    return await get_us_indices_latest(await get_alpaca_client(db))


@router.get("/indices/history")
async def us_indices_history(range: str = Query(default="1M"), db: AsyncSession = Depends(get_db)):
    """Daily-bar history for the same three proxies, normalized to % change
    from the first point in range. For the Dashboard Market Overview chart."""
    return await get_us_indices_history(await get_alpaca_client(db), range)


@router.get("/research/recent")
async def us_research_recent(limit: int = Query(default=5, ge=1, le=20), db: AsyncSession = Depends(get_db)):
    """Most recently generated AI research notes, one per distinct symbol —
    for the Dashboard's "Recent US Analysis" panel."""
    return {"items": await list_recent_research(db, limit)}


@router.get("/scanner")
async def us_scanner(user: Optional[User] = Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    """Technical scan across the default US watchlist, favorable setups
    first. Never places an order — Buy/Sell on the frontend opens the
    existing paper-order dialog pre-filled, same confirm-before-acting
    pattern as everywhere else in this app."""
    provider = await get_us_provider(db)
    return await run_us_scanner(provider, user, db)
