"""
StockMind AI — User & Authentication Models
Database models for users, OAuth connections, and tokens.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from app.models.compat import CompatUUID as UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    oauth_connections = relationship("OAuthConnection", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class OAuthConnection(Base):
    """
    A linked broker account (Upstox or Kite). A user may link several accounts
    per provider — e.g. two Upstox logins and one Kite login — each identified
    by its own row. Exactly one row (across all providers) may be `is_active`
    at a time; that's the account order placement routes to by default.
    """

    __tablename__ = "oauth_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False, default="upstox")  # "upstox" | "kite"

    # User-facing label for this account, e.g. "Main Upstox", "Dad's Kite"
    nickname = Column(String(100), nullable=True)
    # Exactly one connection per user should be active at a time (enforced in
    # application code — see UpstoxAuthService.set_active)
    is_active = Column(Boolean, default=False, nullable=False)

    # Encrypted tokens — NEVER stored in plaintext
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)

    # Token metadata
    token_type = Column(String(50), default="Bearer")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(Text, nullable=True)

    # Broker account profile (generic — populated for both Upstox and Kite)
    account_user_id = Column(String(100), nullable=True)
    account_user_name = Column(String(255), nullable=True)
    account_email = Column(String(255), nullable=True)
    account_exchanges = Column(Text, nullable=True)  # JSON array of enabled exchanges

    # Connection state
    is_connected = Column(Boolean, default=False, nullable=False)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    last_token_refresh = Column(DateTime(timezone=True), nullable=True)
    oauth_state = Column(String(255), nullable=True)  # CSRF protection (see KiteAuthService for a caveat)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="oauth_connections")

    __table_args__ = (
        Index("ix_oauth_user_provider", "user_id", "provider"),
    )

    def __repr__(self) -> str:
        return f"<OAuthConnection user={self.user_id} provider={self.provider}>"


class Alert(Base):
    """User-defined alerts."""

    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    alert_type = Column(String(50), nullable=False)  # price, breakout, portfolio, volume, confidence
    instrument_key = Column(String(100), nullable=True)
    symbol = Column(String(50), nullable=True)
    condition = Column(Text, nullable=False)  # JSON condition object
    message = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_triggered = Column(Boolean, default=False, nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    trigger_count = Column(Integer, default=0)
    max_triggers = Column(Integer, default=1)

    # Notification channels
    notify_browser = Column(Boolean, default=True)
    notify_email = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="alerts")

    __table_args__ = (
        Index("ix_alerts_user_active", "user_id", "is_active"),
    )
