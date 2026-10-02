"""
StockMind AI — Zerodha Kite Connect Authentication Service
Handles the Kite Connect login flow. Tokens are encrypted at rest and NEVER
sent to the browser.

Important limitation vs. Upstox: Kite Connect's login URL has no `state` or
per-request redirect parameter — the redirect target is a single fixed URL
configured once in the Kite Developer Console for the whole app, and Kite's
callback carries no identifier of ours back. `oauth_state` is still generated
and stored for consistency with the Upstox flow, but the callback route
cannot match it against Kite's response the way it does for Upstox; instead
it resolves to the most recently initiated, not-yet-completed Kite connection
attempt (see `app/api/routes/auth.py::kite_callback`). That's an accepted
simplification for a single-user local app, not a multi-tenant-safe CSRF
guarantee.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decrypt_token, encrypt_token, generate_oauth_state
from app.models.user import OAuthConnection
from app.services.accounts import get_active_connection
from app.services.broker_config import get_credentials as get_broker_credentials

logger = get_logger(__name__)


class KiteAuthService:
    """
    Manages the Zerodha Kite Connect login lifecycle. Mirrors
    UpstoxAuthService's shape so both providers plug into the same Accounts
    API and order-routing logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_auth_url(self, user_id: UUID, nickname: Optional[str] = None) -> str:
        """Generate the Kite Connect login URL for a NEW account link."""
        creds = await get_broker_credentials(self.db, "kite")
        if not creds["configured"]:
            raise ValueError(
                "Kite Connect API credentials not configured. Add them in Settings → Broker API "
                "Credentials, or set KITE_API_KEY/KITE_API_SECRET in backend/.env."
            )

        state = generate_oauth_state()
        conn = OAuthConnection(user_id=user_id, provider="kite", nickname=nickname, oauth_state=state)
        self.db.add(conn)
        await self.db.commit()

        login_url = KiteConnect(api_key=creds["client_id"]).login_url()
        logger.info("kite_auth_url_generated", user_id=str(user_id))
        return login_url

    async def handle_callback(self, connection_id: UUID, request_token: str) -> dict:
        """Exchange a Kite request_token for an access_token, encrypt & store it."""
        conn = await self.db.get(OAuthConnection, connection_id)
        if not conn:
            raise ValueError("No pending Kite connection found for this callback")
        user_id = conn.user_id
        creds = await get_broker_credentials(self.db, "kite")

        kite = KiteConnect(api_key=creds["client_id"])
        try:
            import asyncio

            session = await asyncio.to_thread(
                kite.generate_session, request_token, api_secret=creds["client_secret"]
            )
        except KiteException as e:
            logger.error("kite_session_exchange_failed", error=str(e))
            raise ValueError(f"Kite login failed: {e}")

        access_token = session.get("access_token")
        if not access_token:
            raise ValueError("No access token in Kite response")

        conn.access_token_encrypted = encrypt_token(access_token)
        conn.token_type = "Bearer"
        conn.is_connected = True
        conn.connected_at = datetime.now(timezone.utc)
        conn.oauth_state = None
        conn.last_token_refresh = datetime.now(timezone.utc)
        conn.account_user_id = session.get("user_id")
        conn.account_user_name = session.get("user_name")
        conn.account_email = session.get("email")
        conn.account_exchanges = str(session.get("exchanges", []))

        await self.db.commit()
        logger.info("kite_connection_established", user_id=str(user_id), connection_id=str(conn.id))

        return {"connected": True, "kite_user_id": conn.account_user_id, "kite_user_name": conn.account_user_name}

    async def get_access_token(self, user_id: UUID) -> Optional[str]:
        """Decrypted access token for the user's active (or most recent) Kite account."""
        conn = await get_active_connection(self.db, user_id, "kite")
        if not conn or not conn.is_connected or not conn.access_token_encrypted:
            return None
        try:
            return decrypt_token(conn.access_token_encrypted)
        except Exception as e:
            logger.error("token_decryption_failed", user_id=str(user_id), error=str(e))
            return None

    async def revoke_connection_by_id(self, connection_id: UUID) -> None:
        """Invalidate a specific Kite connection's access token and clear it."""
        conn = await self.db.get(OAuthConnection, connection_id)
        if not conn:
            return

        if conn.access_token_encrypted:
            try:
                token = decrypt_token(conn.access_token_encrypted)
                creds = await get_broker_credentials(self.db, "kite")
                kite = KiteConnect(api_key=creds["client_id"], access_token=token)
                import asyncio

                await asyncio.to_thread(kite.invalidate_access_token)
            except Exception as e:
                logger.warning("kite_logout_failed", error=str(e))

        conn.access_token_encrypted = None
        conn.refresh_token_encrypted = None
        conn.is_connected = False
        conn.is_active = False
        conn.disconnected_at = datetime.now(timezone.utc)
        conn.oauth_state = None

        await self.db.commit()
        logger.info("kite_connection_revoked", connection_id=str(connection_id))
