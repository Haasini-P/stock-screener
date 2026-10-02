"""
StockMind AI — AI Commentary Models
AISettings holds the Claude API credentials (singleton, mirrors BrokerCredential's
encrypt-on-write pattern). AICommentary caches generated commentary per symbol so
repeated views within the same day — across Scanner, Daily Signals and Stock Report —
never re-bill the API; see app/services/ai/commentary_service.py.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.compat import CompatUUID as UUID


class AISettings(Base):
    """Singleton row holding the Claude API key and chosen model."""

    __tablename__ = "ai_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_encrypted = Column(Text, nullable=True)
    model = Column(String(100), nullable=False, default="claude-opus-5-5")
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AICommentary(Base):
    """Cached AI-generated commentary for a symbol — avoids re-billing on every view."""

    __tablename__ = "ai_commentary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(50), nullable=False, index=True)
    context_hash = Column(String(64), nullable=False)  # sha256 of the inputs that produced `content`
    content = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=False)
    chart_included = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIBatchCommentary(Base):
    """Cached AI-generated multi-stock quick-scan — one cheaper, shallower call covering several symbols."""

    __tablename__ = "ai_batch_commentary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbols = Column(Text, nullable=False)  # comma-joined, sorted — also used for display
    context_hash = Column(String(64), nullable=False)
    content = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
