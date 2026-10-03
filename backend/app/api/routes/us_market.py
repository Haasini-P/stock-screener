"""
StockMind AI — US Market Routes
Covers the approved US ticker universe, an honest "is live data available"
status check (see app/services/us_market/provider.py), and AI Research Notes.
No scanner/screener, no batch AI, and no real market data for this round —
see the US Stocks plan for why.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ai.commentary_service import CommentaryError
from app.services.ai.us_commentary_service import generate_us_research
from app.services.us_market.provider import USDataUnavailableError, get_us_provider
from app.services.us_market.universe import US_STOCK_UNIVERSE

router = APIRouter(prefix="/api/us", tags=["US Market"])


@router.get("/universe")
async def us_universe():
    """Sector-keyed list of approved US tickers — used for the frontend's symbol
    picker since there's no live instrument search for US stocks."""
    return {"universe": US_STOCK_UNIVERSE}


@router.get("/stocks/{symbol}/quote-status")
async def us_quote_status(symbol: str):
    """Resolves the symbol (404 if not in the approved universe) and reports
    plainly whether live data is available for it — never a 500 for "no data"."""
    provider = get_us_provider()
    try:
        inst = await provider.resolve_instrument(symbol)
    except USDataUnavailableError as e:
        raise HTTPException(status_code=404, detail=str(e))

    quote = await provider.get_quote(inst["instrument_key"])
    return {**inst, **quote}


@router.get("/stocks/{symbol}/research")
async def us_research(symbol: str, db: AsyncSession = Depends(get_db)):
    """Generate (or return cached) AI Research Notes for a US symbol — see
    us_commentary_service.py. Always labeled GENERAL_KNOWLEDGE, never live data."""
    try:
        return await generate_us_research(db, symbol)
    except CommentaryError as e:
        raise HTTPException(status_code=422, detail=str(e))
