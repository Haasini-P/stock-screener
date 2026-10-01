"""
StockMind AI — Market Screener
Builds a live, feature-rich snapshot of the approved sector universe from Upstox data.
Feeds the scanner, sector map, daily stock list and market analytics.
"""

import asyncio
import math
import time
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd

from app.core.logging import get_logger
from app.services.analytics.features import FeatureEngine
from app.services.analytics.signals import MarketRegime, SignalEngine, PortfolioConfig
from app.services.ml.prediction_engine import EnsemblePredictionEngine
from app.services.upstox.provider import UpstoxDataProvider

logger = get_logger(__name__)

# Approved sector universe (NSE trading symbols). Every symbol here is verified
# to resolve through Upstox instrument search.
SECTOR_UNIVERSE: dict[str, list[str]] = {
    "Defence": ["HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "DATAPATTNS", "ASTRAMICRO", "PARAS", "GRSE", "ZENTEC"],
    "Power & Grid": ["NTPC", "POWERGRID", "TATAPOWER", "ABB", "SIEMENS", "BHEL", "SUZLON", "INOXWIND", "POWERINDIA"],
    "Semiconductor": ["KAYNES", "MOSCHIP", "TATAELXSI", "CGPOWER", "SYRMA", "RIR"],
    "AI / Data Centre": ["TCS", "INFY", "HCLTECH", "PERSISTENT", "NETWEB", "ANANTRAJ", "TATACOMM", "E2E", "COFORGE"],
    "Pharma / CDMO": ["SUNPHARMA", "DIVISLAB", "DRREDDY", "CIPLA", "LAURUSLABS", "SYNGENE", "PPLPHARMA", "COHANCE", "GLAND", "NEULANDLAB"],
    "Cables & Wires": ["POLYCAB", "KEI", "FINCABLES", "RRKABEL", "HAVELLS", "UNIVCABLES", "DIACABS", "PARACABLES"],
    "EV / Electronics": ["TMPV", "OLAELEC", "EXIDEIND", "ARE&M", "DIXON", "AMBER", "SONACOMS", "UNOMINDA"],
    "Chemicals": ["PIDILITIND", "SRF", "DEEPAKNTR", "NAVINFLUOR", "AARTIIND", "CLEAN", "TATACHEM", "PIIND", "ATUL"],
}

SNAPSHOT_TTL_SECONDS = 300
HISTORY_DAYS = 450  # enough trading days for SMA-200 and 52-week stats
MAX_CONCURRENCY = 8

_snapshot: dict[str, Any] = {"rows": None, "at": 0.0, "errors": []}
_snapshot_lock = asyncio.Lock()

REGIME_MAP = {r.value: r for r in MarketRegime}


def _clean(value: Any) -> Any:
    """Convert NaN/inf and numpy scalars into JSON-safe Python values."""
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _pct(value: Optional[float]) -> Optional[float]:
    """Fraction → rounded percentage."""
    return None if value is None else round(value * 100, 2)


def all_symbols() -> list[tuple[str, str]]:
    """(symbol, sector) pairs, de-duplicated (first sector wins)."""
    seen: dict[str, str] = {}
    for sector, symbols in SECTOR_UNIVERSE.items():
        for sym in symbols:
            seen.setdefault(sym, sector)
    return list(seen.items())


class MarketScreener:
    """Computes features + signals for the whole universe, cached for a few minutes."""

    def __init__(self, provider: UpstoxDataProvider, regime: Optional[str] = None):
        self.provider = provider
        self.regime = REGIME_MAP.get(regime or "")
        self.signal_engine = SignalEngine(PortfolioConfig())
        self.prediction_engine = EnsemblePredictionEngine()

    async def snapshot(self, force: bool = False) -> dict[str, Any]:
        """Return {rows, generated_at, errors}; recomputes when the cache is stale."""
        async with _snapshot_lock:
            fresh = time.time() - _snapshot["at"] < SNAPSHOT_TTL_SECONDS
            if _snapshot["rows"] is not None and fresh and not force:
                return self._result()

            started = time.monotonic()
            rows, errors = await self._build()
            if rows:
                _snapshot.update(rows=rows, at=time.time(), errors=errors)
            elif _snapshot["rows"] is None:
                _snapshot.update(rows=[], at=0.0, errors=errors)
            logger.info(
                "screener_snapshot_built",
                stocks=len(rows),
                errors=len(errors),
                seconds=round(time.monotonic() - started, 2),
            )
            return self._result()

    @staticmethod
    def _result() -> dict[str, Any]:
        return {
            "rows": _snapshot["rows"] or [],
            "generated_at": _snapshot["at"],
            "errors": _snapshot["errors"],
        }

    async def _build(self) -> tuple[list[dict], list[dict]]:
        symbols = all_symbols()
        errors: list[dict] = []
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def resolve(sym: str):
            async with semaphore:
                try:
                    return await self.provider.resolve_instrument(sym)
                except Exception as e:
                    errors.append({"symbol": sym, "stage": "resolve", "error": str(e)})
                    return None

        instruments = await asyncio.gather(*(resolve(sym) for sym, _ in symbols))
        resolved = [(sym, sector, inst) for (sym, sector), inst in zip(symbols, instruments) if inst]
        if not resolved:
            return [], errors

        # One batched live-quote call for the whole universe
        quotes_by_key: dict[str, dict] = {}
        try:
            quotes = await self.provider.get_quotes([inst["instrument_key"] for _, _, inst in resolved])
            for q in (quotes.get("data") or {}).values():
                if isinstance(q, dict) and q.get("instrument_token"):
                    quotes_by_key[q["instrument_token"]] = q
        except Exception as e:
            errors.append({"symbol": "*", "stage": "quotes", "error": str(e)})

        from_date = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()

        async def analyze(sym: str, sector: str, inst: dict):
            async with semaphore:
                try:
                    candles = await self.provider.get_historical_candles(
                        inst["instrument_key"], "day", from_date=from_date
                    )
                    candle_list = (candles.get("data") or {}).get("candles") or []
                    return self._analyze_stock(sym, sector, inst, candle_list, quotes_by_key.get(inst["instrument_key"]))
                except Exception as e:
                    errors.append({"symbol": sym, "stage": "analyze", "error": str(e)})
                    return None

        results = await asyncio.gather(*(analyze(*r) for r in resolved))
        rows = [r for r in results if r]
        self._apply_buckets(rows)
        return rows, errors

    def _analyze_stock(
        self,
        symbol: str,
        sector: str,
        inst: dict,
        candle_list: list,
        quote: Optional[dict],
    ) -> Optional[dict]:
        if len(candle_list) < 30:
            return None

        df = pd.DataFrame(candle_list, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = FeatureEngine.compute_all_features(df)
        latest = {k: _clean(v) for k, v in df.iloc[-1].to_dict().items() if k != "timestamp"}
        last_close = latest.get("close")

        # Prefer the live quote for price/volume; historical candles end at the last session
        ltp = (quote or {}).get("last_price") or last_close
        net_change = (quote or {}).get("net_change")
        if net_change is None and ltp is not None and last_close:
            net_change = ltp - last_close
        prev_close = ltp - net_change if (ltp is not None and net_change is not None) else None
        change_pct = round(net_change / prev_close * 100, 2) if prev_close else None

        # Drop missing indicators so the signal engine's .get() defaults apply
        features = {
            **{k: v for k, v in latest.items() if v is not None},
            "close": ltp,
            "symbol": symbol,
            "name": inst.get("short_name") or inst.get("name") or symbol,
            "sector": sector,
            "instrument_key": inst["instrument_key"],
        }
        signal = self.signal_engine.generate_signal(features, market_regime=self.regime)
        signal.instrument_key = inst["instrument_key"]
        signal.isin = inst.get("isin", "")
        signal.cmp_source = "upstox_quote" if quote else "upstox_candles"
        prediction = self.prediction_engine.predict(features, horizon="5D")
        signal.probability = prediction.prob_up
        signal.prediction_horizon = "5D"

        sig = signal.to_dict()
        return {
            "symbol": symbol,
            "name": features["name"],
            "sector": sector,
            "instrument_key": inst["instrument_key"],
            "isin": inst.get("isin"),
            "ltp": _clean(ltp),
            "change": _clean(round(net_change, 2)) if net_change is not None else None,
            "change_pct": change_pct,
            "volume": _clean((quote or {}).get("volume")) or latest.get("volume"),
            "volume_ratio": latest.get("volume_ratio"),
            "rsi": latest.get("rsi_14"),
            "macd_histogram": latest.get("macd_histogram"),
            "adx": latest.get("adx"),
            "atr": latest.get("atr_14"),
            "return_5d": _pct(latest.get("return_5d")),
            "return_20d": _pct(latest.get("return_20d")),
            "return_60d": _pct(latest.get("rolling_return_60d")),
            "high_52w": latest.get("high_52w"),
            "low_52w": latest.get("low_52w"),
            "dist_52w_high": _pct(latest.get("dist_52w_high")),
            "sma_50": latest.get("sma_50"),
            "sma_200": latest.get("sma_200"),
            "trend": signal.trend,
            "signal_type": sig["signal"]["type"],
            "entry": sig["signal"]["entry"],
            "probability_up": prediction.prob_up,
            "confidence": signal.confidence,
            "risk": signal.risk,
            "stop_loss": sig["entry_exit"]["stop_loss"],
            "target_1": sig["entry_exit"]["target_1"],
            "target_2": sig["entry_exit"]["target_2"],
            "risk_reward": sig["entry_exit"]["risk_reward"],
            "entry_zone": sig["entry_exit"]["entry_zone"],
            "quantity": sig["position"]["quantity"],
            "explanation": signal.explanation,
            "evidence": sig["evidence"],
            "buckets": [],
            "_features": {k: latest.get(k) for k in (
                "close", "ema_20", "ema_50", "sma_20", "sma_200", "rsi_14", "macd_histogram",
                "adx", "volume_ratio", "dist_52w_high", "bollinger_width", "volume_trend",
            )},
        }

    def _apply_buckets(self, rows: list[dict]) -> None:
        """Tag rows with the discovery buckets (momentum breakout, retest, ...) they pass."""
        if not rows:
            return
        frame = pd.DataFrame([{**r["_features"], "symbol": r["symbol"]} for r in rows])
        for col in frame.columns.drop("symbol"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        screens = [
            self.signal_engine.run_momentum_breakout_screen,
            self.signal_engine.run_breakout_retest_screen,
            self.signal_engine.run_early_stage_screen,
            self.signal_engine.run_quality_pullback_screen,
        ]
        by_symbol = {r["symbol"]: r for r in rows}
        for screen in screens:
            try:
                hits = screen(frame.copy())
            except Exception as e:  # missing columns on sparse data
                logger.warning("screen_failed", screen=screen.__name__, error=str(e))
                continue
            for _, hit in hits.iterrows():
                by_symbol[hit["symbol"]]["buckets"].append(hit["discovery_bucket"])
        for r in rows:
            r.pop("_features", None)


def sector_summary(rows: list[dict]) -> list[dict]:
    """Aggregate screener rows into per-sector performance and breadth."""
    out = []
    for sector in SECTOR_UNIVERSE:
        stocks = [r for r in rows if r["sector"] == sector]
        if not stocks:
            out.append({"sector": sector, "stocks": 0})
            continue

        def avg(field: str) -> Optional[float]:
            vals = [s[field] for s in stocks if s.get(field) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        movers = [s for s in stocks if s.get("change_pct") is not None]
        out.append({
            "sector": sector,
            "stocks": len(stocks),
            "change_pct": avg("change_pct"),
            "return_5d": avg("return_5d"),
            "return_20d": avg("return_20d"),
            "advances": sum(1 for s in movers if s["change_pct"] > 0),
            "declines": sum(1 for s in movers if s["change_pct"] < 0),
            "avg_rsi": avg("rsi"),
            "bullish_signals": sum(1 for s in stocks if s["entry"] in ("BUY_NOW", "BUY_ON_RETEST", "BREAKOUT_WATCH")),
            "top_gainer": max(movers, key=lambda s: s["change_pct"])["symbol"] if movers else None,
            "top_loser": min(movers, key=lambda s: s["change_pct"])["symbol"] if movers else None,
        })
    return out
