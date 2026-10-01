"""
StockMind AI — Unit Tests for Technical Feature Engine
"""

import numpy as np
import pandas as pd
import pytest

from app.services.analytics.features import FeatureEngine


def _make_sample_df(n: int = 300) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range(start="2023-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.8)
    low = close - np.abs(np.random.randn(n) * 0.8)
    open_ = close + np.random.randn(n) * 0.3
    volume = np.random.randint(100000, 1000000, n)

    return pd.DataFrame({
        "timestamp": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestFeatureEngine:
    """Tests for the technical feature computation engine."""

    def test_compute_all_features_returns_dataframe(self):
        df = _make_sample_df()
        result = FeatureEngine.compute_all_features(df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(df)

    def test_insufficient_data_returns_input(self):
        df = _make_sample_df(10)  # Too few rows
        result = FeatureEngine.compute_all_features(df)
        assert len(result) == 10

    def test_sma_computed_correctly(self):
        df = _make_sample_df()
        result = FeatureEngine.compute_all_features(df)

        # SMA 20 should be the mean of the last 20 closes
        expected_sma_20 = df["close"].rolling(20).mean().iloc[-1]
        actual_sma_20 = result["sma_20"].iloc[-1]
        assert abs(expected_sma_20 - actual_sma_20) < 0.01

    def test_rsi_range(self):
        df = _make_sample_df()
        result = FeatureEngine.compute_all_features(df)
        rsi = result["rsi_14"].dropna()
        assert rsi.min() >= 0
        assert rsi.max() <= 100

    def test_bollinger_bands(self):
        df = _make_sample_df()
        result = FeatureEngine.compute_all_features(df)
        valid = result.dropna(subset=["bollinger_upper", "bollinger_lower"])
        assert (valid["bollinger_upper"] >= valid["bollinger_lower"]).all()

    def test_volume_ratio_positive(self):
        df = _make_sample_df()
        result = FeatureEngine.compute_all_features(df)
        vol_ratio = result["volume_ratio"].dropna()
        assert (vol_ratio > 0).all()

    def test_returns_correct(self):
        df = _make_sample_df()
        result = FeatureEngine.compute_all_features(df)
        # 1-day return = (close[t] - close[t-1]) / close[t-1]
        expected = df["close"].pct_change(1).iloc[-1]
        actual = result["return_1d"].iloc[-1]
        assert abs(expected - actual) < 1e-10

    def test_no_future_leakage_in_pivot_points(self):
        """Pivot points should use previous day's data, not current."""
        df = _make_sample_df()
        result = FeatureEngine.compute_all_features(df)
        # Pivot = (prev_high + prev_low + prev_close) / 3
        prev_high = df["high"].iloc[-2]
        prev_low = df["low"].iloc[-2]
        prev_close = df["close"].iloc[-2]
        expected_pivot = (prev_high + prev_low + prev_close) / 3
        actual_pivot = result["pivot_point"].iloc[-1]
        assert abs(expected_pivot - actual_pivot) < 0.01

    def test_feature_names_list(self):
        names = FeatureEngine.get_feature_names()
        assert len(names) > 50
        assert "rsi_14" in names
        assert "sma_200" in names
        assert "volume_ratio" in names

    def test_interpret_indicators_with_data(self):
        features = {
            "close": 150,
            "sma_20": 145,
            "sma_50": 140,
            "sma_200": 130,
            "rsi_14": 65,
            "macd_histogram": 2.5,
            "volume_ratio": 2.1,
            "volatility_percentile": 0.4,
            "adx": 30,
        }
        text = FeatureEngine.interpret_indicators(features)
        assert len(text) > 0
        assert "moving average" in text.lower() or "ma" in text.lower() or "sma" in text.lower()

    def test_interpret_indicators_empty(self):
        text = FeatureEngine.interpret_indicators({})
        assert "Insufficient" in text


class TestFeatureEngineEdgeCases:
    """Edge case tests."""

    def test_zero_volume(self):
        df = _make_sample_df()
        df["volume"] = 0
        result = FeatureEngine.compute_all_features(df)
        assert isinstance(result, pd.DataFrame)

    def test_constant_price(self):
        df = _make_sample_df()
        df["close"] = 100
        df["open"] = 100
        df["high"] = 100
        df["low"] = 100
        result = FeatureEngine.compute_all_features(df)
        assert isinstance(result, pd.DataFrame)

    def test_negative_prices_handled(self):
        """Ensure engine handles malformed data gracefully."""
        df = _make_sample_df()
        df.loc[0, "close"] = -1  # Invalid
        result = FeatureEngine.compute_all_features(df)
        assert isinstance(result, pd.DataFrame)
