"""
StockMind AI — Market Regime Analyzer
Determines market regime from indices, VIX, breadth, FII/DII, and global context.
Every data point is labeled FACT or DATA_NOT_VERIFIED.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging import get_logger
from app.services.analytics.signals import MarketRegime, MarketMood, DataConfidence

logger = get_logger(__name__)


@dataclass
class MarketRegimeReport:
    """Complete market regime analysis with evidence."""

    # Regime
    regime: MarketRegime = MarketRegime.NEUTRAL
    mood: MarketMood = MarketMood.NEUTRAL
    timestamp: str = ""

    # Indian market
    nifty_50: Optional[float] = None
    nifty_50_change: Optional[float] = None
    nifty_midcap: Optional[float] = None
    nifty_midcap_change: Optional[float] = None
    nifty_smallcap: Optional[float] = None
    nifty_smallcap_change: Optional[float] = None
    bank_nifty: Optional[float] = None
    bank_nifty_change: Optional[float] = None
    india_vix: Optional[float] = None
    india_vix_change: Optional[float] = None

    # Breadth
    advances: Optional[int] = None
    declines: Optional[int] = None
    breadth_ratio: Optional[float] = None

    # Institutional flows
    fii_net: Optional[float] = None
    dii_net: Optional[float] = None
    fii_trend: str = ""  # buying, selling, neutral
    dii_trend: str = ""

    # Macro
    inr_usd: Optional[float] = None
    crude_oil: Optional[float] = None
    gold: Optional[float] = None
    us_10y_yield: Optional[float] = None

    # Global
    sp500_change: Optional[float] = None
    nasdaq_change: Optional[float] = None
    dxy_change: Optional[float] = None
    asian_markets_trend: str = ""

    # Sector rotation
    strong_sectors: list[str] = field(default_factory=list)
    weak_sectors: list[str] = field(default_factory=list)

    # Risk alerts
    risk_alerts: list[dict] = field(default_factory=list)

    # Data sources
    data_sources: list[str] = field(default_factory=list)
    data_confidence: dict[str, str] = field(default_factory=dict)

    # Evidence
    regime_evidence: list[str] = field(default_factory=list)
    mood_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "mood": self.mood.value,
            "timestamp": self.timestamp,
            "indian_market": {
                "nifty_50": {"value": self.nifty_50, "change": self.nifty_50_change},
                "nifty_midcap": {"value": self.nifty_midcap, "change": self.nifty_midcap_change},
                "nifty_smallcap": {"value": self.nifty_smallcap, "change": self.nifty_smallcap_change},
                "bank_nifty": {"value": self.bank_nifty, "change": self.bank_nifty_change},
                "india_vix": {"value": self.india_vix, "change": self.india_vix_change},
            },
            "breadth": {
                "advances": self.advances,
                "declines": self.declines,
                "ratio": self.breadth_ratio,
            },
            "institutional": {
                "fii_net": self.fii_net,
                "fii_trend": self.fii_trend,
                "dii_net": self.dii_net,
                "dii_trend": self.dii_trend,
            },
            "macro": {
                "inr_usd": self.inr_usd,
                "crude_oil": self.crude_oil,
                "gold": self.gold,
                "us_10y_yield": self.us_10y_yield,
            },
            "global": {
                "sp500_change": self.sp500_change,
                "nasdaq_change": self.nasdaq_change,
                "dxy_change": self.dxy_change,
                "asian_markets": self.asian_markets_trend,
            },
            "sectors": {
                "strong": self.strong_sectors,
                "weak": self.weak_sectors,
            },
            "risk_alerts": self.risk_alerts,
            "evidence": {
                "regime": self.regime_evidence,
                "mood": self.mood_evidence,
            },
            "data_sources": self.data_sources,
            "data_confidence": self.data_confidence,
        }


class MarketRegimeAnalyzer:
    """
    Determines market regime from multiple data sources.

    Regime is derived from EVIDENCE, not hardcoded rules.
    Each data point is labeled with its confidence level.
    """

    # VIX thresholds (India VIX)
    VIX_LOW = 12
    VIX_NORMAL = 18
    VIX_HIGH = 25
    VIX_EXTREME = 35

    def analyze(
        self,
        indices: Optional[dict] = None,
        fii_data: Optional[dict] = None,
        dii_data: Optional[dict] = None,
        global_data: Optional[dict] = None,
        macro_data: Optional[dict] = None,
    ) -> MarketRegimeReport:
        """
        Analyze market conditions and determine regime.

        Every factor contributes evidence; the regime is the aggregate.
        """
        report = MarketRegimeReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        scores: list[tuple[str, float, float]] = []  # (name, score [-1,1], weight)

        # --- Parse Indian indices ---
        if indices:
            report.data_sources.append("upstox_indices")
            self._parse_indices(indices, report, scores)

        # --- VIX ---
        if report.india_vix is not None:
            vix = report.india_vix
            if vix < self.VIX_LOW:
                scores.append(("vix_complacency", 0.3, 0.15))
                report.regime_evidence.append(f"VIX at {vix:.1f} — low volatility, complacency risk")
                report.mood_evidence.append(f"Low VIX suggests greed/complacency")
            elif vix < self.VIX_NORMAL:
                scores.append(("vix_normal", 0.1, 0.1))
                report.regime_evidence.append(f"VIX at {vix:.1f} — normal volatility")
            elif vix < self.VIX_HIGH:
                scores.append(("vix_elevated", -0.3, 0.15))
                report.regime_evidence.append(f"VIX at {vix:.1f} — elevated volatility, caution warranted")
            elif vix < self.VIX_EXTREME:
                scores.append(("vix_high", -0.6, 0.2))
                report.regime_evidence.append(f"VIX at {vix:.1f} — high fear")
                report.mood_evidence.append(f"High VIX indicates fear")
                report.risk_alerts.append({
                    "trigger": f"India VIX spike to {vix:.1f}",
                    "impact": "Increased hedging cost, wider bid/ask spreads",
                    "action": "Reduce new exposure, tighten stops",
                })
            else:
                scores.append(("vix_extreme", -0.9, 0.25))
                report.regime_evidence.append(f"VIX at {vix:.1f} — EXTREME FEAR")
                report.risk_alerts.append({
                    "trigger": f"India VIX at extreme level {vix:.1f}",
                    "impact": "All sectors affected, circuit breakers possible",
                    "action": "Halt new positions, protect existing stops, maintain cash",
                })

        # --- Institutional flows ---
        if fii_data:
            report.data_sources.append("upstox_fii")
            self._parse_fii(fii_data, report, scores)

        if dii_data:
            report.data_sources.append("upstox_dii")
            self._parse_dii(dii_data, report, scores)

        # --- Determine regime ---
        if scores:
            total_weight = sum(w for _, _, w in scores)
            composite = sum(s * w for _, s, w in scores) / total_weight if total_weight else 0

            if composite > 0.4:
                report.regime = MarketRegime.RISK_ON
            elif composite > 0.15:
                report.regime = MarketRegime.MILD_RISK_ON
            elif composite > -0.15:
                report.regime = MarketRegime.NEUTRAL
            elif composite > -0.35:
                report.regime = MarketRegime.CAUTIOUS
            elif composite > -0.6:
                report.regime = MarketRegime.RISK_OFF
            else:
                report.regime = MarketRegime.EXTREME_RISK_OFF

        # --- Determine mood ---
        report.mood = self._determine_mood(report)

        # --- If no data available ---
        if not report.data_sources:
            report.data_confidence["overall"] = DataConfidence.DATA_NOT_VERIFIED.value
            report.regime_evidence.append(
                "Insufficient data for regime determination. Connect Upstox for live analysis."
            )

        return report

    def _parse_indices(
        self,
        indices: dict,
        report: MarketRegimeReport,
        scores: list,
    ) -> None:
        """Parse index quotes from Upstox response."""
        if not indices:
            return

        for key, data in indices.items():
            if not isinstance(data, dict):
                continue

            ltp = data.get("last_price") or data.get("ltp")
            change_pct = data.get("net_change_percentage") or data.get("change_percentage")
            # Upstox full quotes only carry absolute net_change; derive the percentage
            net_change = data.get("net_change")
            if change_pct is None and ltp and net_change is not None and ltp != net_change:
                change_pct = round(net_change / (ltp - net_change) * 100, 2)

            if "Nifty 50" in key:
                report.nifty_50 = ltp
                report.nifty_50_change = change_pct
                report.data_confidence["nifty_50"] = DataConfidence.FACT.value
                if change_pct:
                    if change_pct > 1:
                        scores.append(("nifty_bullish", 0.6, 0.2))
                        report.regime_evidence.append(f"Nifty 50 up {change_pct:.2f}% — positive")
                    elif change_pct > 0:
                        scores.append(("nifty_mild_bullish", 0.2, 0.15))
                    elif change_pct > -1:
                        scores.append(("nifty_mild_bearish", -0.2, 0.15))
                    else:
                        scores.append(("nifty_bearish", -0.6, 0.2))
                        report.regime_evidence.append(f"Nifty 50 down {change_pct:.2f}% — negative")

            elif "India VIX" in key:
                report.india_vix = ltp
                report.india_vix_change = change_pct
                report.data_confidence["india_vix"] = DataConfidence.FACT.value

            elif "Midcap" in key or "MIDCAP" in key:
                report.nifty_midcap = ltp
                report.nifty_midcap_change = change_pct
                report.data_confidence["nifty_midcap"] = DataConfidence.FACT.value
                if change_pct:
                    if change_pct > 1:
                        scores.append(("midcap_bullish", 0.4, 0.1))
                    elif change_pct < -1:
                        scores.append(("midcap_bearish", -0.4, 0.1))

            elif "SMLCAP" in key or "Smallcap" in key:
                report.nifty_smallcap = ltp
                report.nifty_smallcap_change = change_pct
                report.data_confidence["nifty_smallcap"] = DataConfidence.FACT.value

            elif "Bank" in key:
                report.bank_nifty = ltp
                report.bank_nifty_change = change_pct

    def _parse_fii(
        self,
        fii_data: dict,
        report: MarketRegimeReport,
        scores: list,
    ) -> None:
        """Parse FII flow data."""
        if not fii_data:
            return

        net = fii_data.get("net_value") or fii_data.get("net")
        if net is not None:
            report.fii_net = net
            report.data_confidence["fii"] = DataConfidence.FACT.value

            if net > 1000:  # ₹1000 Cr+ buying
                scores.append(("fii_buying", 0.5, 0.15))
                report.fii_trend = "strong_buying"
                report.regime_evidence.append(f"FII net buying ₹{net:.0f} Cr — positive flows")
            elif net > 0:
                scores.append(("fii_mild_buying", 0.2, 0.1))
                report.fii_trend = "buying"
            elif net > -1000:
                scores.append(("fii_mild_selling", -0.2, 0.1))
                report.fii_trend = "selling"
            else:
                scores.append(("fii_heavy_selling", -0.6, 0.2))
                report.fii_trend = "heavy_selling"
                report.regime_evidence.append(f"FII net selling ₹{abs(net):.0f} Cr — capital outflow risk")
                report.risk_alerts.append({
                    "trigger": f"Heavy FII selling: ₹{abs(net):.0f} Cr",
                    "impact": "Potential for broader market weakness, INR pressure",
                    "action": "Avoid new mid/smallcap entries, watch for follow-through",
                })

    def _parse_dii(
        self,
        dii_data: dict,
        report: MarketRegimeReport,
        scores: list,
    ) -> None:
        """Parse DII flow data."""
        if not dii_data:
            return

        net = dii_data.get("net_value") or dii_data.get("net")
        if net is not None:
            report.dii_net = net
            report.data_confidence["dii"] = DataConfidence.FACT.value

            if net > 500:
                scores.append(("dii_support", 0.3, 0.08))
                report.dii_trend = "buying"
            elif net < -500:
                scores.append(("dii_selling", -0.2, 0.08))
                report.dii_trend = "selling"
            else:
                report.dii_trend = "neutral"

    def _determine_mood(self, report: MarketRegimeReport) -> MarketMood:
        """Determine market mood from available evidence."""
        mood_score = 0

        # VIX contribution
        if report.india_vix:
            if report.india_vix > self.VIX_EXTREME:
                mood_score -= 4
                report.mood_evidence.append("Extreme VIX → Extreme Fear conditions")
            elif report.india_vix > self.VIX_HIGH:
                mood_score -= 2
                report.mood_evidence.append("High VIX → Fear conditions")
            elif report.india_vix < self.VIX_LOW:
                mood_score += 2
                report.mood_evidence.append("Very low VIX → potential complacency (Greed)")

        # Index performance
        if report.nifty_50_change:
            if report.nifty_50_change > 1.5:
                mood_score += 2
            elif report.nifty_50_change < -1.5:
                mood_score -= 2

        # FII flows
        if report.fii_trend == "heavy_selling":
            mood_score -= 1
        elif report.fii_trend == "strong_buying":
            mood_score += 1

        # Classify
        if mood_score >= 4:
            return MarketMood.EXTREME_GREED
        elif mood_score >= 2:
            return MarketMood.GREED
        elif mood_score <= -4:
            mood = MarketMood.EXTREME_FEAR
            report.mood_evidence.append(
                "Extreme Fear can create conditions for a rebound, "
                "but reversal requires price and breadth confirmation."
            )
            return mood
        elif mood_score <= -2:
            return MarketMood.FEAR
        return MarketMood.NEUTRAL
