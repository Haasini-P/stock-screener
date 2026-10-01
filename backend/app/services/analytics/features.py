"""
StockMind AI — Technical Analysis Feature Engine
Computes all technical indicators and features from OHLCV data.
Every feature has a defined "as-of timestamp" to prevent look-ahead bias.
"""

from typing import Optional

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


class FeatureEngine:
    """
    Compute technical features from OHLCV data.

    All features are computed point-in-time — only using data
    available at or before the timestamp. No look-ahead bias.
    """

    @staticmethod
    def compute_all_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all technical features from a DataFrame with OHLCV columns.

        Expected columns: timestamp, open, high, low, close, volume
        Returns DataFrame with all computed features.
        """
        if df.empty or len(df) < 20:
            logger.warning("insufficient_data_for_features", rows=len(df))
            return df

        df = df.copy().sort_values("timestamp").reset_index(drop=True)

        # --- Price Features ---
        df = FeatureEngine._price_features(df)

        # --- Moving Averages ---
        df = FeatureEngine._moving_averages(df)

        # --- Momentum Indicators ---
        df = FeatureEngine._momentum_indicators(df)

        # --- Volatility Indicators ---
        df = FeatureEngine._volatility_indicators(df)

        # --- Volume Features ---
        df = FeatureEngine._volume_features(df)

        # --- Support / Resistance ---
        df = FeatureEngine._support_resistance(df)

        # --- 52-Week Statistics ---
        df = FeatureEngine._52week_stats(df)

        return df

    @staticmethod
    def _price_features(df: pd.DataFrame) -> pd.DataFrame:
        """Compute price-derived features."""
        c = df["close"]
        o = df["open"]
        h = df["high"]
        l = df["low"]

        # Returns
        df["return_1d"] = c.pct_change(1)
        df["return_5d"] = c.pct_change(5)
        df["return_10d"] = c.pct_change(10)
        df["return_20d"] = c.pct_change(20)
        df["log_return_1d"] = np.log(c / c.shift(1))

        # Gap
        df["gap"] = (o - c.shift(1)) / c.shift(1)

        # Candle analysis
        body = (c - o).abs()
        full_range = h - l
        full_range = full_range.replace(0, np.nan)

        df["candle_body_ratio"] = body / full_range
        df["upper_wick_ratio"] = (h - pd.concat([c, o], axis=1).max(axis=1)) / full_range
        df["lower_wick_ratio"] = (pd.concat([c, o], axis=1).min(axis=1) - l) / full_range
        df["range_pct"] = full_range / c

        # Rolling returns
        for window in [5, 10, 20, 60]:
            df[f"rolling_return_{window}d"] = c.pct_change(window)

        return df

    @staticmethod
    def _moving_averages(df: pd.DataFrame) -> pd.DataFrame:
        """Compute moving averages and distances."""
        c = df["close"]

        # Simple Moving Averages
        for period in [10, 20, 50, 100, 200]:
            col = f"sma_{period}"
            df[col] = c.rolling(window=period, min_periods=period).mean()
            df[f"dist_sma_{period}"] = (c - df[col]) / df[col]

        # Exponential Moving Averages
        for period in [9, 20, 50]:
            col = f"ema_{period}"
            df[col] = c.ewm(span=period, adjust=False).mean()
            df[f"dist_ema_{period}"] = (c - df[col]) / df[col]

        # MA slopes (rate of change of the MA itself)
        for period in [20, 50, 200]:
            ma_col = f"sma_{period}"
            if ma_col in df.columns:
                df[f"slope_sma_{period}"] = df[ma_col].pct_change(5)

        # Golden / Death cross signals
        if "sma_50" in df.columns and "sma_200" in df.columns:
            df["ma_cross_50_200"] = (
                (df["sma_50"] > df["sma_200"]).astype(int)
                - (df["sma_50"] > df["sma_200"]).shift(1, fill_value=False).astype(int)
            )

        return df

    @staticmethod
    def _momentum_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Compute momentum indicators."""
        c = df["close"]
        h = df["high"]
        l = df["low"]

        # RSI
        df["rsi_14"] = FeatureEngine._rsi(c, 14)

        # MACD
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        # Stochastic Oscillator
        low_14 = l.rolling(14).min()
        high_14 = h.rolling(14).max()
        denom = high_14 - low_14
        denom = denom.replace(0, np.nan)
        df["stochastic_k"] = ((c - low_14) / denom) * 100
        df["stochastic_d"] = df["stochastic_k"].rolling(3).mean()

        # ADX (Average Directional Index)
        df["adx"] = FeatureEngine._adx(h, l, c, 14)

        # Rate of Change
        df["roc_10"] = ((c - c.shift(10)) / c.shift(10)) * 100
        df["roc_20"] = ((c - c.shift(20)) / c.shift(20)) * 100

        # Williams %R
        df["williams_r"] = ((high_14 - c) / denom) * -100

        return df

    @staticmethod
    def _volatility_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Compute volatility indicators."""
        c = df["close"]
        h = df["high"]
        l = df["low"]

        # ATR
        df["atr_14"] = FeatureEngine._atr(h, l, c, 14)

        # Bollinger Bands
        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        df["bollinger_upper"] = sma20 + 2 * std20
        df["bollinger_lower"] = sma20 - 2 * std20
        df["bollinger_width"] = (df["bollinger_upper"] - df["bollinger_lower"]) / sma20
        bb_range = df["bollinger_upper"] - df["bollinger_lower"]
        bb_range = bb_range.replace(0, np.nan)
        df["bollinger_pct_b"] = (c - df["bollinger_lower"]) / bb_range

        # Historical volatility
        log_returns = np.log(c / c.shift(1))
        df["volatility_20d"] = log_returns.rolling(20).std() * np.sqrt(252)
        df["volatility_60d"] = log_returns.rolling(60).std() * np.sqrt(252)

        # Volatility percentile (where current vol sits in 1-year range)
        vol_250 = log_returns.rolling(20).std()
        vol_250_rolling_max = vol_250.rolling(252, min_periods=60).max()
        vol_250_rolling_min = vol_250.rolling(252, min_periods=60).min()
        denom = vol_250_rolling_max - vol_250_rolling_min
        denom = denom.replace(0, np.nan)
        df["volatility_percentile"] = (vol_250 - vol_250_rolling_min) / denom

        # Volatility expansion (current vs 60d average)
        avg_vol = vol_250.rolling(60).mean()
        avg_vol_safe = avg_vol.replace(0, np.nan)
        df["volatility_expansion"] = vol_250 / avg_vol_safe

        return df

    @staticmethod
    def _volume_features(df: pd.DataFrame) -> pd.DataFrame:
        """Compute volume-derived features."""
        v = df["volume"].astype(float)
        c = df["close"]

        # Volume ratio (relative to 20-day SMA)
        vol_sma20 = v.rolling(20).mean()
        vol_sma20_safe = vol_sma20.replace(0, np.nan)
        df["volume_ratio"] = v / vol_sma20_safe

        # Volume z-score
        vol_std = v.rolling(20).std()
        vol_std_safe = vol_std.replace(0, np.nan)
        df["volume_zscore"] = (v - vol_sma20) / vol_std_safe

        # OBV (On-Balance Volume)
        direction = np.sign(c.diff())
        df["obv"] = (direction * v).cumsum()

        # Volume trend (slope of volume SMA)
        df["volume_trend"] = vol_sma20.pct_change(5)

        # VWAP proxy (approximate using available data)
        typical_price = (df["high"] + df["low"] + c) / 3
        cum_tp_vol = (typical_price * v).cumsum()
        cum_vol = v.cumsum()
        cum_vol_safe = cum_vol.replace(0, np.nan)
        df["vwap"] = cum_tp_vol / cum_vol_safe

        return df

    @staticmethod
    def _support_resistance(df: pd.DataFrame) -> pd.DataFrame:
        """Compute pivot points and S/R levels."""
        h = df["high"].shift(1)  # Previous day's high
        l = df["low"].shift(1)   # Previous day's low
        c = df["close"].shift(1)  # Previous day's close

        # Standard pivot points
        df["pivot_point"] = (h + l + c) / 3
        df["support_1"] = 2 * df["pivot_point"] - h
        df["support_2"] = df["pivot_point"] - (h - l)
        df["resistance_1"] = 2 * df["pivot_point"] - l
        df["resistance_2"] = df["pivot_point"] + (h - l)

        return df

    @staticmethod
    def _52week_stats(df: pd.DataFrame) -> pd.DataFrame:
        """Compute 52-week high/low statistics."""
        c = df["close"]
        h = df["high"]
        l = df["low"]

        # 52-week (252 trading days) high/low
        df["high_52w"] = h.rolling(252, min_periods=60).max()
        df["low_52w"] = l.rolling(252, min_periods=60).min()

        high_safe = df["high_52w"].replace(0, np.nan)
        low_safe = df["low_52w"].replace(0, np.nan)

        df["dist_52w_high"] = (c - df["high_52w"]) / high_safe
        df["dist_52w_low"] = (c - df["low_52w"]) / low_safe

        return df

    # --- Helper indicator calculations ---

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()

        avg_loss_safe = avg_loss.replace(0, np.nan)
        rs = avg_gain / avg_loss_safe
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index."""
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        # Where +DM > -DM, -DM = 0 and vice versa
        mask = plus_dm > minus_dm
        minus_dm[mask] = 0
        plus_dm[~mask] = 0

        atr = FeatureEngine._atr(high, low, close, period)
        atr_safe = atr.replace(0, np.nan)

        plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr_safe)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period).mean() / atr_safe)

        di_sum = plus_di + minus_di
        di_sum_safe = di_sum.replace(0, np.nan)
        dx = 100 * ((plus_di - minus_di).abs() / di_sum_safe)

        return dx.ewm(alpha=1/period).mean()

    @staticmethod
    def get_feature_names() -> list[str]:
        """Return the list of all computed feature names."""
        return [
            # Price
            "return_1d", "return_5d", "return_10d", "return_20d", "log_return_1d",
            "gap", "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio", "range_pct",
            "rolling_return_5d", "rolling_return_10d", "rolling_return_20d", "rolling_return_60d",
            # Moving averages
            "sma_10", "sma_20", "sma_50", "sma_100", "sma_200",
            "ema_9", "ema_20", "ema_50",
            "dist_sma_10", "dist_sma_20", "dist_sma_50", "dist_sma_100", "dist_sma_200",
            "dist_ema_9", "dist_ema_20", "dist_ema_50",
            "slope_sma_20", "slope_sma_50", "slope_sma_200",
            "ma_cross_50_200",
            # Momentum
            "rsi_14", "macd", "macd_signal", "macd_histogram",
            "stochastic_k", "stochastic_d", "adx", "roc_10", "roc_20", "williams_r",
            # Volatility
            "atr_14", "bollinger_upper", "bollinger_lower", "bollinger_width", "bollinger_pct_b",
            "volatility_20d", "volatility_60d", "volatility_percentile", "volatility_expansion",
            # Volume
            "volume_ratio", "volume_zscore", "obv", "volume_trend", "vwap",
            # Support / Resistance
            "pivot_point", "support_1", "support_2", "resistance_1", "resistance_2",
            # 52-week
            "high_52w", "low_52w", "dist_52w_high", "dist_52w_low",
        ]

    @staticmethod
    def interpret_indicators(features: dict) -> str:
        """
        Generate a human-readable interpretation of technical indicators.
        This is based on actual computed values — never fabricated.
        """
        interpretations = []

        # Trend analysis
        close = features.get("close", 0)
        sma_20 = features.get("sma_20")
        sma_50 = features.get("sma_50")
        sma_200 = features.get("sma_200")

        above_count = 0
        below_count = 0
        for ma_name, ma_val in [("20-day SMA", sma_20), ("50-day SMA", sma_50), ("200-day SMA", sma_200)]:
            if ma_val and close:
                if close > ma_val:
                    above_count += 1
                else:
                    below_count += 1

        if above_count == 3:
            interpretations.append(
                "Price is above the 20/50/200-day moving averages, indicating a positive medium/long-term trend."
            )
        elif below_count == 3:
            interpretations.append(
                "Price is below all major moving averages, suggesting a negative trend environment."
            )
        elif above_count >= 2:
            interpretations.append(
                "Price is above most major moving averages, suggesting a generally positive trend."
            )

        # RSI
        rsi = features.get("rsi_14")
        if rsi:
            if rsi > 70:
                interpretations.append(f"RSI at {rsi:.1f} is in overbought territory, suggesting potential overextension.")
            elif rsi > 60:
                interpretations.append(f"RSI at {rsi:.1f} shows positive momentum but approaching overbought.")
            elif rsi < 30:
                interpretations.append(f"RSI at {rsi:.1f} is in oversold territory, suggesting potential overselling.")
            elif rsi < 40:
                interpretations.append(f"RSI at {rsi:.1f} shows weak momentum.")
            else:
                interpretations.append(f"RSI at {rsi:.1f} is in neutral territory.")

        # MACD
        macd_hist = features.get("macd_histogram")
        if macd_hist:
            if macd_hist > 0:
                interpretations.append("MACD histogram is positive, supporting bullish momentum.")
            else:
                interpretations.append("MACD histogram is negative, suggesting bearish momentum pressure.")

        # Volume
        vol_ratio = features.get("volume_ratio")
        if vol_ratio:
            if vol_ratio > 2.0:
                interpretations.append(f"Volume is {vol_ratio:.1f}x the 20-day average — unusually high activity.")
            elif vol_ratio > 1.5:
                interpretations.append(f"Volume is {vol_ratio:.1f}x average — elevated interest.")
            elif vol_ratio < 0.5:
                interpretations.append(f"Volume is {vol_ratio:.1f}x average — below-average participation.")

        # Volatility
        vol_pct = features.get("volatility_percentile")
        if vol_pct is not None:
            if vol_pct > 0.8:
                interpretations.append("Volatility is in the upper 20th percentile of the past year — high-risk environment.")
            elif vol_pct < 0.2:
                interpretations.append("Volatility is low relative to the past year — potential for expansion.")

        # Bollinger
        bb_pct = features.get("bollinger_pct_b")
        if bb_pct is not None:
            if bb_pct > 1.0:
                interpretations.append("Price has broken above the upper Bollinger Band — extended move.")
            elif bb_pct < 0.0:
                interpretations.append("Price is below the lower Bollinger Band — extended to the downside.")

        # ADX
        adx_val = features.get("adx")
        if adx_val:
            if adx_val > 25:
                interpretations.append(f"ADX at {adx_val:.1f} indicates a strong trend.")
            else:
                interpretations.append(f"ADX at {adx_val:.1f} suggests a weak or sideways trend.")

        return " ".join(interpretations) if interpretations else "Insufficient indicator data for interpretation."
