"""
StockMind AI — US Market Data Provider
Quotes/candles/news are now backed by Alpaca Markets (free tier — 15-min-delayed
IEX data, no KYC, app.alpaca.markets/signup) once the user adds an API key+secret
in Settings → Broker API Credentials. Fundamentals come from SEC EDGAR (free,
no key — see sec_edgar_client.py) via a separate path, not through this class
(XBRL data doesn't map onto Upstox-shaped key_ratios/shareholding fields).

Until a key is added, or if a specific Alpaca call fails, every method returns
the same honest {"data_available": False, "reason": ...} shape it always has —
this app's core rule (never fabricate) applies here too. Alpaca is market data
only, never order execution — the US paper-trading ledger
(app/services/paper_trading.py) remains the system of record for trades.
"""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.broker_config import get_credentials
from app.services.us_market.alpaca_client import AlpacaAPIError, AlpacaClient
from app.services.us_market.universe import us_symbol_sector_lookup

_SECTOR_LOOKUP = us_symbol_sector_lookup()

_NOT_CONFIGURED_REASON = (
    "No Alpaca API key configured — add a free key (no KYC needed) in "
    "Settings → Broker API Credentials to see live US quotes, charts and news."
)


class USDataUnavailableError(Exception):
    """Raised only for a genuine error (symbol not in the approved universe) —
    never for "no live data", which is a known, expected state returned as
    {"data_available": False, ...} instead of an exception."""


def _not_available(reason: str = _NOT_CONFIGURED_REASON, **extra) -> dict:
    return {"data_available": False, "reason": reason, **extra}


class USMarketProvider:
    """Mirrors UpstoxDataProvider's method names so call sites stay familiar.
    `alpaca` is None when no key is configured — every method degrades to the
    honest "not available" shape in that case."""

    def __init__(self, alpaca: Optional[AlpacaClient] = None):
        self._alpaca = alpaca

    async def resolve_instrument(self, symbol: str) -> dict:
        symbol = symbol.strip().upper()
        sector = _SECTOR_LOOKUP.get(symbol)
        if not sector:
            raise USDataUnavailableError(
                f"'{symbol}' is not in StockMind's approved US stock list yet. "
                f"Approved symbols: {', '.join(sorted(_SECTOR_LOOKUP))}."
            )
        return {
            "symbol": symbol,
            "name": symbol,  # no name-resolution source yet — ticker doubles as display name
            "sector": sector,
            "instrument_key": f"US_EQ|{symbol}",  # locally synthesized — no real Upstox instrument backs this
        }

    @staticmethod
    def _symbol_from_key(instrument_key: str) -> str:
        return instrument_key.split("|")[-1]

    async def get_quote(self, instrument_key: str) -> dict:
        if not self._alpaca:
            return _not_available(instrument_key=instrument_key)
        symbol = self._symbol_from_key(instrument_key)
        try:
            snap = await self._alpaca.get_snapshot(symbol)
        except AlpacaAPIError as e:
            return _not_available(reason=str(e), instrument_key=instrument_key)

        trade = snap.get("latestTrade") or {}
        daily = snap.get("dailyBar") or {}
        prev = snap.get("prevDailyBar") or {}
        ltp = trade.get("p") if trade.get("p") is not None else daily.get("c")
        prev_close = prev.get("c")
        change = (ltp - prev_close) if (ltp is not None and prev_close is not None) else None
        change_pct = round(change / prev_close * 100, 2) if change is not None and prev_close else None

        return {
            "data_available": True,
            "instrument_key": instrument_key,
            "ltp": ltp,
            "change": change,
            "change_pct": change_pct,
            "prev_close": prev_close,
            "ohlc": {"open": daily.get("o"), "high": daily.get("h"), "low": daily.get("l"), "close": daily.get("c")},
            "volume": daily.get("v"),
            "timestamp": trade.get("t") or daily.get("t"),
            "source": "alpaca",
            "feed_note": "IEX feed via Alpaca's free tier — approximately 15 minutes delayed.",
        }

    async def get_historical_candles(
        self, instrument_key: str, interval: str = "day",
        from_date: Optional[str] = None, to_date: Optional[str] = None,
    ) -> dict:
        if not self._alpaca:
            return _not_available(instrument_key=instrument_key, candles=[])
        symbol = self._symbol_from_key(instrument_key)
        start = from_date or (date.today() - timedelta(days=450)).isoformat()
        end = to_date or date.today().isoformat()
        try:
            bars = await self._alpaca.get_daily_bars(symbol, start, end)
        except AlpacaAPIError as e:
            return _not_available(reason=str(e), instrument_key=instrument_key, candles=[])

        # 7-column shape (timestamp, o, h, l, c, v, oi) matches what FeatureEngine's
        # candle-DataFrame construction expects elsewhere in this app — oi (open
        # interest) doesn't apply to equities, kept as 0 for column-count parity.
        candles = [[b["t"], b["o"], b["h"], b["l"], b["c"], b["v"], 0] for b in bars]
        return {"data_available": True, "instrument_key": instrument_key, "candles": candles, "source": "alpaca"}

    async def get_news(self, instrument_keys: Optional[list[str]] = None, **kwargs) -> dict:
        if not self._alpaca or not instrument_keys:
            return _not_available(news=[])
        symbol = self._symbol_from_key(instrument_keys[0])
        try:
            raw_news = await self._alpaca.get_news(symbol)
        except AlpacaAPIError as e:
            return _not_available(reason=str(e), news=[])

        news = [
            {"heading": n.get("headline"), "published_at": n.get("created_at"), "url": n.get("url"), "source": n.get("source")}
            for n in raw_news
        ]
        return {"data_available": True, "news": news, "source": "alpaca (Benzinga)"}

    # No Alpaca equivalent — fundamentals are served via SEC EDGAR (see
    # sec_edgar_client.py / sec_compaction.py), not through this class.
    async def get_company_profile(self, symbol: str) -> dict:
        return _not_available(reason="See /api/us/stocks/{symbol}/fundamentals (SEC EDGAR) instead.")

    async def get_key_ratios(self, symbol: str) -> dict:
        return _not_available(reason="See /api/us/stocks/{symbol}/fundamentals (SEC EDGAR) instead.")

    async def get_shareholding(self, symbol: str) -> dict:
        return _not_available(reason="Not tracked by SEC EDGAR's XBRL facts.")

    async def get_corporate_actions(self, symbol: str) -> dict:
        return _not_available(reason="Not available from SEC EDGAR's XBRL facts.")

    async def get_competitors(self, symbol: str) -> dict:
        return _not_available(reason="No peer-comparison data source configured for US stocks yet.")


async def get_us_provider(db: AsyncSession) -> USMarketProvider:
    """Attaches a real AlpacaClient only when a key is stored (Settings ->
    Broker API Credentials) or set via ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY —
    otherwise every call degrades to the honest "not configured" shape."""
    creds = await get_credentials(db, "alpaca")
    if not creds["configured"]:
        return USMarketProvider()
    return USMarketProvider(alpaca=AlpacaClient(creds["client_id"], creds["client_secret"]))
