"""
StockMind AI — Historical Data Collection
Pulls daily candles for the approved universe into the (previously unused)
Candle table, so the training pipeline doesn't re-fetch from Upstox on every
run. Idempotent: re-running for the same symbol replaces its stored rows for
the requested interval rather than appending duplicates.
"""

from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.market import Candle
from app.services.upstox.provider import UpstoxDataProvider

logger = get_logger(__name__)


async def collect_historical_data(
    db: AsyncSession,
    provider: UpstoxDataProvider,
    symbols: list[str],
    lookback_days: int,
) -> dict[str, Any]:
    """Fetch `lookback_days` of daily candles per symbol and upsert into `Candle`. Returns a per-symbol row-count/error summary."""
    from_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    results: dict[str, Any] = {}

    for symbol in symbols:
        try:
            inst = await provider.resolve_instrument(symbol)
            instrument_key = inst["instrument_key"]
            response = await provider.get_historical_candles(instrument_key, "day", from_date=from_date)
            rows = (response.get("data") or {}).get("candles") or []
            if not rows:
                results[symbol] = {"rows": 0, "error": "no candles returned"}
                continue

            await db.execute(delete(Candle).where(Candle.instrument_key == instrument_key, Candle.interval == "day"))
            for r in rows:
                # Upstox candle shape: [timestamp, open, high, low, close, volume, oi]
                db.add(Candle(
                    instrument_key=instrument_key,
                    interval="day",
                    timestamp=pd.Timestamp(r[0]).to_pydatetime(),
                    open=r[1],
                    high=r[2],
                    low=r[3],
                    close=r[4],
                    volume=r[5],
                    oi=r[6] if len(r) > 6 else None,
                ))
            await db.commit()
            results[symbol] = {"rows": len(rows), "instrument_key": instrument_key}
            logger.info("historical_data_collected", symbol=symbol, rows=len(rows))
        except Exception as e:
            await db.rollback()
            logger.warning("historical_data_collection_failed", symbol=symbol, error=str(e))
            results[symbol] = {"rows": 0, "error": str(e)}

    return results
