"""
StockMind AI — Broker App Credentials Model
Stores the Upstox/Kite app-level API credentials (client id/secret, redirect
uri) that can be configured from Settings instead of only via backend/.env.
One row per provider; falls back to env vars when no row exists — see
app/services/broker_config.py.
"""

import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.compat import CompatUUID as UUID


class BrokerCredential(Base):
    """App-level OAuth credentials for a broker (Upstox's client_id/secret, or Kite's api_key/secret)."""

    __tablename__ = "broker_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, unique=True)  # "upstox" | "kite"

    # Generic naming so one model/service covers both providers:
    # Upstox: client_id = Client ID, client_secret = Client Secret
    # Kite:   client_id = API Key,   client_secret = API Secret
    client_id = Column(String(255), nullable=True)
    client_secret_encrypted = Column(Text, nullable=True)
    redirect_uri = Column(String(500), nullable=True)

    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<BrokerCredential provider={self.provider}>"
