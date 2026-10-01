"""
StockMind AI — Portfolio Models
Database models for portfolio holdings, positions, and P&L tracking.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from app.models.compat import CompatUUID as UUID, CompatJSON as JSON
from sqlalchemy.sql import func

from app.database import Base


class PortfolioHolding(Base):
    """User portfolio holding snapshot."""

    __tablename__ = "portfolio_holdings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    instrument_key = Column(String(100), nullable=False)
    trading_symbol = Column(String(100), nullable=True)
    exchange = Column(String(10), nullable=True)
    isin = Column(String(20), nullable=True)

    quantity = Column(Integer, nullable=False)
    average_price = Column(Float, nullable=False)
    last_price = Column(Float, nullable=True)

    # Values
    invested_value = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)

    # P&L
    pnl = Column(Float, nullable=True)
    pnl_percentage = Column(Float, nullable=True)
    day_change = Column(Float, nullable=True)
    day_change_percentage = Column(Float, nullable=True)

    # Analytics
    allocation_percentage = Column(Float, nullable=True)
    sector = Column(String(100), nullable=True)

    # Model outlook
    trend = Column(String(20), nullable=True)
    momentum = Column(String(20), nullable=True)
    risk_score = Column(Float, nullable=True)
    action_category = Column(String(50), nullable=True)
    model_outlook = Column(JSON, nullable=True)

    snapshot_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_holdings_user", "user_id"),
        Index("ix_holdings_user_inst", "user_id", "instrument_key"),
    )


class PortfolioPosition(Base):
    """User intraday/short-term positions."""

    __tablename__ = "portfolio_positions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    instrument_key = Column(String(100), nullable=False)
    trading_symbol = Column(String(100), nullable=True)
    exchange = Column(String(10), nullable=True)
    product = Column(String(10), nullable=True)  # D, I, MTF

    quantity = Column(Integer, nullable=False)
    average_price = Column(Float, nullable=False)
    last_price = Column(Float, nullable=True)

    buy_quantity = Column(Integer, nullable=True)
    buy_price = Column(Float, nullable=True)
    sell_quantity = Column(Integer, nullable=True)
    sell_price = Column(Float, nullable=True)

    pnl = Column(Float, nullable=True)
    day_buy_value = Column(Float, nullable=True)
    day_sell_value = Column(Float, nullable=True)

    snapshot_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_positions_user", "user_id"),
    )


class PortfolioPnL(Base):
    """Daily portfolio P&L snapshot."""

    __tablename__ = "portfolio_pnl"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)

    total_invested = Column(Float, nullable=True)
    total_current_value = Column(Float, nullable=True)
    total_pnl = Column(Float, nullable=True)
    total_pnl_percentage = Column(Float, nullable=True)
    day_pnl = Column(Float, nullable=True)
    day_pnl_percentage = Column(Float, nullable=True)

    # Risk metrics
    portfolio_volatility = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    concentration_risk = Column(Float, nullable=True)  # Herfindahl index
    diversification_score = Column(Float, nullable=True)

    # Allocation breakdown
    sector_allocation = Column(JSON, nullable=True)
    top_holdings = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_pnl_user_date", "user_id", "date"),
    )
