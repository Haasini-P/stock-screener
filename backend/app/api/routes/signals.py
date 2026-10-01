"""
StockMind AI — Signals & Daily Stock List Routes
Endpoints for the daily stock list, market regime, single-stock analysis and entry levels.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_optional_user
from app.api.routes.market import get_market_provider, get_screener_rows
from app.database import get_db
from app.models.user import User
from app.services.analytics.daily_list import DailyStockListService
from app.services.analytics.market_state import get_market_state
from app.services.analytics.signals import MarketRegime, PortfolioConfig

router = APIRouter(prefix="/api/signals", tags=["Signals"])

# Symbols in the most recent daily list per date, for continuity tracking (in-process)
_daily_history: dict[str, list[str]] = {}


def _portfolio_config(capital: float, risk_pct: float) -> PortfolioConfig:
    """Portfolio config from user settings; risk_pct is a percentage (0.75 = 0.75%)."""
    fraction = risk_pct / 100
    return PortfolioConfig(
        total_capital=capital,
        max_loss_default_pct=fraction,
        max_loss_high_quality_pct=fraction * 4 / 3,
        max_loss_low_quality_pct=fraction * 2 / 3,
    )


CapitalQuery = Query(200000, gt=0, le=1e10, description="Portfolio capital in ₹")
RiskQuery = Query(0.75, gt=0, le=5, description="Max loss per trade, % of capital")


@router.get("/daily-list")
async def daily_stock_list(
    capital: float = CapitalQuery,
    risk_pct: float = RiskQuery,
    refresh: bool = False,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate the Daily Stock List: data status, regime, multi-bucket discovery,
    signals by horizon, continuity, top picks and capital deployment.
    """
    provider = await get_market_provider(user, db)
    market_state = await get_market_state(provider, force=refresh)
    rows, meta = await get_screener_rows(provider, force=refresh)

    today = date.today().isoformat()
    previous_dates = sorted(d for d in _daily_history if d < today)
    previous = _daily_history[previous_dates[-1]] if previous_dates else []

    service = DailyStockListService(_portfolio_config(capital, risk_pct))
    report = (await service.generate(market_data=market_state, screened=rows, previous_signals=previous)).to_dict()

    _daily_history[today] = [
        s["symbol"] for h in ("short_term", "mid_term", "long_term") for s in report["stocks"][h]
    ]
    report["screener"] = meta
    return report


@router.get("/regime")
async def market_regime(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Current market regime: classification, indices, VIX, FII/DII flows, risk alerts.
    All data points labeled with confidence (FACT / DATA_NOT_VERIFIED).
    """
    provider = await get_market_provider(user, db)
    state = await get_market_state(provider)
    return {
        **state["regime"],
        "market_status": state["market_status"],
        "fii_activity": state["fii_activity"],
        "dii_activity": state["dii_activity"],
    }


@router.get("/analyze/{symbol}")
async def analyze_stock(
    symbol: str,
    capital: float = CapitalQuery,
    risk_pct: float = RiskQuery,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete analysis for a single stock: signal, entry/exit levels, position size,
    multi-horizon predictions, technical summary and news.
    """
    import pandas as pd
    from app.services.analytics.features import FeatureEngine
    from app.services.analytics.signals import SignalEngine
    from app.services.ml.prediction_engine import EnsemblePredictionEngine

    provider = await get_market_provider(user, db)
    inst = await provider.resolve_instrument(symbol)
    instrument_key = inst["instrument_key"]

    quote = await provider.get_quote(instrument_key)
    candles = await provider.get_historical_candles(instrument_key, "day")
    candle_data = (candles.get("data") or {}).get("candles") or []

    if len(candle_data) < 50:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data for {symbol.upper()}. Need at least 50 daily candles.",
        )

    df = pd.DataFrame(candle_data, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = FeatureEngine.compute_all_features(df.sort_values("timestamp").reset_index(drop=True))

    latest = {k: v for k, v in df.iloc[-1].to_dict().items() if not (isinstance(v, float) and v != v)}
    q = next(iter((quote.get("data") or {}).values()), {}) or {}
    if q.get("last_price"):
        latest["close"] = q["last_price"]
    latest["instrument_key"] = instrument_key
    latest["symbol"] = symbol.upper()
    latest["name"] = inst.get("short_name") or inst.get("name") or symbol.upper()

    state = await get_market_state(provider)
    regime = {r.value: r for r in MarketRegime}.get(state["regime"].get("regime"))

    signal = SignalEngine(_portfolio_config(capital, risk_pct)).generate_signal(latest, market_regime=regime)
    signal.instrument_key = instrument_key
    signal.isin = inst.get("isin", "")

    pred_engine = EnsemblePredictionEngine()
    predictions = {h: pred_engine.predict(latest, horizon=h).to_dict() for h in ["1D", "5D", "10D", "20D"]}

    news = None
    try:
        news = (await provider.get_news(instrument_keys=[instrument_key])).get("data")
    except Exception:
        pass

    return {
        "symbol": symbol.upper(),
        "name": latest["name"],
        "instrument_key": instrument_key,
        "quote": quote.get("data"),
        "signal": signal.to_dict(),
        "predictions": predictions,
        "technical_summary": signal.technical_summary,
        "news": news,
        "portfolio": {"capital": capital, "risk_pct": risk_pct},
        "metadata": {
            "source": "upstox",
            "candles_used": len(candle_data),
            "features_computed": len(FeatureEngine.get_feature_names()),
            "regime": state["regime"].get("regime"),
            "timestamp": quote.get("metadata", {}).get("received_at"),
        },
        "_disclaimer": (
            "This analysis uses computed technical indicators and statistical models. "
            "Predictions are probabilistic, not deterministic."
        ),
    }


@router.get("/entry/{symbol}")
async def entry_calculation(
    symbol: str,
    capital: float = CapitalQuery,
    risk_pct: float = RiskQuery,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Entry zone, stop-loss, targets and risk-based position size for a stock."""
    analysis = await analyze_stock(symbol, capital, risk_pct, user, db)
    signal = analysis["signal"]
    entry_exit = signal.get("entry_exit", {})
    position = signal.get("position", {})

    return {
        "symbol": symbol.upper(),
        "entry": {
            "zone": entry_exit.get("entry_zone"),
            "stop_loss": entry_exit.get("stop_loss"),
            "target_1": entry_exit.get("target_1"),
            "target_2": entry_exit.get("target_2"),
            "risk_reward": entry_exit.get("risk_reward"),
            "classification": signal.get("signal", {}).get("entry"),
        },
        "position_sizing": {
            "portfolio_capital": capital,
            "risk_pct": risk_pct,
            "max_risk_per_trade": round(capital * risk_pct / 100, 2),
            "quantity": position.get("quantity"),
            "position_value": position.get("value"),
            "risk_amount": position.get("max_risk"),
        },
        "thesis_invalidation": signal.get("thesis_invalidation"),
        "_note": "All levels are model estimates. Verify CMP before placing orders.",
    }
