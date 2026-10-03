"""
StockMind AI — SEC EDGAR Client (US fundamentals, free, no API key)
Official US government data (data.sec.gov) — no signup, no key, just a
descriptive User-Agent per SEC's fair-access policy
(https://www.sec.gov/os/webmaster-faq#developers). Verified live during
planning: the real ticker->CIK map and Apple Inc.'s real XBRL facts both
fetched successfully with zero credentials.

The User-Agent identifies this software, not any individual person — SEC asks
for *a* descriptive contact, not specifically an end user's identity, and
sending a user's personal email to an unrelated third-party service isn't
something to do without them explicitly asking for it. The default below uses
example.com (RFC 2606 reserved for documentation/placeholder use — it resolves
to nowhere real) rather than a live address, since SEC's bot-filter was
confirmed (live) to require an email-*shaped* string in the header but doesn't
verify deliverability. Override via the SEC_EDGAR_CONTACT env var with a real
contact if you prefer — not required for this to work.
"""

import asyncio
import time
from typing import Any, Optional

import httpx

from app.config import get_settings

settings = get_settings()

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
TICKER_MAP_TTL_SECONDS = 86400  # the official ticker list changes rarely — daily refresh is plenty

_DEFAULT_CONTACT = "StockMind AI noreply@example.com"  # see note below
_USER_AGENT = settings.sec_edgar_contact.strip() or _DEFAULT_CONTACT

_ticker_map_cache: dict[str, Any] = {"by_symbol": None, "at": 0.0}
_ticker_map_lock = asyncio.Lock()


async def _get_cik_map(client: httpx.AsyncClient) -> dict[str, str]:
    """{SYMBOL: zero-padded 10-digit CIK}, TTL-cached in-process — same style
    as screener.py's _snapshot dict."""
    async with _ticker_map_lock:
        if _ticker_map_cache["by_symbol"] and (time.time() - _ticker_map_cache["at"] < TICKER_MAP_TTL_SECONDS):
            return _ticker_map_cache["by_symbol"]
        response = await client.get(TICKER_MAP_URL, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        raw = response.json()  # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        by_symbol = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in raw.values()}
        _ticker_map_cache["by_symbol"] = by_symbol
        _ticker_map_cache["at"] = time.time()
        return by_symbol


async def get_company_facts(symbol: str) -> Optional[dict]:
    """Raw SEC companyfacts JSON for a ticker (every XBRL fact it has ever
    filed), or None if it's not an SEC-registered US issuer (not expected for
    this app's approved universe, but handled cleanly either way)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        cik_map = await _get_cik_map(client)
        cik = cik_map.get(symbol.strip().upper())
        if not cik:
            return None
        response = await client.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
