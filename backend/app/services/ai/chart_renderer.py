"""
StockMind AI — Candlestick Chart Rendering
Renders a real candlestick-plus-volume chart (with 20/50/200-day moving
averages, since the research-report prompt explicitly discusses EMA
alignment) from Upstox OHLCV candles, for Claude's vision input. This is the
only way the model actually "sees" price structure — without it, "chart"
analysis is inferred purely from numeric indicators.
"""

import io
from typing import Any

import matplotlib
matplotlib.use("Agg")  # headless — no display backend needed on a server
import mplfinance as mpf
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


def render_candlestick_chart(candles: list[Any], symbol: str) -> bytes | None:
    """
    `candles` is Upstox's raw candle array format: [timestamp, open, high, low, close, volume, oi].
    Returns PNG bytes, or None if there isn't enough data to plot anything useful.
    """
    if not candles or len(candles) < 10:
        return None

    try:
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").set_index("timestamp")
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})

        # mplfinance drops the leading N-1 rows of a MA it can't yet compute — only
        # include a moving average if there's enough history for it to render at all.
        mav = tuple(n for n in (20, 50, 200) if len(df) > n)

        buf = io.BytesIO()
        mpf.plot(
            df,
            type="candle",
            volume=True,
            style="charles",
            mav=mav if mav else None,
            title=f"\n{symbol} — Daily",
            figsize=(10, 6),
            savefig=dict(fname=buf, format="png", dpi=110, bbox_inches="tight"),
        )
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.warning("chart_render_failed", symbol=symbol, error=str(e))
        return None
