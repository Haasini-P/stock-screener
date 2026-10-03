"""
StockMind AI — US Stock Analysis
Mirrors app/api/routes/signals.py::analyze_stock's shape of work (technical
features -> signal -> multi-horizon predictions) for US tickers, but is
deliberately NOT a reuse of that function — it's hard-wired to Upstox's
provider, Indian market regime, and a live-broker held-symbols lookup, none of
which exist here. FeatureEngine/SignalEngine/EnsemblePredictionEngine
themselves are reused directly (confirmed market-agnostic — pure OHLCV math).

One deliberate semantic difference from the Indian path: "held" status comes
from this app's own paper-trading ledger (app/services/paper_trading.py), not
a live broker, since there is no real US brokerage connection.

No market-regime input yet (no US regime data source chosen — VIX/sector-
rotation equivalent is a listed follow-up, not silently dropped) and a fixed
default paper-trading capital/risk rather than per-request query params, to
match the $10,000 default already used for the US Settings/Dashboard.
"""

from typing import Optional

import pandas as pd

from app.api.routes.signals import _portfolio_config
from app.models.user import User
from app.services.analytics.features import FeatureEngine
from app.services.analytics.signals import SignalEngine
from app.services.ml.prediction_engine import EnsemblePredictionEngine
from app.services.paper_trading import compute_positions
from app.services.us_market.provider import USMarketProvider
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_US_CAPITAL = 10000.0
DEFAULT_US_RISK_PCT = 1.0
HORIZONS = ["1D", "5D", "10D", "20D"]


async def analyze_us_stock(
    provider: USMarketProvider, symbol: str, user: Optional[User], db: AsyncSession,
) -> dict:
    """Full technical analysis for a US ticker, or a clean data_available:false
    result (never a 500) when Alpaca isn't configured or returns too little
    history. Raises USDataUnavailableError only if the symbol itself isn't in
    the approved universe (handled by the caller same as the Indian 404 path)."""
    inst = await provider.resolve_instrument(symbol)

    candles_resp = await provider.get_historical_candles(inst["instrument_key"], "day")
    if not candles_resp.get("data_available"):
        return {
            "symbol": inst["symbol"], "name": inst["name"], "sector": inst["sector"],
            "data_available": False, "reason": candles_resp.get("reason"),
        }

    candle_data = candles_resp["candles"]
    if len(candle_data) < 50:
        return {
            "symbol": inst["symbol"], "name": inst["name"], "sector": inst["sector"],
            "data_available": False,
            "reason": f"Only {len(candle_data)} daily bars from Alpaca — need at least 50 for technical analysis.",
        }

    df = pd.DataFrame(candle_data, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = FeatureEngine.compute_all_features(df.sort_values("timestamp").reset_index(drop=True))

    latest = {k: v for k, v in df.iloc[-1].to_dict().items() if not (isinstance(v, float) and v != v)}
    latest["instrument_key"] = inst["instrument_key"]
    latest["symbol"] = inst["symbol"]
    latest["name"] = inst["name"]

    quote = await provider.get_quote(inst["instrument_key"])
    if quote.get("data_available") and quote.get("ltp"):
        latest["close"] = quote["ltp"]

    # No live US broker — "held" comes from this app's own paper-trading ledger.
    held: set[str] = set()
    if user:
        positions = await compute_positions(db, user.id)
        held = {p["symbol"] for p in positions if p["quantity"] > 0}

    signal = SignalEngine(_portfolio_config(DEFAULT_US_CAPITAL, DEFAULT_US_RISK_PCT)).generate_signal(
        latest, held_symbols=held,
    )
    signal.instrument_key = inst["instrument_key"]

    pred_engine = EnsemblePredictionEngine()
    predictions = {h: pred_engine.predict(latest, horizon=h).to_dict() for h in HORIZONS}

    news = await provider.get_news(instrument_keys=[inst["instrument_key"]])

    return {
        "symbol": inst["symbol"], "name": inst["name"], "sector": inst["sector"],
        "instrument_key": inst["instrument_key"],
        "data_available": True,
        "quote": quote,
        "signal": signal.to_dict(),
        "predictions": predictions,
        "technical_summary": signal.technical_summary,
        "news": news.get("news") if news.get("data_available") else None,
        "portfolio": {"capital": DEFAULT_US_CAPITAL, "risk_pct": DEFAULT_US_RISK_PCT},
        "metadata": {
            "source": "alpaca", "candles_used": len(candle_data),
            "features_computed": len(FeatureEngine.get_feature_names()),
        },
        "_disclaimer": (
            "US market data via Alpaca's free tier (~15-min delayed). This analysis uses computed "
            "technical indicators and statistical models — predictions are probabilistic, not deterministic."
        ),
    }
