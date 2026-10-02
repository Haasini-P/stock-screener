"""
StockMind AI — Daily Stock List Service
Implements the complete "/daily stocks list" workflow.
This is the central orchestrator that ties all analysis together.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging import get_logger
from app.services.analytics.signals import (
    ContinuityStatus,
    EntryClassification,
    PortfolioConfig,
    StockSignal,
    TimeHorizon,
)
from app.services.analytics.regime import MarketRegimeAnalyzer, MarketRegimeReport

logger = get_logger(__name__)


@dataclass
class DailyStockListReport:
    """Complete daily stock list output as specified in Rule 20-23."""

    date: str = ""
    timestamp: str = ""

    # Data status
    data_status: dict = field(default_factory=dict)

    # Market regime
    market_regime: Optional[dict] = None

    # Stock lists by horizon
    short_term: list[dict] = field(default_factory=list)  # 1-4 weeks
    mid_term: list[dict] = field(default_factory=list)     # 1-6 months
    long_term: list[dict] = field(default_factory=list)    # 6-24 months

    # Continuity tracking
    continuity: list[dict] = field(default_factory=list)

    # Top picks
    top_short_term: list[dict] = field(default_factory=list)
    top_mid_term: list[dict] = field(default_factory=list)
    top_long_term: list[dict] = field(default_factory=list)

    # Capital deployment
    capital_deployment: dict = field(default_factory=dict)

    # Risk alerts
    risk_alerts: list[dict] = field(default_factory=list)

    # Actionable classification
    actionable_now: list[dict] = field(default_factory=list)   # 🟢
    watch_retest: list[dict] = field(default_factory=list)     # 🟡
    wait: list[dict] = field(default_factory=list)             # 🟠
    avoid: list[dict] = field(default_factory=list)            # 🔴

    def to_dict(self) -> dict:
        return {
            "report_type": "DAILY_STOCK_LIST",
            "date": self.date,
            "timestamp": self.timestamp,
            "data_status": self.data_status,
            "market_regime": self.market_regime,
            "stocks": {
                "short_term": self.short_term,
                "mid_term": self.mid_term,
                "long_term": self.long_term,
            },
            "continuity": self.continuity,
            "top_picks": {
                "short_term": self.top_short_term,
                "mid_term": self.top_mid_term,
                "long_term": self.top_long_term,
            },
            "capital_deployment": self.capital_deployment,
            "risk_alerts": self.risk_alerts,
            "actionable": {
                "buy_now": self.actionable_now,
                "watch_retest": self.watch_retest,
                "wait": self.wait,
                "avoid": self.avoid,
            },
            "_disclaimer": (
                "This is an analytical decision-support report. "
                "All predictions are probabilistic estimates with inherent uncertainty. "
                "No stock recommendation is a certainty. Protect capital first."
            ),
        }


class DailyStockListService:
    """
    Orchestrates the complete Daily Stock List generation.

    Workflow:
    1. Determine data status (Upstox connectivity, freshness)
    2. Analyze market regime
    3. Run discovery buckets across approved sectors
    4. Generate signals for qualifying stocks
    5. Classify by time horizon
    6. Compare with previous report (continuity)
    7. Rank and select top picks
    8. Calculate capital deployment
    9. Generate risk alerts
    10. Produce final actionable classifications
    """

    def __init__(self, portfolio_config: Optional[PortfolioConfig] = None):
        self.portfolio_config = portfolio_config or PortfolioConfig()
        self.regime_analyzer = MarketRegimeAnalyzer()
        self._previous_report: Optional[DailyStockListReport] = None

    async def generate(
        self,
        market_data: Optional[dict] = None,
        screened: Optional[list[dict]] = None,
        previous_signals: Optional[list[str]] = None,
    ) -> DailyStockListReport:
        """
        Generate the complete daily stock list.

        Args:
            market_data: Current market state (indices, flows, regime) from Upstox
            screened: Screener rows for the approved universe (see MarketScreener)
            previous_signals: Symbols from the previous report, for continuity
        """
        now = datetime.now(timezone.utc)
        report = DailyStockListReport(
            date=now.strftime("%Y-%m-%d"),
            timestamp=now.isoformat(),
        )

        # 1. Data status
        report.data_status = self._check_data_status(market_data)

        # 2. Market regime
        if market_data and market_data.get("regime"):
            report.market_regime = market_data["regime"]
            report.risk_alerts = market_data["regime"].get("risk_alerts", [])
        elif market_data:
            regime_report = self.regime_analyzer.analyze(
                indices=market_data.get("indices"),
                fii_data=market_data.get("fii_activity"),
                dii_data=market_data.get("dii_activity"),
            )
            report.market_regime = regime_report.to_dict()
            report.risk_alerts = regime_report.risk_alerts
        else:
            report.market_regime = {
                "regime": "Neutral",
                "mood": "Neutral",
                "note": "Live market data required. Connect Upstox to activate regime analysis.",
            }

        # 3-9. Discovery -> signals -> horizons -> continuity -> ranking
        if not market_data or screened is None:
            report.data_status["action_required"] = (
                "Connect Upstox API to activate the full stock discovery engine. "
                "Without live data, the system cannot generate verified recommendations."
            )
        else:
            logger.info("daily_stock_list_generating", date=report.date, universe=len(screened))
            self._populate_from_screener(report, screened, previous_signals or [])

        # 10. Capital deployment recommendation
        report.capital_deployment = self._capital_deployment(report)

        return report

    # Entries that represent an actionable or developing long setup
    BULLISH_ENTRIES = {"BUY_NOW", "BUY_ON_RETEST", "BUY_ON_DIP", "BREAKOUT_WATCH"}

    def _populate_from_screener(
        self,
        report: DailyStockListReport,
        rows: list[dict],
        previous_symbols: list[str],
    ) -> None:
        cfg = self.portfolio_config
        max_position_value = cfg.total_capital * 0.20  # never more than 20% in one stock

        candidates = []
        for r in rows:
            # Existing holdings (tagged upstream from the user's live broker holdings — see
            # app/services/portfolio_holdings.py) get the exact same bucket treatment as any
            # other candidate now; _list_item carries is_holding/holding_action through so the
            # UI can show "ADD"/"REDUCE" instead of a generic buy/avoid label for these rows.
            if r["entry"] == "AVOID":
                report.avoid.append(self._list_item(r))
                continue
            if r["entry"] not in self.BULLISH_ENTRIES and not r["buckets"]:
                if r["entry"] == "EXTENDED":
                    report.wait.append(self._list_item(r, "Extended move - do not chase"))
                continue
            candidates.append(r)

        items = []
        for r in candidates:
            item = self._list_item(r)
            if r.get("ltp") and r.get("stop_loss") and r["ltp"] > r["stop_loss"]:
                quality = "high" if r.get("confidence") == "high" else "default"
                qty = cfg.calculate_quantity(r["ltp"], r["stop_loss"], quality)
                qty = min(qty, int(max_position_value // r["ltp"]))
                item["quantity"] = qty
                item["position_value"] = round(qty * r["ltp"], 2)
                item["max_risk"] = round(qty * (r["ltp"] - r["stop_loss"]), 2)

            item["horizon"] = self._horizon_for(r).value
            item["continuity"] = (
                ContinuityStatus.RETAINED.value if r["symbol"] in previous_symbols
                else ContinuityStatus.NEW.value
            )
            item["score"] = self._rank_score(r)
            getattr(report, item["horizon"]).append(item)
            items.append(item)

            if r["entry"] == "BUY_NOW":
                report.actionable_now.append(item)
            elif r["entry"] in self.BULLISH_ENTRIES:
                report.watch_retest.append(item)
            else:
                report.wait.append(item)

        for horizon in ("short_term", "mid_term", "long_term"):
            ranked = sorted(getattr(report, horizon), key=lambda i: i["score"], reverse=True)
            setattr(report, horizon, ranked)
            setattr(report, f"top_{horizon}", ranked[:3])

        current = {i["symbol"] for i in items}
        report.continuity = [
            {
                "symbol": i["symbol"],
                "previous_status": "Present" if i["symbol"] in previous_symbols else "-",
                "today_status": i["continuity"],
                "entry": i["entry"],
            }
            for i in items
        ] + [
            {
                "symbol": sym,
                "previous_status": "Present",
                "today_status": ContinuityStatus.REMOVED.value,
                "entry": "N/A",
            }
            for sym in previous_symbols if sym not in current
        ]

    @staticmethod
    def _list_item(r: dict, reason: Optional[str] = None) -> dict:
        return {
            "symbol": r["symbol"],
            "name": r.get("name"),
            "sector": r["sector"],
            "ltp": r.get("ltp"),
            "change_pct": r.get("change_pct"),
            "entry": r["entry"],
            "signal_type": r.get("signal_type"),
            "probability_up": r.get("probability_up"),
            "confidence": r.get("confidence"),
            "risk": r.get("risk"),
            "trend": r.get("trend"),
            "rsi": r.get("rsi"),
            "volume_ratio": r.get("volume_ratio"),
            "entry_zone": r.get("entry_zone"),
            "stop_loss": r.get("stop_loss"),
            "target_1": r.get("target_1"),
            "target_2": r.get("target_2"),
            "risk_reward": r.get("risk_reward"),
            "buckets": r.get("buckets", []),
            "explanation": reason or r.get("explanation"),
            "is_holding": r.get("is_holding", False),
            "holding_action": r.get("holding_action"),
        }

    @staticmethod
    def _horizon_for(r: dict) -> TimeHorizon:
        buckets = set(r.get("buckets") or [])
        rsi, vol = r.get("rsi"), r.get("volume_ratio")
        if buckets & {"momentum_breakout", "early_stage_breakout"} or (
            vol and vol >= 2 and rsi and 55 <= rsi <= 70
        ):
            return TimeHorizon.SHORT_TERM
        if "quality_pullback" in buckets or (
            r.get("trend") == "Strong Uptrend" and (r.get("return_60d") or 0) > 10
        ):
            return TimeHorizon.LONG_TERM
        return TimeHorizon.MID_TERM

    @staticmethod
    def _rank_score(r: dict) -> float:
        score = (r.get("probability_up") or 0.5) * 100
        score += {"BUY_NOW": 15, "BUY_ON_RETEST": 10, "BUY_ON_DIP": 8, "BREAKOUT_WATCH": 5}.get(r["entry"], 0)
        score += 4 * len(r.get("buckets") or [])
        score += {"high": 6, "moderate": 3}.get(r.get("confidence"), 0)
        score -= {"high": 6, "medium-high": 3}.get(r.get("risk"), 0)
        return round(score, 2)

    def classify_signal_by_horizon(self, signal: StockSignal) -> TimeHorizon:
        """Classify a signal into the appropriate time horizon."""
        # Short-term: strong momentum, volume, breakout
        if signal.volume_ratio and signal.volume_ratio > 2.0:
            if signal.rsi and 55 <= signal.rsi <= 70:
                return TimeHorizon.SHORT_TERM

        # Long-term: strong fundamentals, ROCE, structural growth
        if signal.roe and signal.roe > 15 and signal.revenue_growth and signal.revenue_growth > 15:
            return TimeHorizon.LONG_TERM

        # Default to mid-term
        return TimeHorizon.MID_TERM

    def track_continuity(
        self,
        current_signals: list[StockSignal],
        previous_symbols: list[str],
    ) -> list[dict]:
        """Track continuity between daily reports (Rule 7)."""
        continuity = []
        current_symbols = {s.symbol for s in current_signals}

        for signal in current_signals:
            if signal.symbol in previous_symbols:
                # Was present before
                if signal.entry_classification in (
                    EntryClassification.BUY_NOW,
                    EntryClassification.BUY_ON_RETEST,
                ):
                    status = ContinuityStatus.RETAINED
                elif signal.entry_classification == EntryClassification.EXTENDED:
                    status = ContinuityStatus.DOWNGRADED
                elif signal.entry_classification == EntryClassification.AVOID:
                    status = ContinuityStatus.REMOVED
                else:
                    status = ContinuityStatus.RETAINED
            else:
                status = ContinuityStatus.NEW

            continuity.append({
                "symbol": signal.symbol,
                "previous_status": "Present" if signal.symbol in previous_symbols else "—",
                "today_status": status.value,
                "entry": signal.entry_classification.value,
                "reason": signal.explanation[:100] if signal.explanation else "",
            })

        # Mark removed stocks
        for prev_sym in previous_symbols:
            if prev_sym not in current_symbols:
                continuity.append({
                    "symbol": prev_sym,
                    "previous_status": "Present",
                    "today_status": ContinuityStatus.REMOVED.value,
                    "entry": "N/A",
                    "reason": "No longer meets screening criteria",
                })

        return continuity

    def _check_data_status(self, market_data: Optional[dict]) -> dict:
        """Check data availability and freshness."""
        status = {
            "upstox": "disconnected",
            "google_fallback": "not_used",
            "nse_bse_cross_check": "not_available",
            "timestamps": {},
            "data_not_verified_items": [],
        }

        if market_data:
            status["upstox"] = "connected"
            metadata = market_data.get("metadata") or {}
            status["timestamps"]["last_quote"] = metadata.get("timestamp")
            status["data_freshness"] = metadata.get("data_freshness", "unknown")
        else:
            status["data_not_verified_items"].append("All market data — Upstox not connected")

        return status

    def _capital_deployment(self, report: DailyStockListReport) -> dict:
        """Generate capital deployment recommendation."""
        total = self.portfolio_config.total_capital
        regime = report.market_regime.get("regime", "Neutral") if report.market_regime else "Neutral"

        # Adjust deployment based on regime
        deployment_pct = {
            "Risk-on": 0.80,
            "Mild risk-on": 0.70,
            "Neutral": 0.60,
            "Cautious": 0.40,
            "Risk-off": 0.25,
            "Extreme risk-off": 0.10,
        }.get(regime, 0.50)

        deployable = total * deployment_pct
        cash_reserve = total - deployable

        actionable_count = len(report.actionable_now)
        max_positions = min(actionable_count, 6)  # Max 6 positions
        per_position = deployable / max_positions if max_positions > 0 else 0

        return {
            "total_capital": total,
            "regime": regime,
            "suggested_deployment_pct": deployment_pct * 100,
            "deployable_amount": round(deployable, 0),
            "cash_reserve": round(cash_reserve, 0),
            "max_risk_per_trade": round(self.portfolio_config.max_loss_default, 0),
            "max_positions": max_positions,
            "per_position_size": round(per_position, 0),
            "sector_diversification": "Spread across 3+ approved sectors",
            "note": (
                "Never force full capital deployment. "
                "Cash is a valid position in uncertain markets."
            ),
        }
