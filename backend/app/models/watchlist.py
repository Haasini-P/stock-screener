"""
StockMind AI — Scanner Watchlist
Tracks the date a symbol was first flagged by the scanner (or manually added)
and its holding-period classification, so the Scanner can show "added on"
dates and segregate ideas by term instead of recomputing a live technical
screen from scratch on every view. See app/services/analytics/watchlist_service.py.
"""

import uuid

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from app.database import Base
from app.models.compat import CompatUUID as UUID

TERMS = ("short", "mid", "long")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(50), nullable=False, unique=True, index=True)
    term = Column(String(10), nullable=False)  # one of TERMS
    source = Column(String(10), nullable=False)  # "auto" (scanner-flagged) | "manual"
    bucket = Column(String(50), nullable=True)  # the scanner bucket that first flagged it, if auto
    added_by = Column(String(255), nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
