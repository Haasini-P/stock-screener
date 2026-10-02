"""
StockMind AI — Unit Tests for Signal Engine
"""

import pytest

from app.services.analytics.signals import (
    SignalEngine,
    PortfolioConfig,
    EntryClassification,
    MarketRegime,
    SignalType,
    holding_action_for_entry,
)


class TestPortfolioConfig:
    def test_default_capital(self):
        config = PortfolioConfig()
        assert config.total_capital == 200000.0

    def test_max_loss_default(self):
        config = PortfolioConfig()
        assert config.max_loss_default == 1500.0

    def test_position_sizing(self):
        config = PortfolioConfig()
        # Entry at 100, stop at 95, risk per share = 5
        # Max loss = 1500, so quantity = 300
        qty = config.calculate_quantity(100.0, 95.0)
        assert qty == 300

    def test_position_sizing_high_quality(self):
        config = PortfolioConfig()
        qty = config.calculate_quantity(100.0, 95.0, "high")
        assert qty == 400  # Max loss = 2000, risk = 5

    def test_position_sizing_zero_risk(self):
        config = PortfolioConfig()
        qty = config.calculate_quantity(100.0, 100.0)
        assert qty == 0


class TestSignalEngine:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_holding_gets_full_analysis_not_blanket_avoid(self):
        """A held symbol must still get a real computed signal — see
        holding_action_for_entry for how it's relabeled for display."""
        features = {
            "symbol": "RELIANCE",
            "name": "Reliance Industries",
            "sector": "Energy",
            "close": 2500,
            "sma_20": 2450,
            "sma_50": 2400,
            "sma_200": 2200,
            "rsi_14": 62,
            "macd_histogram": 5.0,
            "adx": 28,
            "volume_ratio": 2.2,
            "volatility_percentile": 0.4,
            "atr_14": 30,
            "support_1": 2420,
            "resistance_1": 2580,
            "return_5d": 0.03,
        }
        not_held = self.engine.generate_signal(features)
        held = self.engine.generate_signal(features, held_symbols={"RELIANCE"})

        assert not_held.is_holding is False
        assert not_held.holding_action is None
        assert held.is_holding is True
        # Same technicals in, same entry classification out — only the holding label differs.
        assert held.entry_classification == not_held.entry_classification
        assert held.holding_action == holding_action_for_entry(held.entry_classification)

    def test_holding_action_mapping(self):
        assert holding_action_for_entry(EntryClassification.BUY_NOW) == "ADD"
        assert holding_action_for_entry(EntryClassification.BUY_ON_RETEST) == "ADD"
        assert holding_action_for_entry(EntryClassification.BUY_ON_DIP) == "ADD"
        assert holding_action_for_entry(EntryClassification.WAIT) == "HOLD"
        assert holding_action_for_entry(EntryClassification.BREAKOUT_WATCH) == "HOLD"
        assert holding_action_for_entry(EntryClassification.EXTENDED) == "HOLD"
        assert holding_action_for_entry(EntryClassification.AVOID) == "REDUCE"
        # Also accepts the raw string form (used by route-level code on cached row dicts)
        assert holding_action_for_entry("BUY_NOW") == "ADD"
        assert holding_action_for_entry("AVOID") == "REDUCE"

    def test_generate_signal_basic(self):
        features = {
            "symbol": "RELIANCE",
            "name": "Reliance Industries",
            "sector": "Energy",
            "close": 2500,
            "sma_20": 2450,
            "sma_50": 2400,
            "sma_200": 2200,
            "rsi_14": 62,
            "macd_histogram": 5.0,
            "adx": 28,
            "volume_ratio": 2.2,
            "volatility_percentile": 0.4,
            "atr_14": 30,
            "support_1": 2420,
            "resistance_1": 2580,
            "return_5d": 0.03,
        }
        signal = self.engine.generate_signal(features)
        assert signal.symbol == "RELIANCE"
        assert signal.signal_type != SignalType.NO_SIGNAL
        assert signal.stop_loss is not None
        assert signal.target_1 is not None
        assert signal.quantity >= 0

    def test_extended_move_not_chased(self):
        features = {
            "symbol": "TEST",
            "name": "Test Stock",
            "close": 100,
            "return_5d": 0.20,  # 20% in 5 days = extended
            "rsi_14": 85,
            "sma_20": 90,
            "sma_50": 85,
            "volume_ratio": 3.0,
            "macd_histogram": 5,
        }
        signal = self.engine.generate_signal(features)
        assert signal.entry_classification == EntryClassification.EXTENDED

    def test_risk_off_regime_affects_signal(self):
        features = {
            "symbol": "TEST",
            "name": "Test Stock",
            "close": 100,
            "sma_20": 98,
            "sma_50": 95,
            "sma_200": 90,
            "rsi_14": 60,
            "volume_ratio": 1.5,
            "volatility_percentile": 0.5,
        }
        signal = self.engine.generate_signal(
            features,
            market_regime=MarketRegime.RISK_OFF,
        )
        # In risk-off, should not be BUY_NOW
        assert signal.entry_classification != EntryClassification.BUY_NOW

    def test_signal_to_dict_has_required_fields(self):
        features = {
            "symbol": "TEST",
            "name": "Test Stock",
            "close": 100,
            "sma_20": 98,
        }
        signal = self.engine.generate_signal(features)
        d = signal.to_dict()
        assert "symbol" in d
        assert "signal" in d
        assert "evidence" in d
        assert "prediction" in d
        assert d["prediction"]["_type"] == "MODEL_PREDICTION"
        assert d["entry_exit"]["_type"] == "ANALYST_INTERPRETATION"


class TestExistingHoldings:
    """
    Holdings are no longer a hardcoded list — "is this held" is resolved by
    the caller from the user's live, connected broker account (see
    app/services/portfolio_holdings.py) and passed into generate_signal() as
    held_symbols. SignalEngine itself does no holdings lookup or I/O.
    """

    def test_held_symbols_is_exact_match_not_substring(self):
        engine = SignalEngine()
        held = engine.generate_signal(
            {"symbol": "TCS", "name": "Tata Consultancy Services", "close": 100},
            held_symbols={"TCS"},
        )
        not_held = engine.generate_signal(
            {"symbol": "TCSADV", "name": "Some Other Company", "close": 100},
            held_symbols={"TCS"},
        )
        assert held.is_holding is True
        assert not_held.is_holding is False
