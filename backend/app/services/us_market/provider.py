"""
StockMind AI — US Market Data Provider (placeholder / future swap point)

No real US-equity data source is wired in yet. Upstox's public developer API
(confirmed against its live announcements page, Oct 2026) has zero individual
US-equity endpoints — it covers NSE/BSE/MCX plus a handful of global INDEX
quotes (Dow Jones, S&P, FTSE) for display only. Upstox's own consumer app does
offer US stock investing, but that's powered by a separate partnership with
Alpaca, not exposed via Upstox's public API.

This class exists so the rest of the US feature (routes, and eventually
FeatureEngine/SignalEngine once real candles exist) can be built against a
stable interface today. Every data method returns a clear
{"data_available": False, "reason": ...} shape instead of fabricating
numbers — this app's core rule (never fabricate) applies here too.

TO ADD A REAL PROVIDER LATER: implement the method bodies below against a
real vendor (Alpaca, Polygon, IEX, etc.), keep the return shapes compatible
with what app/services/upstox/provider.py's UpstoxDataProvider returns for
quote/get_historical_candles, and FeatureEngine.compute_all_features /
SignalEngine.generate_signal need no changes at all — this is the single
swap point.
"""

from typing import Optional

from app.services.us_market.universe import US_STOCK_UNIVERSE, us_symbol_sector_lookup

_SECTOR_LOOKUP = us_symbol_sector_lookup()

_NOT_AVAILABLE_REASON = (
    "Upstox's public API does not provide individual US equity data "
    "(quotes, candles, fundamentals, or order execution) — only Indian "
    "exchanges and a few global index quotes. This will populate once a "
    "real US market data provider is connected."
)


class USDataUnavailableError(Exception):
    """Raised only for a genuine error (symbol not in the approved universe) —
    never for "no live data", which is a known, expected state returned as
    {"data_available": False, ...} instead of an exception."""


def _not_available(**extra) -> dict:
    return {"data_available": False, "reason": _NOT_AVAILABLE_REASON, **extra}


class USMarketProvider:
    """Mirrors UpstoxDataProvider's method names so call sites and a future
    real implementation both stay familiar — see module docstring."""

    def __init__(self, access_token: Optional[str] = None):
        self._access_token = access_token  # unused today; kept for interface parity

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

    async def get_quote(self, instrument_key: str) -> dict:
        return _not_available(instrument_key=instrument_key)

    async def get_historical_candles(
        self, instrument_key: str, interval: str = "day",
        from_date: Optional[str] = None, to_date: Optional[str] = None,
    ) -> dict:
        return _not_available(instrument_key=instrument_key, candles=[])

    async def get_news(self, instrument_keys: Optional[list[str]] = None, **kwargs) -> dict:
        return _not_available(news=[])

    async def get_company_profile(self, symbol: str) -> dict:
        return _not_available()

    async def get_key_ratios(self, symbol: str) -> dict:
        return _not_available()

    async def get_shareholding(self, symbol: str) -> dict:
        return _not_available()

    async def get_corporate_actions(self, symbol: str) -> dict:
        return _not_available()

    async def get_competitors(self, symbol: str) -> dict:
        return _not_available()


def get_us_provider() -> USMarketProvider:
    """No credentials needed today (see class docstring) — kept as a function,
    not a plain constant, so a future real provider can thread a stored API
    key through without changing call sites."""
    return USMarketProvider()
