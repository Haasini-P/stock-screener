"""
StockMind AI — Market State
Cached live market snapshot: index quotes, FII/DII flows, market status and regime.
"""

import asyncio
import time
from typing import Any

from app.core.logging import get_logger
from app.services.analytics.regime import MarketRegimeAnalyzer
from app.services.upstox.provider import UpstoxDataProvider

logger = get_logger(__name__)

INDEX_KEYS = [
    "NSE_INDEX|Nifty 50",
    "NSE_INDEX|Nifty Bank",
    "NSE_INDEX|India VIX",
    "NSE_INDEX|NIFTY MIDCAP 100",
    "NSE_INDEX|NIFTY SMLCAP 100",
]

STATE_TTL_SECONDS = 30

_state: dict[str, Any] = {"value": None, "at": 0.0}
_state_lock = asyncio.Lock()


async def get_market_state(provider: UpstoxDataProvider, force: bool = False) -> dict[str, Any]:
    """
    Return {indices, fii_activity, dii_activity, market_status, regime, metadata}.
    Index quotes are required (errors propagate); flows and status are best-effort.
    """
    async with _state_lock:
        if not force and _state["value"] and time.time() - _state["at"] < STATE_TTL_SECONDS:
            return _state["value"]

        quotes = await provider.get_quotes(INDEX_KEYS)

        async def optional(coro, name: str):
            try:
                return (await coro).get("data")
            except Exception as e:
                logger.warning("market_state_optional_failed", source=name, error=str(e))
                return None

        fii, dii, status = await asyncio.gather(
            optional(provider.get_fii_data(), "fii"),
            optional(provider.get_dii_data(), "dii"),
            optional(provider.get_market_status("NSE"), "market_status"),
        )

        regime = MarketRegimeAnalyzer().analyze(
            indices=quotes.get("data"),
            fii_data=fii,
            dii_data=dii,
        ).to_dict()

        value = {
            "indices": quotes.get("data"),
            "fii_activity": fii,
            "dii_activity": dii,
            "market_status": status,
            "regime": regime,
            "metadata": {
                "source": "upstox",
                "timestamp": quotes.get("metadata", {}).get("received_at"),
                "data_freshness": "live" if status else "unknown",
            },
        }
        _state.update(value=value, at=time.time())
        return value
