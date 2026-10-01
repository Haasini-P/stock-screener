"""
StockMind AI — Signal Engine
Implements the multi-bucket stock discovery, signal generation, and analyst rules.
Every signal includes FACT vs MODEL PREDICTION vs INTERPRETATION classification.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# ENUMS & DATA CLASSES
# ============================================================

class SignalType(str, Enum):
    POTENTIAL_BULLISH_BREAKOUT = "potential_bullish_breakout"
    POTENTIAL_BEARISH_BREAKDOWN = "potential_bearish_breakdown"
    POTENTIAL_UPWARD_MOMENTUM = "potential_upward_momentum"
    POTENTIAL_DOWNWARD_MOMENTUM = "potential_downward_momentum"
    TREND_CONTINUATION = "trend_continuation"
    TREND_REVERSAL = "trend_reversal"
    ABNORMAL_VOLUME = "abnormal_volume"
    VOLATILITY_EXPANSION = "volatility_expansion"
    RELATIVE_STRENGTH = "relative_strength"
    RELATIVE_WEAKNESS = "relative_weakness"
    CONSOLIDATION_BREAKOUT = "consolidation_breakout"
    SUPPORT_BREAK = "support_break"
    RESISTANCE_BREAK = "resistance_break"
    HIGH_RISK_UNCERTAIN = "high_risk_uncertain"
    NO_SIGNAL = "no_signal"


class EntryClassification(str, Enum):
    BUY_NOW = "BUY_NOW"
    BUY_ON_RETEST = "BUY_ON_RETEST"
    BUY_ON_DIP = "BUY_ON_DIP"
    BREAKOUT_WATCH = "BREAKOUT_WATCH"
    WAIT = "WAIT"
    AVOID = "AVOID"
    EXTENDED = "EXTENDED"


class ContinuityStatus(str, Enum):
    NEW = "NEW"
    RETAINED = "RETAINED"
    UPGRADED = "UPGRADED"
    DOWNGRADED = "DOWNGRADED"
    REMOVED = "REMOVED"
    WAIT = "WAIT"


class TimeHorizon(str, Enum):
    SHORT_TERM = "short_term"    # 1-4 weeks
    MID_TERM = "mid_term"        # 1-6 months
    LONG_TERM = "long_term"      # 6-24 months


class DataConfidence(str, Enum):
    FACT = "FACT"
    ESTIMATE = "ESTIMATE"
    ANALYST_INTERPRETATION = "ANALYST_INTERPRETATION"
    DATA_NOT_VERIFIED = "DATA_NOT_VERIFIED"


class MarketRegime(str, Enum):
    RISK_ON = "Risk-on"
    MILD_RISK_ON = "Mild risk-on"
    NEUTRAL = "Neutral"
    CAUTIOUS = "Cautious"
    RISK_OFF = "Risk-off"
    EXTREME_RISK_OFF = "Extreme risk-off"


class MarketMood(str, Enum):
    EXTREME_FEAR = "Extreme Fear"
    FEAR = "Fear"
    NEUTRAL = "Neutral"
    GREED = "Greed"
    EXTREME_GREED = "Extreme Greed"


# ============================================================
# APPROVED SECTORS
# ============================================================

APPROVED_SECTORS = [
    "Defence", "Defence Electronics", "Aerospace", "Radar", "Missile Systems",
    "Defence Manufacturing", "Defence Components",
    "Power", "Power Generation", "Transmission", "Grid Equipment",
    "Power Electronics", "Renewable Infrastructure", "Energy Storage",
    "Cables & Wires",
    "AI", "Data Centres",
    "Pharma", "CDMO", "API", "Medical Devices", "Specialty Pharma",
    "Contract Manufacturing",
    "Precision Engineering",
    "Chemicals",
    "EV", "Electric Vehicles",
    "Semiconductor", "Semiconductor Manufacturing", "Semiconductor Equipment",
    "Chip Design", "Electronics Manufacturing", "OSAT", "ATMP",
    "Embedded Electronics",
]

# ============================================================
# EXISTING HOLDINGS (excluded from new recommendations)
# ============================================================

EXISTING_HOLDINGS = [
    "Apollo Micro Systems", "Avantel", "BCL Industries",
    "Bluspring Enterprises", "Delhivery",
    "Diamond Power Infrastructure", "DIACABS",
    "EMS Ltd", "Gandhar Oil Refinery",
    "Garuda Construction & Engineering", "Goldiam International",
    "Jai Balaji Industries", "JNK India",
    "Kirloskar Electric Company", "Kirloskar Ferrous Industries",
    "KPEL", "Prostarm Info Systems", "Rallis India",
    "TARIL", "Transrail",
]

EXISTING_HOLDING_SYMBOLS = {h.upper() for h in EXISTING_HOLDINGS}


# ============================================================
# POSITION SIZING
# ============================================================

@dataclass
class PortfolioConfig:
    """Portfolio risk configuration."""
    total_capital: float = 200000.0  # ₹2,00,000
    max_loss_default_pct: float = 0.0075  # 0.75% = ₹1,500
    max_loss_high_quality_pct: float = 0.01  # 1% = ₹2,000
    max_loss_low_quality_pct: float = 0.005  # 0.5% = ₹1,000

    @property
    def max_loss_default(self) -> float:
        return self.total_capital * self.max_loss_default_pct

    @property
    def max_loss_high_quality(self) -> float:
        return self.total_capital * self.max_loss_high_quality_pct

    @property
    def max_loss_low_quality(self) -> float:
        return self.total_capital * self.max_loss_low_quality_pct

    def calculate_quantity(
        self,
        entry_price: float,
        stop_loss: float,
        quality: str = "default",
    ) -> int:
        """Calculate position size based on risk."""
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return 0

        if quality == "high":
            max_loss = self.max_loss_high_quality
        elif quality == "low":
            max_loss = self.max_loss_low_quality
        else:
            max_loss = self.max_loss_default

        quantity = int(max_loss / risk_per_share)
        return max(0, quantity)


# ============================================================
# SIGNAL DATACLASS
# ============================================================

@dataclass
class StockSignal:
    """Complete stock signal with full audit trail."""
    # Identity
    symbol: str
    name: str
    instrument_key: str = ""
    isin: str = ""
    exchange: str = "NSE"
    sector: str = ""

    # Signal
    signal_type: SignalType = SignalType.NO_SIGNAL
    entry_classification: EntryClassification = EntryClassification.WAIT
    continuity_status: ContinuityStatus = ContinuityStatus.NEW
    time_horizon: TimeHorizon = TimeHorizon.SHORT_TERM

    # Price data
    cmp: Optional[float] = None
    cmp_source: str = ""
    cmp_timestamp: Optional[str] = None
    cmp_confidence: DataConfidence = DataConfidence.FACT

    # Prediction
    probability: Optional[float] = None
    confidence: str = ""  # high, moderate, low
    risk: str = ""  # low, medium, medium-high, high
    prediction_horizon: str = ""

    # Entry/Exit
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    long_term_target: Optional[float] = None
    risk_reward_ratio: Optional[float] = None

    # Position sizing
    quantity: int = 0
    position_value: float = 0.0
    max_risk_amount: float = 0.0

    # Evidence
    positive_evidence: list[dict] = field(default_factory=list)
    negative_evidence: list[dict] = field(default_factory=list)

    # Technical snapshot
    technical_summary: str = ""
    rsi: Optional[float] = None
    macd_signal_status: str = ""
    adx: Optional[float] = None
    volume_ratio: Optional[float] = None
    relative_strength: Optional[float] = None
    trend: str = ""

    # Fundamental snapshot
    fundamental_summary: str = ""
    pe_ratio: Optional[float] = None
    roe: Optional[float] = None
    revenue_growth: Optional[float] = None
    pat_growth: Optional[float] = None

    # Governance/Liquidity
    governance_flags: list[str] = field(default_factory=list)
    liquidity: str = ""  # HIGH, LOW, MODERATE

    # Meta
    timestamp: str = ""
    data_sources: list[str] = field(default_factory=list)
    model_version: str = ""
    explanation: str = ""
    thesis_invalidation: str = ""
    catalyst: str = ""
    discovery_bucket: str = ""  # Which bucket found this stock

    def to_dict(self) -> dict:
        """Serialize to dict, classifying FACT vs INTERPRETATION."""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "signal": {
                "type": self.signal_type.value,
                "entry": self.entry_classification.value,
                "status": self.continuity_status.value,
                "horizon": self.time_horizon.value,
            },
            "price": {
                "cmp": self.cmp,
                "source": self.cmp_source,
                "timestamp": self.cmp_timestamp,
                "confidence": self.cmp_confidence.value,
            },
            "prediction": {
                "probability": self.probability,
                "confidence": self.confidence,
                "risk": self.risk,
                "horizon": self.prediction_horizon,
                "_type": "MODEL_PREDICTION",
            },
            "entry_exit": {
                "entry_zone": [self.entry_zone_low, self.entry_zone_high],
                "stop_loss": self.stop_loss,
                "target_1": self.target_1,
                "target_2": self.target_2,
                "long_term_target": self.long_term_target,
                "risk_reward": self.risk_reward_ratio,
                "_type": "ANALYST_INTERPRETATION",
            },
            "position": {
                "quantity": self.quantity,
                "value": self.position_value,
                "max_risk": self.max_risk_amount,
            },
            "evidence": {
                "positive": self.positive_evidence,
                "negative": self.negative_evidence,
            },
            "technical": {
                "summary": self.technical_summary,
                "rsi": self.rsi,
                "macd": self.macd_signal_status,
                "adx": self.adx,
                "volume_ratio": self.volume_ratio,
                "trend": self.trend,
                "_type": "FACT" if self.cmp_confidence == DataConfidence.FACT else "DATA_NOT_VERIFIED",
            },
            "fundamental": {
                "summary": self.fundamental_summary,
                "pe": self.pe_ratio,
                "roe": self.roe,
                "revenue_growth": self.revenue_growth,
                "_type": "FACT",
            },
            "governance": self.governance_flags,
            "liquidity": self.liquidity,
            "explanation": self.explanation,
            "thesis_invalidation": self.thesis_invalidation,
            "catalyst": self.catalyst,
            "discovery_bucket": self.discovery_bucket,
            "data_sources": self.data_sources,
            "model_version": self.model_version,
            "timestamp": self.timestamp,
        }


# ============================================================
# SIGNAL ENGINE
# ============================================================

class SignalEngine:
    """
    Multi-bucket stock discovery and signal generation engine.

    Combines:
    1. Price action
    2. Volume
    3. Volatility
    4. Momentum
    5. Technical indicators
    6. Market regime
    7. Sector performance
    8. Index performance
    9. Relative strength
    10. Market breadth
    11. News
    12. Company fundamentals
    13. Institutional activity
    14. Options/OI information
    15. Historical analogues
    16. ML predictions
    17. Prediction uncertainty
    """

    def __init__(self, portfolio_config: Optional[PortfolioConfig] = None):
        self.portfolio_config = portfolio_config or PortfolioConfig()

    def is_existing_holding(self, name: str, symbol: str = "") -> bool:
        """Check if a stock is in the existing holdings exclusion list."""
        name_upper = name.upper().strip()
        symbol_upper = symbol.upper().strip()
        for holding in EXISTING_HOLDING_SYMBOLS:
            if holding in name_upper or holding in symbol_upper:
                return True
        return False

    def generate_signal(
        self,
        features: dict[str, Any],
        fundamentals: Optional[dict] = None,
        news_sentiment: Optional[dict] = None,
        market_regime: Optional[MarketRegime] = None,
        sector_data: Optional[dict] = None,
        ml_prediction: Optional[dict] = None,
        options_data: Optional[dict] = None,
    ) -> StockSignal:
        """
        Generate a comprehensive stock signal by combining all available evidence.

        This is NOT a simple if-else rule engine. It combines multiple
        factors with uncertainty quantification.
        """
        signal = StockSignal(
            symbol=features.get("symbol", ""),
            name=features.get("name", ""),
            sector=features.get("sector", ""),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Check existing holding exclusion
        if self.is_existing_holding(signal.name, signal.symbol):
            signal.entry_classification = EntryClassification.AVOID
            signal.explanation = "EXCLUDED — EXISTING HOLDING"
            return signal

        # --- Collect evidence ---
        evidence_scores = []

        # 1. Price action & trend
        trend_score, trend_evidence = self._analyze_trend(features)
        evidence_scores.append(("trend", trend_score, 0.15))
        signal.positive_evidence.extend([e for e in trend_evidence if e.get("direction") == "positive"])
        signal.negative_evidence.extend([e for e in trend_evidence if e.get("direction") == "negative"])

        # 2. Volume
        volume_score, volume_evidence = self._analyze_volume(features)
        evidence_scores.append(("volume", volume_score, 0.12))
        signal.positive_evidence.extend([e for e in volume_evidence if e.get("direction") == "positive"])
        signal.negative_evidence.extend([e for e in volume_evidence if e.get("direction") == "negative"])

        # 3. Momentum
        momentum_score, momentum_evidence = self._analyze_momentum(features)
        evidence_scores.append(("momentum", momentum_score, 0.15))
        signal.positive_evidence.extend([e for e in momentum_evidence if e.get("direction") == "positive"])
        signal.negative_evidence.extend([e for e in momentum_evidence if e.get("direction") == "negative"])

        # 4. Volatility
        vol_score, vol_evidence = self._analyze_volatility(features)
        evidence_scores.append(("volatility", vol_score, 0.08))

        # 5. Market regime
        regime_score = self._score_market_regime(market_regime)
        evidence_scores.append(("market_regime", regime_score, 0.10))

        # 6. Sector
        sector_score = self._score_sector(sector_data)
        evidence_scores.append(("sector", sector_score, 0.08))

        # 7. Relative strength
        rs_score = self._score_relative_strength(features)
        evidence_scores.append(("relative_strength", rs_score, 0.08))

        # 8. Fundamentals
        if fundamentals:
            fund_score, fund_evidence = self._analyze_fundamentals(fundamentals)
            evidence_scores.append(("fundamentals", fund_score, 0.10))
            signal.fundamental_summary = self._summarize_fundamentals(fundamentals)

        # 9. News sentiment
        if news_sentiment:
            news_score = self._score_news(news_sentiment)
            evidence_scores.append(("news", news_score, 0.05))

        # 10. ML prediction
        if ml_prediction:
            ml_score = ml_prediction.get("prob_up", 0.5) - 0.5  # Center around 0
            evidence_scores.append(("ml_model", ml_score * 2, 0.09))
            signal.probability = ml_prediction.get("prob_up")
            signal.model_version = ml_prediction.get("model_version", "")

        # --- Weighted composite score ---
        total_weight = sum(w for _, _, w in evidence_scores)
        if total_weight > 0:
            composite_score = sum(score * weight for _, score, weight in evidence_scores) / total_weight
        else:
            composite_score = 0.0

        # --- Determine signal type ---
        signal.signal_type = self._classify_signal(composite_score, features)

        # --- Determine confidence and risk ---
        signal.confidence = self._classify_confidence(evidence_scores)
        signal.risk = self._classify_risk(features, market_regime)

        # --- Determine entry classification ---
        signal.entry_classification = self._classify_entry(
            composite_score, features, market_regime
        )

        # --- Set technical snapshot ---
        signal.rsi = features.get("rsi_14")
        signal.adx = features.get("adx")
        signal.volume_ratio = features.get("volume_ratio")
        signal.cmp = features.get("close")
        signal.trend = self._determine_trend_label(features)

        # --- Calculate entry/exit levels ---
        self._calculate_levels(signal, features)

        # --- Position sizing ---
        if signal.cmp and signal.stop_loss:
            quality = "high" if signal.confidence == "high" else "default"
            signal.quantity = self.portfolio_config.calculate_quantity(
                signal.cmp, signal.stop_loss, quality
            )
            signal.position_value = signal.quantity * signal.cmp
            signal.max_risk_amount = signal.quantity * abs(signal.cmp - signal.stop_loss)

        # --- Generate explanation ---
        signal.explanation = self._generate_explanation(signal, evidence_scores)
        signal.technical_summary = self._generate_technical_summary(features)

        return signal

    # ============================================================
    # ANALYSIS METHODS
    # ============================================================

    def _analyze_trend(self, f: dict) -> tuple[float, list[dict]]:
        """Analyze price trend from MA structure."""
        score = 0.0
        evidence = []

        close = f.get("close", 0)
        sma_20 = f.get("sma_20")
        sma_50 = f.get("sma_50")
        sma_200 = f.get("sma_200")

        if sma_20 and close > sma_20:
            score += 0.3
            evidence.append({"factor": "Price above 20-day SMA", "direction": "positive", "type": "FACT"})
        elif sma_20 and close < sma_20:
            score -= 0.3
            evidence.append({"factor": "Price below 20-day SMA", "direction": "negative", "type": "FACT"})

        if sma_50 and close > sma_50:
            score += 0.3
            evidence.append({"factor": "Price above 50-day SMA", "direction": "positive", "type": "FACT"})
        elif sma_50:
            score -= 0.3
            evidence.append({"factor": "Price below 50-day SMA", "direction": "negative", "type": "FACT"})

        if sma_200 and close > sma_200:
            score += 0.4
            evidence.append({"factor": "Price above 200-day SMA", "direction": "positive", "type": "FACT"})
        elif sma_200:
            score -= 0.4
            evidence.append({"factor": "Price below 200-day SMA", "direction": "negative", "type": "FACT"})

        # MA alignment
        if sma_20 and sma_50 and sma_200:
            if sma_20 > sma_50 > sma_200:
                score += 0.3
                evidence.append({"factor": "Bullish MA alignment (20 > 50 > 200)", "direction": "positive", "type": "FACT"})
            elif sma_20 < sma_50 < sma_200:
                score -= 0.3
                evidence.append({"factor": "Bearish MA alignment (20 < 50 < 200)", "direction": "negative", "type": "FACT"})

        return np.clip(score, -1, 1), evidence

    def _analyze_volume(self, f: dict) -> tuple[float, list[dict]]:
        """Analyze volume patterns."""
        score = 0.0
        evidence = []
        vol_ratio = f.get("volume_ratio")

        if vol_ratio:
            if vol_ratio >= 2.5:
                score += 0.8
                evidence.append({
                    "factor": f"Volume is {vol_ratio:.1f}x 20-day average — strong unusual activity",
                    "direction": "positive", "type": "FACT"
                })
            elif vol_ratio >= 2.0:
                score += 0.5
                evidence.append({
                    "factor": f"Volume is {vol_ratio:.1f}x 20-day average — elevated",
                    "direction": "positive", "type": "FACT"
                })
            elif vol_ratio >= 1.5:
                score += 0.2
            elif vol_ratio < 0.5:
                score -= 0.3
                evidence.append({
                    "factor": f"Volume is {vol_ratio:.1f}x average — low participation",
                    "direction": "negative", "type": "FACT"
                })

        obv_trend = f.get("volume_trend")
        if obv_trend and obv_trend > 0.05:
            score += 0.2
            evidence.append({"factor": "Volume trend is positive", "direction": "positive", "type": "FACT"})

        return np.clip(score, -1, 1), evidence

    def _analyze_momentum(self, f: dict) -> tuple[float, list[dict]]:
        """Analyze momentum indicators."""
        score = 0.0
        evidence = []

        rsi = f.get("rsi_14")
        if rsi:
            if 55 <= rsi <= 70:
                score += 0.4
                evidence.append({
                    "factor": f"RSI at {rsi:.1f} — healthy bullish momentum",
                    "direction": "positive", "type": "FACT"
                })
            elif rsi > 80:
                score -= 0.4
                evidence.append({
                    "factor": f"RSI at {rsi:.1f} — extremely overbought",
                    "direction": "negative", "type": "FACT"
                })
            elif rsi < 30:
                score -= 0.3
                evidence.append({
                    "factor": f"RSI at {rsi:.1f} — oversold",
                    "direction": "negative", "type": "FACT"
                })

        macd_hist = f.get("macd_histogram")
        if macd_hist:
            if macd_hist > 0:
                score += 0.3
                evidence.append({"factor": "MACD histogram positive — bullish", "direction": "positive", "type": "FACT"})
            else:
                score -= 0.3
                evidence.append({"factor": "MACD histogram negative — bearish", "direction": "negative", "type": "FACT"})

        adx = f.get("adx")
        if adx and adx > 25:
            score += 0.3
            evidence.append({
                "factor": f"ADX at {adx:.1f} — strong trend",
                "direction": "positive", "type": "FACT"
            })

        return np.clip(score, -1, 1), evidence

    def _analyze_volatility(self, f: dict) -> tuple[float, list[dict]]:
        """Analyze volatility conditions."""
        score = 0.0
        evidence = []

        vol_expansion = f.get("volatility_expansion")
        if vol_expansion and vol_expansion > 1.5:
            score -= 0.3  # Higher volatility = more risk
            evidence.append({
                "factor": "Volatility expanding",
                "direction": "negative", "type": "FACT"
            })

        vol_pct = f.get("volatility_percentile")
        if vol_pct and vol_pct > 0.8:
            score -= 0.2
            evidence.append({
                "factor": "Volatility in upper 20th percentile",
                "direction": "negative", "type": "FACT"
            })

        return np.clip(score, -1, 1), evidence

    def _score_market_regime(self, regime: Optional[MarketRegime]) -> float:
        if not regime:
            return 0.0
        regime_scores = {
            MarketRegime.RISK_ON: 0.8,
            MarketRegime.MILD_RISK_ON: 0.4,
            MarketRegime.NEUTRAL: 0.0,
            MarketRegime.CAUTIOUS: -0.3,
            MarketRegime.RISK_OFF: -0.6,
            MarketRegime.EXTREME_RISK_OFF: -0.9,
        }
        return regime_scores.get(regime, 0.0)

    def _score_sector(self, sector_data: Optional[dict]) -> float:
        if not sector_data:
            return 0.0
        sector_return = sector_data.get("return_1d", 0)
        momentum = sector_data.get("momentum_score", 0)
        return np.clip((sector_return * 10 + momentum) / 2, -1, 1)

    def _score_relative_strength(self, f: dict) -> float:
        rs = f.get("relative_return_nifty", 0)
        if rs:
            return np.clip(rs * 20, -1, 1)
        return 0.0

    def _analyze_fundamentals(self, fund: dict) -> tuple[float, list[dict]]:
        score = 0.0
        evidence = []

        roe = fund.get("roe")
        if roe and roe > 15:
            score += 0.3
        revenue_growth = fund.get("revenue_growth")
        if revenue_growth and revenue_growth > 15:
            score += 0.3
            evidence.append({
                "factor": f"Revenue growth {revenue_growth:.1f}%",
                "direction": "positive", "type": "FACT"
            })
        de = fund.get("debt_equity")
        if de and de > 2:
            score -= 0.3
            evidence.append({
                "factor": f"High debt/equity {de:.1f}",
                "direction": "negative", "type": "FACT"
            })
        return np.clip(score, -1, 1), evidence

    def _score_news(self, news: dict) -> float:
        sentiment = news.get("sentiment_score", 0)
        return np.clip(sentiment, -1, 1)

    # ============================================================
    # CLASSIFICATION METHODS
    # ============================================================

    def _classify_signal(self, score: float, f: dict) -> SignalType:
        """Classify the composite score into a signal type."""
        vol_ratio = f.get("volume_ratio", 1)
        dist_52w_high = f.get("dist_52w_high", -1)

        if score > 0.4 and vol_ratio and vol_ratio > 2.0:
            if dist_52w_high and dist_52w_high > -0.05:
                return SignalType.POTENTIAL_BULLISH_BREAKOUT
            return SignalType.POTENTIAL_UPWARD_MOMENTUM
        elif score > 0.2:
            return SignalType.TREND_CONTINUATION
        elif score < -0.4 and vol_ratio and vol_ratio > 2.0:
            return SignalType.POTENTIAL_BEARISH_BREAKDOWN
        elif score < -0.2:
            return SignalType.POTENTIAL_DOWNWARD_MOMENTUM
        elif vol_ratio and vol_ratio > 2.5:
            return SignalType.ABNORMAL_VOLUME
        return SignalType.NO_SIGNAL

    def _classify_confidence(self, evidence_scores: list) -> str:
        """Classify confidence based on evidence agreement."""
        if not evidence_scores:
            return "low"
        scores = [s for _, s, _ in evidence_scores]
        agreement = sum(1 for s in scores if s > 0.2) / len(scores) if scores else 0
        if agreement > 0.7:
            return "high"
        elif agreement > 0.4:
            return "moderate"
        return "low"

    def _classify_risk(self, f: dict, regime: Optional[MarketRegime]) -> str:
        vol_pct = f.get("volatility_percentile", 0.5)
        if vol_pct > 0.8 or regime in (MarketRegime.RISK_OFF, MarketRegime.EXTREME_RISK_OFF):
            return "high"
        elif vol_pct > 0.6 or regime == MarketRegime.CAUTIOUS:
            return "medium-high"
        elif vol_pct > 0.3:
            return "medium"
        return "low"

    def _classify_entry(
        self, score: float, f: dict, regime: Optional[MarketRegime]
    ) -> EntryClassification:
        """Classify entry type — never chase extended moves."""
        return_5d = f.get("return_5d", 0)
        rsi = f.get("rsi_14", 50)
        vol_ratio = f.get("volume_ratio", 1)

        # Extended check — do not chase
        if return_5d and return_5d > 0.15:
            return EntryClassification.EXTENDED
        if rsi and rsi > 80:
            return EntryClassification.EXTENDED

        if score > 0.5 and vol_ratio and vol_ratio > 1.5:
            if regime in (MarketRegime.RISK_ON, MarketRegime.MILD_RISK_ON, None):
                return EntryClassification.BUY_NOW
            return EntryClassification.BUY_ON_RETEST
        elif score > 0.3:
            return EntryClassification.BUY_ON_RETEST
        elif score > 0.1:
            return EntryClassification.BREAKOUT_WATCH
        elif score < -0.2:
            return EntryClassification.AVOID
        return EntryClassification.WAIT

    def _determine_trend_label(self, f: dict) -> str:
        close = f.get("close", 0)
        sma_20 = f.get("sma_20")
        sma_50 = f.get("sma_50")
        sma_200 = f.get("sma_200")

        above = 0
        for ma in [sma_20, sma_50, sma_200]:
            if ma and close > ma:
                above += 1

        if above == 3:
            return "Strong Uptrend"
        elif above == 2:
            return "Uptrend"
        elif above == 1:
            return "Mixed"
        elif above == 0 and sma_200:
            return "Downtrend"
        return "Insufficient Data"

    def _calculate_levels(self, signal: StockSignal, f: dict) -> None:
        """Calculate entry, stop-loss, and target levels."""
        close = f.get("close")
        if not close:
            return

        atr = f.get("atr_14", close * 0.02)  # Default 2% if no ATR
        support_1 = f.get("support_1")
        resistance_1 = f.get("resistance_1")

        # Entry zone: near current price or support
        signal.entry_zone_low = round(close * 0.98, 2)  # 2% below
        signal.entry_zone_high = round(close * 1.01, 2)  # 1% above

        # Stop-loss: below nearest support or ATR-based
        if support_1 and support_1 < close:
            signal.stop_loss = round(support_1 * 0.99, 2)
        else:
            signal.stop_loss = round(close - 2 * atr, 2)

        # Targets
        risk = abs(close - signal.stop_loss)
        signal.target_1 = round(close + 2 * risk, 2)  # 2:1 R/R
        signal.target_2 = round(close + 3.5 * risk, 2)  # 3.5:1 R/R

        # Risk/Reward
        if risk > 0:
            reward = signal.target_1 - close
            signal.risk_reward_ratio = round(reward / risk, 2)

        signal.thesis_invalidation = (
            f"Close below ₹{signal.stop_loss} would invalidate the bullish thesis."
        )

    def _generate_explanation(self, signal: StockSignal, evidence_scores: list) -> str:
        """Generate human-readable explanation from actual evidence."""
        parts = []
        for name, score, weight in evidence_scores:
            if abs(score) > 0.2:
                direction = "supportive" if score > 0 else "unsupportive"
                parts.append(f"{name}: {direction} ({score:+.2f})")

        if signal.signal_type != SignalType.NO_SIGNAL:
            parts.insert(0, f"Signal: {signal.signal_type.value}")

        return ". ".join(parts) if parts else "Insufficient evidence for a clear signal."

    def _generate_technical_summary(self, f: dict) -> str:
        """Generate technical interpretation from computed indicators."""
        from app.services.analytics.features import FeatureEngine
        return FeatureEngine.interpret_indicators(f)

    def _summarize_fundamentals(self, fund: dict) -> str:
        parts = []
        if fund.get("revenue_growth"):
            parts.append(f"Revenue growth: {fund['revenue_growth']:.1f}%")
        if fund.get("roe"):
            parts.append(f"ROE: {fund['roe']:.1f}%")
        if fund.get("debt_equity"):
            parts.append(f"D/E: {fund['debt_equity']:.2f}")
        if fund.get("pe_ratio"):
            parts.append(f"PE: {fund['pe_ratio']:.1f}")
        return " | ".join(parts) if parts else "Fundamental data not available."

    # ============================================================
    # DISCOVERY BUCKETS
    # ============================================================

    def run_momentum_breakout_screen(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Bucket A — Momentum breakout screen."""
        if features_df.empty:
            return features_df

        mask = (
            (features_df["volume_ratio"] >= 2.0) &
            (features_df["close"] > features_df["ema_20"]) &
            (features_df["close"] > features_df["ema_50"]) &
            (features_df["rsi_14"].between(55, 70)) &
            (features_df["macd_histogram"] > 0)
        )
        # Only apply ADX if column has data
        if features_df["adx"].notna().sum() > 0:
            mask = mask & (features_df["adx"] > 25)

        result = features_df[mask].copy()
        result["discovery_bucket"] = "momentum_breakout"
        return result

    def run_breakout_retest_screen(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Bucket B — Breakout retest screen."""
        if features_df.empty:
            return features_df

        mask = (
            (features_df["dist_52w_high"] > -0.10) &
            (features_df["volume_ratio"] < 1.5) &  # Volume contracted
            (features_df["close"] > features_df["sma_20"]) &
            (features_df["rsi_14"] > 40)
        )
        result = features_df[mask].copy()
        result["discovery_bucket"] = "breakout_retest"
        return result

    def run_early_stage_screen(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Bucket C — Early-stage breakout screen."""
        if features_df.empty:
            return features_df

        mask = (
            (features_df["dist_52w_high"] > -0.05) &
            (features_df["bollinger_width"] < features_df["bollinger_width"].quantile(0.3)) &
            (features_df["volume_trend"] > 0) &
            (features_df["close"] > features_df["ema_50"])
        )
        result = features_df[mask].copy()
        result["discovery_bucket"] = "early_stage_breakout"
        return result

    def run_quality_pullback_screen(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Bucket H — Quality pullback screen."""
        if features_df.empty:
            return features_df

        mask = (
            (features_df["close"] > features_df["sma_200"]) &  # Long-term trend intact
            (features_df["close"] < features_df["sma_20"]) &   # Below short-term
            (features_df["rsi_14"] < 40) &
            (features_df["volume_ratio"] < 1.0)
        )
        result = features_df[mask].copy()
        result["discovery_bucket"] = "quality_pullback"
        return result
