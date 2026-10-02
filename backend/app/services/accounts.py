"""
StockMind AI — Linked Broker Accounts
Cross-provider helpers for managing a user's linked broker accounts
(OAuthConnection rows) — listing, activating, and ownership-checked lookup —
regardless of whether a given row is an Upstox or a Kite login. Provider-
specific behavior (OAuth exchange, logout calls, order placement) lives in
app/services/upstox/auth.py, app/services/kite/auth.py and
app/services/trading/order_service.py.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.user import OAuthConnection

logger = get_logger(__name__)


async def get_active_connection(db: AsyncSession, user_id: UUID, provider: str) -> Optional[OAuthConnection]:
    """The active connection for this provider, else the most-recently-connected one, else None."""
    result = await db.execute(
        select(OAuthConnection)
        .where(OAuthConnection.user_id == user_id, OAuthConnection.provider == provider)
        .order_by(OAuthConnection.is_active.desc(), OAuthConnection.connected_at.desc())
    )
    return result.scalars().first()


async def list_connections(db: AsyncSession, user_id: UUID) -> list[OAuthConnection]:
    """All linked accounts for a user, across every provider."""
    result = await db.execute(
        select(OAuthConnection).where(OAuthConnection.user_id == user_id).order_by(OAuthConnection.created_at)
    )
    return list(result.scalars().all())


async def get_connection_for_user(db: AsyncSession, user_id: UUID, connection_id: UUID) -> Optional[OAuthConnection]:
    """Ownership-checked single-connection lookup — used before placing an order or removing an account."""
    result = await db.execute(
        select(OAuthConnection).where(OAuthConnection.id == connection_id, OAuthConnection.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def set_active(db: AsyncSession, user_id: UUID, connection_id: UUID) -> OAuthConnection:
    """Mark one connection active and every other connection (any provider) inactive."""
    conns = await list_connections(db, user_id)
    target = next((c for c in conns if c.id == connection_id), None)
    if target is None:
        raise ValueError("Account not found")
    for c in conns:
        c.is_active = c.id == connection_id
    await db.commit()
    logger.info("account_activated", user_id=str(user_id), connection_id=str(connection_id), provider=target.provider)
    return target


def serialize_connection(conn: OAuthConnection) -> dict:
    return {
        "id": str(conn.id),
        "provider": conn.provider,
        "nickname": conn.nickname,
        "account_user_name": conn.account_user_name,
        "account_email": conn.account_email,
        "is_connected": conn.is_connected,
        "is_active": conn.is_active,
        "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
    }
