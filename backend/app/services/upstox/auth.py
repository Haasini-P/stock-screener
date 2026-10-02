"""
StockMind AI — Upstox OAuth Authentication Service
Handles the complete OAuth 2.0 flow with Upstox.
Tokens are encrypted at rest and NEVER sent to the browser.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decrypt_token, encrypt_token, generate_oauth_state
from app.models.user import OAuthConnection
from app.services.accounts import get_active_connection
from app.services.broker_config import get_credentials as get_broker_credentials

logger = get_logger(__name__)


class UpstoxAuthService:
    """
    Manages Upstox OAuth 2.0 authentication lifecycle. A user may link several
    Upstox accounts (one row per login); `get_access_token`/`is_connected`/
    `revoke_connection` operate on the user's *active* Upstox connection
    (falling back to the most-recently-connected one) for backward-compatible,
    single-account call sites (market data, portfolio). Multi-account
    management (listing, activating, deleting a specific account) is exposed
    separately for the Accounts API.

    Flow:
    1. generate_auth_url() → redirect user to Upstox login (creates a new row)
    2. handle_callback() → exchange auth code for token, encrypt & store
    3. get_access_token() → decrypt & return the active account's token
    4. revoke_connection() → logout from Upstox & clear tokens
    """

    AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
    LOGOUT_URL = "https://api.upstox.com/v2/logout"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_auth_url(self, user_id: UUID, nickname: Optional[str] = None) -> str:
        """
        Generate the Upstox OAuth authorization URL for a NEW account link.
        Creates a state parameter for CSRF protection.
        """
        creds = await get_broker_credentials(self.db, "upstox")
        if not creds["configured"]:
            raise ValueError(
                "Upstox API credentials not configured. Add them in Settings → Broker API "
                "Credentials, or set UPSTOX_CLIENT_ID/UPSTOX_CLIENT_SECRET in backend/.env."
            )

        state = generate_oauth_state()

        conn = OAuthConnection(user_id=user_id, provider="upstox", nickname=nickname, oauth_state=state)
        self.db.add(conn)
        await self.db.commit()

        params = urlencode({
            "client_id": creds["client_id"],
            "redirect_uri": creds["redirect_uri"],
            "response_type": "code",
            "state": state,
        })
        auth_url = f"{self.AUTH_URL}?{params}"

        logger.info(
            "oauth_auth_url_generated",
            user_id=str(user_id),
            client_id=creds["client_id"],
            redirect_uri=creds["redirect_uri"],
        )
        return auth_url

    async def handle_callback(
        self,
        connection_id: UUID,
        code: str,
        state: str,
    ) -> dict:
        """
        Handle the OAuth callback from Upstox for a specific pending connection.
        Validates state, exchanges code for token, encrypts & stores.
        """
        conn = await self.db.get(OAuthConnection, connection_id)
        if not conn or conn.oauth_state != state:
            raise ValueError("Invalid OAuth state parameter — possible CSRF attack")
        user_id = conn.user_id
        creds = await get_broker_credentials(self.db, "upstox")

        # Exchange authorization code for access token
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "client_id": creds["client_id"],
                    "client_secret": creds["client_secret"],
                    "redirect_uri": creds["redirect_uri"],
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            logger.error(
                "oauth_token_exchange_failed",
                status_code=response.status_code,
                response=response.text,
            )
            raise ValueError(f"Token exchange failed: {response.text}")

        token_data = response.json()

        # Encrypt and store the access token
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("No access token in Upstox response")

        conn.access_token_encrypted = encrypt_token(access_token)
        conn.token_type = token_data.get("token_type", "Bearer")
        conn.is_connected = True
        conn.connected_at = datetime.now(timezone.utc)
        conn.oauth_state = None  # Clear state after use
        conn.last_token_refresh = datetime.now(timezone.utc)

        # Try to fetch user profile
        try:
            profile = await self._fetch_profile(access_token)
            conn.account_user_id = profile.get("user_id")
            conn.account_user_name = profile.get("user_name")
            conn.account_email = profile.get("email")
            conn.account_exchanges = str(profile.get("exchanges", []))
        except Exception as e:
            logger.warning("oauth_profile_fetch_failed", error=str(e))

        await self.db.commit()

        logger.info(
            "oauth_connection_established",
            user_id=str(user_id),
            connection_id=str(conn.id),
            upstox_user=conn.account_user_id,
        )

        return {
            "connected": True,
            "upstox_user_id": conn.account_user_id,
            "upstox_user_name": conn.account_user_name,
        }

    async def get_access_token(self, user_id: UUID) -> Optional[str]:
        """
        Get the decrypted access token for the user's active (or most recently
        connected) Upstox account. Returns None if no Upstox account is linked.
        """
        conn = await get_active_connection(self.db, user_id, "upstox")
        if not conn or not conn.is_connected or not conn.access_token_encrypted:
            return None

        try:
            return decrypt_token(conn.access_token_encrypted)
        except Exception as e:
            logger.error("token_decryption_failed", user_id=str(user_id), error=str(e))
            return None

    async def revoke_connection(self, user_id: UUID) -> None:
        """Revoke the user's active Upstox connection and clear its stored tokens."""
        conn = await get_active_connection(self.db, user_id, "upstox")
        if conn:
            await self.revoke_connection_by_id(conn.id)

    async def revoke_connection_by_id(self, connection_id: UUID) -> None:
        """Revoke a specific Upstox connection (logout + clear tokens) by its row id."""
        conn = await self.db.get(OAuthConnection, connection_id)
        if not conn:
            return

        # Try to logout from Upstox
        if conn.access_token_encrypted:
            try:
                token = decrypt_token(conn.access_token_encrypted)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.delete(
                        self.LOGOUT_URL,
                        headers={"Authorization": f"Bearer {token}"},
                    )
            except Exception as e:
                logger.warning("upstox_logout_failed", error=str(e))

        # Clear tokens
        conn.access_token_encrypted = None
        conn.refresh_token_encrypted = None
        conn.is_connected = False
        conn.is_active = False
        conn.disconnected_at = datetime.now(timezone.utc)
        conn.oauth_state = None

        await self.db.commit()
        logger.info("oauth_connection_revoked", connection_id=str(connection_id))

    async def is_connected(self, user_id: UUID) -> bool:
        """Check if the user has at least one connected Upstox account."""
        conn = await get_active_connection(self.db, user_id, "upstox")
        return bool(conn and conn.is_connected and conn.access_token_encrypted)

    # --- Internal helpers ---

    async def _fetch_profile(self, access_token: str) -> dict:
        """Fetch user profile from Upstox."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.upstox.com/v2/user/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {})
            return {}
