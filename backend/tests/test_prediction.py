"""
StockMind AI — Unit Tests for ML Prediction Engine
"""

import pytest

from app.services.ml.prediction_engine import EnsemblePredictionEngine, PredictionResult


class TestPredictionEngine:
    def setup_method(self):
        self.engine = EnsemblePredictionEngine()

    def test_prediction_returns_result(self):
        features = {
            "instrument_key": "NSE_EQ|RELIANCE",
            "symbol": "RELIANCE",
            "close": 2500,
            "sma_20": 2450,
            "sma_50": 2400,
            "sma_200": 2200,
            "rsi_14": 60,
            "macd_histogram": 3.0,
            "volume_ratio": 1.5,
            "volatility_20d": 0.22,
            "volatility_percentile": 0.4,
            "return_1d": 0.01,
        }
        result = self.engine.predict(features, horizon="1D")
        assert isinstance(result, PredictionResult)

    def test_probabilities_sum_to_one(self):
        features = {
            "close": 100,
            "sma_20": 98,
            "sma_50": 95,
            "sma_200": 90,
            "rsi_14": 55,
            "macd_histogram": 1.0,
            "volatility_20d": 0.20,
        }
        result = self.engine.predict(features)
        total = result.prob_up + result.prob_flat + result.prob_down
        assert abs(total - 1.0) < 0.01

    def test_probabilities_bounded(self):
        features = {"close": 100, "sma_200": 50, "rsi_14": 90}
        result = self.engine.predict(features)
        assert 0 <= result.prob_up <= 1
        assert 0 <= result.prob_down <= 1
        assert 0 <= result.prob_flat <= 1

    def test_never_returns_certainty(self):
        """Model must never claim 100% or 0% probability."""
        for rsi in [10, 30, 50, 70, 90]:
            features = {"close": 100, "rsi_14": rsi, "sma_20": 100}
            result = self.engine.predict(features)
            assert result.prob_up < 1.0
            assert result.prob_up > 0.0
            assert result.prob_down < 1.0
            assert result.prob_down > 0.0

    def test_prediction_interval_lower_less_than_upper(self):
        features = {"close": 100, "volatility_20d": 0.25}
        result = self.engine.predict(features)
        assert result.prediction_interval_lower < result.prediction_interval_upper

    def test_scenarios_generated(self):
        features = {
            "close": 100,
            "volatility_20d": 0.25,
            "support_1": 95,
            "resistance_1": 108,
        }
        result = self.engine.predict(features)
        assert result.bull_scenario != ""
        assert result.base_scenario != ""
        assert result.bear_scenario != ""

    def test_to_dict_has_disclaimer(self):
        features = {"close": 100}
        result = self.engine.predict(features)
        d = result.to_dict()
        assert "_disclaimer" in d
        assert "certainties" in d["_disclaimer"].lower() or "uncertainty" in d["_disclaimer"].lower()

    def test_explanation_generated(self):
        features = {
            "close": 100,
            "sma_50": 95,
            "sma_200": 90,
            "rsi_14": 62,
            "macd_histogram": 2.0,
            "volume_ratio": 2.5,
        }
        result = self.engine.predict(features)
        assert result.explanation_text != ""
        assert len(result.key_positive_factors) > 0

    def test_empty_features_max_uncertainty(self):
        """No data = maximum uncertainty = prob near 0.5."""
        result = self.engine.predict({"close": 100})
        assert abs(result.prob_up - 0.5) < 0.15

    def test_longer_horizons_more_uncertain(self):
        features = {"close": 100, "sma_20": 105, "rsi_14": 65}
        result_1d = self.engine.predict(features, horizon="1D")
        result_20d = self.engine.predict(features, horizon="20D")
        # Longer horizon should have wider prediction interval
        width_1d = result_1d.prediction_interval_upper - result_1d.prediction_interval_lower
        width_20d = result_20d.prediction_interval_upper - result_20d.prediction_interval_lower
        assert width_20d >= width_1d

    def test_feature_snapshot_stored(self):
        features = {
            "instrument_key": "NSE_EQ|TEST",
            "close": 100,
            "rsi_14": 60,
            "timestamp": "2024-01-01T00:00:00",
        }
        result = self.engine.predict(features)
        assert result.feature_snapshot is not None
        assert "close" in result.feature_snapshot
        assert "rsi_14" in result.feature_snapshot
        # timestamp should NOT be in snapshot (it's metadata)
        assert "timestamp" not in result.feature_snapshot
