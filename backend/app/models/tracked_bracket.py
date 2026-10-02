"""
StockMind AI — Tracked Brackets
Records a target+stop-loss (optionally trailing) bracket placed alongside a
live entry order, so it's visible in the UI and — for Kite, which has no
native trailing in its API — so the trailing monitor has something to act on.
Upstox's trailing is broker-native (its GTT `trailing_gap`); the row is still
kept for visibility even though the monitor never touches it.
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy.sql import func

from app.database import Base
from app.models.compat import CompatUUID as UUID


class TrackedBracket(Base):
    """A target/stop-loss (optionally trailing) bracket attached to a live entry order."""

    __tablename__ = "tracked_brackets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), nullable=False)
    provider = Column(String(50), nullable=False)  # "upstox" | "kite"

    symbol = Column(String(50), nullable=False)
    instrument_token = Column(String(100), nullable=True)
    transaction_type = Column(String(10), nullable=False)  # BUY | SELL (the entry side)
    product = Column(String(20), nullable=False)  # DELIVERY | INTRADAY — needed to rebuild Kite's GTT orders[] on modify
    quantity = Column(Integer, nullable=False)

    entry_price = Column(Numeric(12, 2), nullable=False)
    target_price = Column(Numeric(12, 2), nullable=True)
    stop_price = Column(Numeric(12, 2), nullable=True)  # current — mutated as it trails
    trailing_amount = Column(Numeric(12, 2), nullable=True)  # absolute ₹ gap; null = not trailing
    high_water_mark = Column(Numeric(12, 2), nullable=True)  # best LTP seen since placement

    broker_ref = Column(String(100), nullable=True)  # Upstox gtt_order_id or Kite GTT trigger_id
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE | TRIGGERED | CANCELLED | ERROR
    last_error = Column(String(500), nullable=True)

    last_trailed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<TrackedBracket {self.symbol} status={self.status}>"
