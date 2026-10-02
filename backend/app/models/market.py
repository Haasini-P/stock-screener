"""
StockMind AI — Market Data Models
Database models for instruments, market ticks, candles, and technical features.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from app.models.compat import CompatUUID as UUID, CompatJSON as JSON
from sqlalchemy.sql import func

from app.database import Base


class Instrument(Base):
    """Tradeable instrument metadata from Upstox."""

    __tablename__ = "instruments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instrument_key = Column(String(100), unique=True, nullable=False, index=True)
    exchange = Column(String(10), nullable=False, index=True)  # NSE, BSE, NFO, MCX
    trading_symbol = Column(String(100), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    instrument_type = Column(String(50), nullable=True)  # EQ, FUT, OPT, IDX
    isin = Column(String(20), nullable=True, index=True)
    lot_size = Column(Integer, nullable=True)
    tick_size = Column(Float, nullable=True)
    exchange_token = Column(String(50), nullable=True)
    segment = Column(String(20), nullable=True)
    sector = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)

    # Expiry for derivatives
    expiry = Column(DateTime, nullable=True)
    strike_price = Column(Float, nullable=True)
    option_type = Column(String(5), nullable=True)  # CE, PE

    is_active = Column(Boolean, default=True, nullable=False)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_instruments_exchange_symbol", "exchange", "trading_symbol"),
        Index("ix_instruments_type", "instrument_type"),
    )


class Candle(Base):
    """Historical and intraday OHLCV candle data."""

    __tablename__ = "candles"

    # Plain Integer, not BigInteger: SQLite only aliases a PRIMARY KEY column to
    # its auto-incrementing rowid when it's declared as INTEGER — BigInteger
    # (BIGINT) breaks that and every insert fails with "NOT NULL constraint
    # failed: candles.id". Fine on Postgres too (SERIAL-equivalent either way).
    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_key = Column(String(100), nullable=False, index=True)
    interval = Column(String(10), nullable=False)  # 1minute, 30minute, day, week, month
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)
    oi = Column(BigInteger, nullable=True)  # Open interest for derivatives

    __table_args__ = (
        Index("ix_candles_instrument_interval_ts", "instrument_key", "interval", "timestamp", unique=True),
        Index("ix_candles_ts", "timestamp"),
    )


class TechnicalFeature(Base):
    """Pre-computed technical features for ML pipeline."""

    __tablename__ = "technical_features"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    instrument_key = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    feature_version = Column(String(20), nullable=False, default="v1")

    # Price features
    return_1d = Column(Float, nullable=True)
    return_5d = Column(Float, nullable=True)
    return_10d = Column(Float, nullable=True)
    return_20d = Column(Float, nullable=True)
    log_return_1d = Column(Float, nullable=True)
    gap = Column(Float, nullable=True)
    candle_body_ratio = Column(Float, nullable=True)
    upper_wick_ratio = Column(Float, nullable=True)
    lower_wick_ratio = Column(Float, nullable=True)
    range_pct = Column(Float, nullable=True)

    # Moving averages
    sma_10 = Column(Float, nullable=True)
    sma_20 = Column(Float, nullable=True)
    sma_50 = Column(Float, nullable=True)
    sma_100 = Column(Float, nullable=True)
    sma_200 = Column(Float, nullable=True)
    ema_9 = Column(Float, nullable=True)
    ema_20 = Column(Float, nullable=True)
    ema_50 = Column(Float, nullable=True)

    # Distances from MAs
    dist_sma_20 = Column(Float, nullable=True)
    dist_sma_50 = Column(Float, nullable=True)
    dist_sma_200 = Column(Float, nullable=True)

    # Momentum
    rsi_14 = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)
    stochastic_k = Column(Float, nullable=True)
    stochastic_d = Column(Float, nullable=True)
    adx = Column(Float, nullable=True)
    roc_10 = Column(Float, nullable=True)

    # Volatility
    atr_14 = Column(Float, nullable=True)
    bollinger_upper = Column(Float, nullable=True)
    bollinger_lower = Column(Float, nullable=True)
    bollinger_width = Column(Float, nullable=True)
    volatility_20d = Column(Float, nullable=True)
    volatility_percentile = Column(Float, nullable=True)

    # Volume
    volume_ratio = Column(Float, nullable=True)  # Volume / SMA(volume, 20)
    volume_zscore = Column(Float, nullable=True)
    obv = Column(Float, nullable=True)
    volume_trend = Column(Float, nullable=True)

    # Support / Resistance
    pivot_point = Column(Float, nullable=True)
    support_1 = Column(Float, nullable=True)
    support_2 = Column(Float, nullable=True)
    resistance_1 = Column(Float, nullable=True)
    resistance_2 = Column(Float, nullable=True)

    # 52-week
    high_52w = Column(Float, nullable=True)
    low_52w = Column(Float, nullable=True)
    dist_52w_high = Column(Float, nullable=True)
    dist_52w_low = Column(Float, nullable=True)

    # Market relative
    relative_return_nifty = Column(Float, nullable=True)
    beta_20d = Column(Float, nullable=True)
    correlation_nifty = Column(Float, nullable=True)
    sector_relative_strength = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_techfeat_inst_ts", "instrument_key", "timestamp", unique=True),
    )


class FundamentalSnapshot(Base):
    """Point-in-time fundamental data snapshot."""

    __tablename__ = "fundamental_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    instrument_key = Column(String(100), nullable=False, index=True)
    isin = Column(String(20), nullable=True)
    snapshot_date = Column(DateTime(timezone=True), nullable=False)

    # Valuation
    pe_ratio = Column(Float, nullable=True)
    pb_ratio = Column(Float, nullable=True)
    ev_ebitda = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)

    # Profitability
    revenue = Column(Float, nullable=True)
    revenue_growth = Column(Float, nullable=True)
    operating_profit = Column(Float, nullable=True)
    operating_margin = Column(Float, nullable=True)
    net_profit = Column(Float, nullable=True)
    net_profit_growth = Column(Float, nullable=True)
    eps = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    roce = Column(Float, nullable=True)

    # Balance sheet
    total_debt = Column(Float, nullable=True)
    debt_equity = Column(Float, nullable=True)
    total_assets = Column(Float, nullable=True)
    total_liabilities = Column(Float, nullable=True)
    cash_equivalents = Column(Float, nullable=True)

    # Shareholding
    promoter_holding = Column(Float, nullable=True)
    fii_holding = Column(Float, nullable=True)
    dii_holding = Column(Float, nullable=True)
    public_holding = Column(Float, nullable=True)

    # Dividend
    dividend_yield = Column(Float, nullable=True)

    # Raw JSON for full data
    raw_data = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_fund_inst_date", "instrument_key", "snapshot_date"),
    )


class NewsItem(Base):
    """News articles from Upstox."""

    __tablename__ = "news"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    instrument_key = Column(String(100), nullable=True, index=True)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    source = Column(String(255), nullable=True)
    url = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    # Sentiment analysis
    sentiment_score = Column(Float, nullable=True)  # -1.0 to +1.0
    sentiment_label = Column(String(20), nullable=True)  # positive, negative, neutral
    event_type = Column(String(50), nullable=True)  # earnings, corporate_action, regulatory, etc.
    materiality = Column(String(20), nullable=True)  # high, medium, low

    __table_args__ = (
        Index("ix_news_instrument_pub", "instrument_key", "published_at"),
    )


class SectorData(Base):
    """Sector-level performance and analytics."""

    __tablename__ = "sector_data"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sector_name = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    # Performance
    return_1d = Column(Float, nullable=True)
    return_5d = Column(Float, nullable=True)
    return_1m = Column(Float, nullable=True)
    return_3m = Column(Float, nullable=True)

    # Breadth
    advances = Column(Integer, nullable=True)
    declines = Column(Integer, nullable=True)
    breadth_ratio = Column(Float, nullable=True)

    # Momentum
    momentum_score = Column(Float, nullable=True)
    relative_strength_nifty = Column(Float, nullable=True)

    # Volatility
    volatility = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_sector_name_ts", "sector_name", "timestamp"),
    )
