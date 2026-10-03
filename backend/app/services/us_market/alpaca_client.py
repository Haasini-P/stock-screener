"""
StockMind AI — Alpaca Markets Client (US market data only)
Free tier: 15-min-delayed IEX feed, 200 req/min, 6+ years of daily history, a
free Benzinga-sourced news feed — no KYC, just an email signup at
https://app.alpaca.markets/signup. Used ONLY for market data (quotes, candles,
news) — never order execution; this app's own paper-trading ledger
(app/services/paper_trading.py) remains the system of record for trades.

Deliberately no circuit breaker / retry logic here (unlike UpstoxClient) — this
is a free, read-only, low-volume data API; that resilience hardening is a
reasonable later addition, not needed for a first working version.
"""

import httpx

DATA_BASE_URL = "https://data.alpaca.markets"


class AlpacaAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


class AlpacaClient:
    def __init__(self, api_key_id: str, api_secret_key: str):
        self._headers = {"APCA-API-KEY-ID": api_key_id, "APCA-API-SECRET-KEY": api_secret_key}

    async def _request(self, path: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(f"{DATA_BASE_URL}{path}", headers=self._headers, params=params)
            except httpx.RequestError as e:
                raise AlpacaAPIError(502, f"Could not reach Alpaca: {e}")

        if response.status_code == 401:
            raise AlpacaAPIError(401, "Alpaca rejected these credentials — check the API Key ID/Secret in Settings.")
        if response.status_code == 403:
            raise AlpacaAPIError(403, "Alpaca denied this request — check your account's data-feed entitlement.")
        if response.status_code == 429:
            raise AlpacaAPIError(429, "Alpaca rate limit hit (free tier: 200 requests/min) — try again shortly.")
        if response.status_code >= 400:
            raise AlpacaAPIError(response.status_code, f"Alpaca API error {response.status_code}: {response.text[:300]}")
        return response.json()

    async def get_snapshot(self, symbol: str) -> dict:
        """Latest trade, latest quote, today's and yesterday's daily bar in one call."""
        return await self._request(f"/v2/stocks/{symbol}/snapshot", {"feed": "iex"})

    async def get_daily_bars(self, symbol: str, start: str, end: str) -> list[dict]:
        """Daily OHLCV bars between start/end (YYYY-MM-DD). Each bar:
        {t, o, h, l, c, v, n, vw}. Adjusted for splits, not dividends, matching
        how most retail charting tools present price history by default.

        feed="iex" is mandatory here, not just a sane default like on the
        snapshot endpoint: confirmed live against a real free-tier account
        that /v2/stocks/bars silently defaults to the premium "sip" feed and
        gets rejected with 403 "subscription does not permit querying recent
        SIP data" if this isn't passed explicitly."""
        data = await self._request("/v2/stocks/bars", {
            "symbols": symbol, "timeframe": "1Day", "start": start, "end": end,
            "limit": 10000, "adjustment": "split", "feed": "iex",
        })
        return (data.get("bars") or {}).get(symbol, [])

    async def get_news(self, symbol: str, limit: int = 10) -> list[dict]:
        """Recent news for a symbol (Benzinga-sourced). Each item:
        {headline, created_at, summary, url, source}. No "feed" param here —
        confirmed live that the news endpoint rejects it outright (400
        "unexpected query parameter(s): feed"), unlike snapshot/bars which
        need it for free-tier entitlement."""
        data = await self._request("/v1beta1/news", {"symbols": symbol, "limit": min(limit, 50)})
        return data.get("news") or []

    async def test_connection(self) -> None:
        """Cheapest real call that proves the key/secret actually work — a
        snapshot for a well-known symbol. Raises AlpacaAPIError on failure
        (401/403/network error); returns nothing on success."""
        await self.get_snapshot("AAPL")
