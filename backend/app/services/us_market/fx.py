"""
StockMind AI — USD/INR Exchange Rate
Real, free, no-key rate from Frankfurter (ECB reference rates) — confirmed
live. TTL-cached in-process for an hour since FX rates don't move fast enough
to justify a call on every request, and this app's own rule against
fabricating numbers applies here too: no hardcoded/guessed rate, ever.
"""

import time
from typing import Any

import httpx

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
RATE_TTL_SECONDS = 3600

_cache: dict[str, Any] = {"rate": None, "as_of": None, "at": 0.0}


async def get_usd_inr_rate() -> dict:
    """{"rate": float, "as_of": "YYYY-MM-DD", "source": "frankfurter.dev (ECB)"}
    or {"rate": None, "error": "..."} if the free FX API is unreachable —
    callers must handle the no-rate case (show USD only), never guess one."""
    if _cache["rate"] is not None and (time.time() - _cache["at"] < RATE_TTL_SECONDS):
        return {"rate": _cache["rate"], "as_of": _cache["as_of"], "source": "frankfurter.dev (ECB)"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(FRANKFURTER_URL, params={"base": "USD", "symbols": "INR"})
            response.raise_for_status()
            data = response.json()
        rate = data["rates"]["INR"]
        _cache.update(rate=rate, as_of=data["date"], at=time.time())
        return {"rate": rate, "as_of": data["date"], "source": "frankfurter.dev (ECB)"}
    except Exception as e:
        if _cache["rate"] is not None:  # serve the last known-good rate rather than nothing
            return {"rate": _cache["rate"], "as_of": _cache["as_of"], "source": "frankfurter.dev (ECB, cached)"}
        return {"rate": None, "error": f"Could not fetch USD/INR rate: {e}"}
