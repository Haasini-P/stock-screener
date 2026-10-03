"""
StockMind AI — US Paper Trading & Research Models
PaperOrder is an append-only ledger (not a live-mutated positions table) —
positions are computed on read in app/services/paper_trading.py. There is no
live US quote to execute against (see app/services/us_market/provider.py), so
fill_price is always user-entered, not auto-filled at "market price" the way
the real Indian order flow (app/models/portfolio.py) works.

USCommentaryCache is a standalone cache table for US "AI Research Notes"
(app/services/ai/us_commentary_service.py) — deliberately separate from
AICommentary (app/models/ai_commentary.py) so it can never collide with or
slow down the live Indian AI commentary cache.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Float, String, Text, Index
from sqlalchemy.sql import func

from app.database import Base
from app.models.compat import CompatUUID as UUID


class PaperOrder(Base):
    """One simulated fill. Positions/P&L are aggregated from these rows, never stored denormalized."""

    __tablename__ = "paper_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(4), nullable=False)  # BUY | SELL
    quantity = Column(Integer, nullable=False)
    fill_price = Column(Float, nullable=False)  # user-entered — no live US quote exists yet
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_paper_orders_user_symbol", "user_id", "symbol"),)


class USCommentaryCache(Base):
    """Cached AI Research Notes for a US symbol — same context-hash cache-hit
    pattern as AICommentary, kept in its own table (see module docstring)."""

    __tablename__ = "us_commentary_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    context_hash = Column(String(64), nullable=False)
    content = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
