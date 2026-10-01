"""
StockMind AI — Upstox Data Provider
Central abstraction over all Upstox REST APIs.
Every market-data-dependent component obtains data through this provider.
"""

from datetime import datetime, date
from typing import Any, Optional

from app.core.logging import get_logger
from app.services.upstox.client import (
    UpstoxClient,
    UpstoxDataUnavailableError,
)

logger = get_logger(__name__)

# Symbol -> instrument record; stable, so cached for the process lifetime
_instrument_cache: dict[str, dict[str, Any]] = {}


class UpstoxDataProvider:
    """
    Unified interface for all Upstox API data retrieval.

    Design principles:
    - Every method returns structured data or raises UpstoxDataUnavailableError
    - No data fabrication — if API fails, the error is surfaced
    - All responses include data freshness metadata
    - Methods are composable for higher-level analytics
    """

    def __init__(self, access_token: Optional[str] = None):
        self._client = UpstoxClient(access_token=access_token)
        self._access_token = access_token

    def with_token(self, access_token: str) -> "UpstoxDataProvider":
        """Return a new provider instance with the given access token."""
        return UpstoxDataProvider(access_token=access_token)

    # ================================================================
    # INSTRUMENTS
    # ================================================================

    async def search_instruments(
        self,
        query: str,
        instrument_type: Optional[str] = None,
        exchange: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Search instruments by name, symbol, or ISIN."""
        params = {"query": query, "page": page, "page_size": page_size}
        if instrument_type:
            params["instrument_type"] = instrument_type
        if exchange:
            params["exchange"] = exchange

        response = await self._client.get("/v2/instruments/search", params=params)
        return self._wrap_response(response, "instruments_search")

    async def resolve_instrument(self, symbol: str, segment: str = "NSE_EQ") -> dict[str, Any]:
        """
        Resolve a trading symbol (e.g. RELIANCE) to its Upstox instrument record
        (instrument_key, isin, name, ...). Upstox rejects symbol-based keys like
        NSE_EQ|RELIANCE — equity keys must use the ISIN.
        """
        symbol = symbol.upper().strip()
        cache_key = f"{segment}:{symbol}"
        if cache_key in _instrument_cache:
            return _instrument_cache[cache_key]

        exchange = segment.split("_")[0]
        search = await self.search_instruments(
            symbol, instrument_type="EQ", exchange=exchange, page_size=30
        )
        for inst in search.get("data") or []:
            if (
                inst.get("segment") == segment
                and (inst.get("trading_symbol") or "").upper() == symbol
            ):
                _instrument_cache[cache_key] = inst
                return inst

        raise UpstoxDataUnavailableError(
            f"Could not resolve instrument key for symbol '{symbol}' on {segment}"
        )

    async def resolve_instrument_key(self, symbol: str, segment: str = "NSE_EQ") -> str:
        """Resolve a trading symbol to an Upstox instrument key (NSE_EQ|<ISIN>)."""
        if "|" in symbol:
            return symbol  # already an instrument key
        return (await self.resolve_instrument(symbol, segment))["instrument_key"]

    # ================================================================
    # MARKET QUOTES
    # ================================================================

    async def get_quote(self, instrument_key: str) -> dict[str, Any]:
        """Get full market quote for a single instrument."""
        response = await self._client.get(
            "/v2/market-quote/quotes",
            params={"instrument_key": instrument_key},
        )
        return self._wrap_response(response, "market_quote")

    async def get_quotes(self, instrument_keys: list[str]) -> dict[str, Any]:
        """Get full market quotes for multiple instruments (max 500)."""
        keys = ",".join(instrument_keys[:500])
        response = await self._client.get(
            "/v2/market-quote/quotes",
            params={"instrument_key": keys},
        )
        return self._wrap_response(response, "market_quotes")

    async def get_ltp(self, instrument_keys: list[str]) -> dict[str, Any]:
        """Get Last Traded Price for multiple instruments."""
        keys = ",".join(instrument_keys[:500])
        response = await self._client.get(
            "/v2/market-quote/ltp",
            params={"instrument_key": keys},
        )
        return self._wrap_response(response, "ltp")

    async def get_ohlc(self, instrument_keys: list[str], interval: str = "1d") -> dict[str, Any]:
        """Get OHLC quotes for multiple instruments."""
        keys = ",".join(instrument_keys[:500])
        response = await self._client.get(
            "/v2/market-quote/ohlc",
            params={"instrument_key": keys, "interval": interval},
        )
        return self._wrap_response(response, "ohlc")

    async def get_full_quote_v3(self, instrument_keys: list[str]) -> dict[str, Any]:
        """Get V3 full quotes with CAS data."""
        keys = ",".join(instrument_keys[:500])
        response = await self._client.get(
            "/v3/market-quote/quotes",
            params={"instrument_key": keys},
        )
        return self._wrap_response(response, "full_quote_v3")

    # ================================================================
    # HISTORICAL CANDLES
    # ================================================================

    async def get_historical_candles(
        self,
        instrument_key: str,
        interval: str = "day",
        to_date: Optional[str] = None,
        from_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get historical OHLCV candle data.

        Args:
            instrument_key: Upstox instrument key
            interval: 1minute, 30minute, day, week, month
            to_date: End date (YYYY-MM-DD)
            from_date: Start date (YYYY-MM-DD)
        """
        if to_date is None:
            to_date = date.today().isoformat()

        path = f"/v2/historical-candle/{instrument_key}/{interval}/{to_date}"
        if from_date:
            path += f"/{from_date}"

        response = await self._client.get(path)
        return self._wrap_response(response, "historical_candles")

    async def get_intraday_candles(
        self,
        instrument_key: str,
        interval: str = "1minute",
    ) -> dict[str, Any]:
        """Get intraday candle data for current trading day."""
        path = f"/v2/historical-candle/intraday/{instrument_key}/{interval}"
        response = await self._client.get(path)
        return self._wrap_response(response, "intraday_candles")

    async def get_historical_candles_v3(
        self,
        instrument_key: str,
        interval: str = "day",
        to_date: Optional[str] = None,
        from_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """V3 historical candles with expanded intervals."""
        if to_date is None:
            to_date = date.today().isoformat()
        path = f"/v3/historical-candle/{instrument_key}/{interval}/{to_date}"
        if from_date:
            path += f"/{from_date}"
        response = await self._client.get(path)
        return self._wrap_response(response, "historical_candles_v3")

    # ================================================================
    # PORTFOLIO
    # ================================================================

    async def get_holdings(self) -> dict[str, Any]:
        """Get user's long-term portfolio holdings."""
        response = await self._client.get("/v2/portfolio/long-term-holdings")
        return self._wrap_response(response, "holdings")

    async def get_positions(self) -> dict[str, Any]:
        """Get user's short-term/intraday positions."""
        response = await self._client.get("/v2/portfolio/short-term-positions")
        return self._wrap_response(response, "positions")

    async def get_mtf_positions(self) -> dict[str, Any]:
        """Get Margin Trading Facility positions."""
        response = await self._client.get("/v3/portfolio/mtf-positions")
        return self._wrap_response(response, "mtf_positions")

    async def get_pnl(
        self,
        from_date: str,
        to_date: str,
        segment: str = "EQ",
    ) -> dict[str, Any]:
        """Get trade-wise profit and loss report."""
        response = await self._client.get(
            "/v2/trade/profit-and-loss/data",
            params={
                "from_date": from_date,
                "to_date": to_date,
                "segment": segment,
            },
        )
        return self._wrap_response(response, "pnl")

    async def get_pnl_metadata(
        self,
        from_date: str,
        to_date: str,
        segment: str = "EQ",
    ) -> dict[str, Any]:
        """Get P&L report metadata."""
        response = await self._client.get(
            "/v2/trade/profit-and-loss/metadata",
            params={
                "from_date": from_date,
                "to_date": to_date,
                "segment": segment,
            },
        )
        return self._wrap_response(response, "pnl_metadata")

    async def get_funds_and_margin(self, segment: str = "SEC") -> dict[str, Any]:
        """Get fund balance and margin details."""
        response = await self._client.get(
            "/v2/user/get-funds-and-margin",
            params={"segment": segment},
        )
        return self._wrap_response(response, "funds_margin")

    # ================================================================
    # FUNDAMENTALS
    # ================================================================

    async def get_company_profile(self, isin: str) -> dict[str, Any]:
        """Get company profile (sector, description, market cap)."""
        response = await self._client.get(f"/v2/fundamentals/{isin}/profile")
        return self._wrap_response(response, "company_profile")

    async def get_income_statement(
        self,
        isin: str,
        period: str = "annual",
    ) -> dict[str, Any]:
        """Get income statement data."""
        response = await self._client.get(
            f"/v2/fundamentals/{isin}/income-statement",
            params={"period": period},
        )
        return self._wrap_response(response, "income_statement")

    async def get_balance_sheet(
        self,
        isin: str,
        period: str = "annual",
    ) -> dict[str, Any]:
        """Get balance sheet data."""
        response = await self._client.get(
            f"/v2/fundamentals/{isin}/balance-sheet",
            params={"period": period},
        )
        return self._wrap_response(response, "balance_sheet")

    async def get_cash_flow(
        self,
        isin: str,
        period: str = "annual",
    ) -> dict[str, Any]:
        """Get cash flow statement."""
        response = await self._client.get(
            f"/v2/fundamentals/{isin}/cash-flow",
            params={"period": period},
        )
        return self._wrap_response(response, "cash_flow")

    async def get_key_ratios(self, isin: str) -> dict[str, Any]:
        """Get key financial ratios (PE, PB, ROE, ROCE, etc.)."""
        response = await self._client.get(f"/v2/fundamentals/{isin}/key-ratios")
        return self._wrap_response(response, "key_ratios")

    async def get_shareholding(self, isin: str) -> dict[str, Any]:
        """Get shareholding pattern (promoter, FII, DII, public)."""
        response = await self._client.get(f"/v2/fundamentals/{isin}/share-holdings")
        return self._wrap_response(response, "shareholding")

    async def get_corporate_actions(self, isin: str) -> dict[str, Any]:
        """Get corporate actions (dividends, splits, bonus, rights)."""
        response = await self._client.get(f"/v2/fundamentals/{isin}/corporate-actions")
        return self._wrap_response(response, "corporate_actions")

    async def get_competitors(self, instrument_key: str) -> dict[str, Any]:
        """Get competitor companies (this endpoint takes the instrument key, not the ISIN)."""
        response = await self._client.get(f"/v2/fundamentals/{instrument_key}/competitors")
        return self._wrap_response(response, "competitors")

    # ================================================================
    # NEWS
    # ================================================================

    async def get_news(
        self,
        instrument_keys: Optional[list[str]] = None,
        category: Optional[str] = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        Get news articles.

        Args:
            instrument_keys: Up to 30 instrument keys
            category: 'instrument_keys', 'positions', or 'holdings'
            page: Page number for pagination
        """
        params: dict[str, Any] = {"page": page}
        if instrument_keys:
            params["instrument_keys"] = ",".join(instrument_keys[:30])
        # Upstox requires `category`; default it when filtering by instrument
        if not category and instrument_keys:
            category = "instrument_keys"
        if category:
            params["category"] = category

        response = await self._client.get("/v2/news", params=params)
        return self._wrap_response(response, "news")

    # ================================================================
    # MARKET INFORMATION
    # ================================================================

    async def get_fii_data(self, interval: str = "1D") -> dict[str, Any]:
        """Get FII cash-market activity (₹ Cr), normalised with a net figure."""
        response = await self._client.get(
            "/v2/market/fii",
            params={"data_type": "NSE_EQ|CASH", "interval": interval},
        )
        return self._wrap_flows(response, "fii_data")

    async def get_dii_data(self, interval: str = "1D") -> dict[str, Any]:
        """Get DII cash-market activity (₹ Cr), normalised with a net figure."""
        response = await self._client.get(
            "/v2/market/dii",
            params={"data_type": "NSE_EQ|CASH", "interval": interval},
        )
        return self._wrap_flows(response, "dii_data")

    def _wrap_flows(self, response: dict[str, Any], source: str) -> dict[str, Any]:
        """Convert raw buy/sell rows into {net, buy, sell, date, history} (newest first)."""
        rows = (response.get("data") or {}).get("NSE_EQ|CASH") or []
        history = []
        for row in sorted(rows, key=lambda r: r.get("time_stamp", 0), reverse=True):
            buy = row.get("buy_amount") or 0.0
            sell = row.get("sell_amount") or 0.0
            history.append({
                "date": datetime.fromtimestamp(row.get("time_stamp", 0) / 1000).strftime("%Y-%m-%d"),
                "buy": round(buy, 2),
                "sell": round(sell, 2),
                "net": round(buy - sell, 2),
            })
        wrapped = self._wrap_response(response, source)
        wrapped["data"] = {**history[0], "history": history} if history else None
        return wrapped

    async def get_open_interest(
        self,
        instrument_key: str,
        expiry: str,
    ) -> dict[str, Any]:
        """Get open interest data by strike price."""
        response = await self._client.get(
            "/v2/market/oi",
            params={"instrument_key": instrument_key, "expiry": expiry},
        )
        return self._wrap_response(response, "open_interest")

    async def get_change_in_oi(
        self,
        instrument_key: str,
        expiry: str,
    ) -> dict[str, Any]:
        """Get change in open interest."""
        response = await self._client.get(
            "/v2/market/change-oi",
            params={"instrument_key": instrument_key, "expiry": expiry},
        )
        return self._wrap_response(response, "change_oi")

    async def get_max_pain(self, instrument_key: str) -> dict[str, Any]:
        """Get max pain data."""
        response = await self._client.get(
            "/v2/market/max-pain",
            params={"instrument_key": instrument_key},
        )
        return self._wrap_response(response, "max_pain")

    async def get_pcr(self, instrument_key: str) -> dict[str, Any]:
        """Get put-call ratio data."""
        response = await self._client.get(
            "/v2/market/pcr",
            params={"instrument_key": instrument_key},
        )
        return self._wrap_response(response, "pcr")

    # ================================================================
    # OPTIONS
    # ================================================================

    async def get_option_chain(
        self,
        instrument_key: str,
        expiry: str,
    ) -> dict[str, Any]:
        """Get put/call option chain."""
        response = await self._client.get(
            "/v2/option/chain",
            params={"instrument_key": instrument_key, "expiry_date": expiry},
        )
        return self._wrap_response(response, "option_chain")

    async def get_option_contracts(
        self,
        instrument_key: str,
    ) -> dict[str, Any]:
        """Get active option contracts."""
        response = await self._client.get(
            "/v2/option/contracts",
            params={"instrument_key": instrument_key},
        )
        return self._wrap_response(response, "option_contracts")

    async def get_option_greeks(
        self,
        instrument_keys: list[str],
    ) -> dict[str, Any]:
        """Get option Greeks (delta, gamma, theta, vega, IV)."""
        keys = ",".join(instrument_keys[:500])
        response = await self._client.get(
            "/v2/option/greeks",
            params={"instrument_key": keys},
        )
        return self._wrap_response(response, "option_greeks")

    async def get_expiries(self, instrument_key: str) -> dict[str, Any]:
        """Get available expiry dates for an instrument."""
        response = await self._client.get(
            "/v2/option/expiries",
            params={"instrument_key": instrument_key},
        )
        return self._wrap_response(response, "expiries")

    # ================================================================
    # MARKET INFO
    # ================================================================

    async def get_market_holidays(self) -> dict[str, Any]:
        """Get market holiday list."""
        response = await self._client.get("/v2/market/holidays")
        return self._wrap_response(response, "market_holidays")

    async def get_market_status(self, exchange: str = "NSE") -> dict[str, Any]:
        """Get current market status."""
        response = await self._client.get(f"/v2/market/status/{exchange}")
        return self._wrap_response(response, "market_status")

    async def get_market_timings(self, date_str: str) -> dict[str, Any]:
        """Get market timing schedules."""
        response = await self._client.get(
            "/v2/market/timings",
            params={"date": date_str},
        )
        return self._wrap_response(response, "market_timings")

    # ================================================================
    # USER
    # ================================================================

    async def get_profile(self) -> dict[str, Any]:
        """Get user profile information."""
        response = await self._client.get("/v2/user/profile")
        return self._wrap_response(response, "user_profile")

    # ================================================================
    # WEBSOCKET AUTH
    # ================================================================

    async def get_market_feed_auth_url(self) -> dict[str, Any]:
        """Get authorized WebSocket URL for market data streaming V3."""
        response = await self._client.get(
            "/v3/feed/market-data-feed/authorize"
        )
        return self._wrap_response(response, "ws_auth")

    async def get_portfolio_feed_auth_url(self) -> dict[str, Any]:
        """Get authorized WebSocket URL for portfolio stream."""
        response = await self._client.get(
            "/v2/feed/portfolio-stream-feed/authorize"
        )
        return self._wrap_response(response, "portfolio_ws_auth")

    # ================================================================
    # HELPERS
    # ================================================================

    def _wrap_response(self, response: dict[str, Any], source: str) -> dict[str, Any]:
        """Add data freshness metadata to every response."""
        return {
            "data": response.get("data"),
            "status": response.get("status", "unknown"),
            "metadata": {
                "source": f"upstox_{source}",
                "received_at": datetime.utcnow().isoformat(),
                "api_status": response.get("status"),
            },
        }

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()
