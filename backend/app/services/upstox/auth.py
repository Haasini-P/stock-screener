"""
StockMind AI — Upstox OAuth Authentication Service
Handles the complete OAuth 2.0 flow with Upstox.
Tokens are encrypted at rest and NEVER sent to the browser.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_token, encrypt_token, generate_oauth_state
from app.models.user import OAuthConnection

logger = get_logger(__name__)
settings = get_settings()


class UpstoxAuthService:
    """
    Manages Upstox OAuth 2.0 authentication lifecycle.

    Flow:
    1. generate_auth_url() → redirect user to Upstox login
    2. handle_callback() → exchange auth code for token, encrypt & store
    3. get_access_token() → decrypt & return token for API calls
    4. revoke_connection() → logout from Upstox & clear tokens
    """

    AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
    LOGOUT_URL = "https://api.upstox.com/v2/logout"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_auth_url(self, user_id: UUID) -> str:
        """
        Generate the Upstox OAuth authorization URL.
        Creates a state parameter for CSRF protection.
        """
        if not settings.has_upstox_credentials:
            raise ValueError(
                "Upstox API credentials not configured. "
                "Set UPSTOX_CLIENT_ID and UPSTOX_CLIENT_SECRET in .env"
            )

        state = generate_oauth_state()

        # Store state in the OAuth connection record
        conn = await self._get_or_create_connection(user_id)
        conn.oauth_state = state
        await self.db.commit()

        auth_url = (
            f"{self.AUTH_URL}"
            f"?client_id={settings.upstox_client_id}"
            f"&redirect_uri={settings.upstox_redirect_uri}"
            f"&response_type=code"
            f"&state={state}"
        )

        logger.info("oauth_auth_url_generated", user_id=str(user_id))
        return auth_url

    async def handle_callback(
        self,
        user_id: UUID,
        code: str,
        state: str,
    ) -> dict:
        """
        Handle the OAuth callback from Upstox.
        Validates state, exchanges code for token, encrypts & stores.
        """
        # Validate state parameter
        conn = await self._get_connection(user_id)
        if not conn or conn.oauth_state != state:
            raise ValueError("Invalid OAuth state parameter — possible CSRF attack")

        # Exchange authorization code for access token
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.upstox_client_id,
                    "client_secret": settings.upstox_client_secret,
                    "redirect_uri": settings.upstox_redirect_uri,
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
            conn.upstox_user_id = profile.get("user_id")
            conn.upstox_user_name = profile.get("user_name")
            conn.upstox_email = profile.get("email")
            conn.upstox_exchanges = str(profile.get("exchanges", []))
        except Exception as e:
            logger.warning("oauth_profile_fetch_failed", error=str(e))

        await self.db.commit()

        logger.info(
            "oauth_connection_established",
            user_id=str(user_id),
            upstox_user=conn.upstox_user_id,
        )

        return {
            "connected": True,
            "upstox_user_id": conn.upstox_user_id,
            "upstox_user_name": conn.upstox_user_name,
        }

    async def get_access_token(self, user_id: UUID) -> Optional[str]:
        """
        Get the decrypted Upstox access token for a user.
        Returns None if not connected.
        """
        conn = await self._get_connection(user_id)
        if not conn or not conn.is_connected or not conn.access_token_encrypted:
            return None

        try:
            return decrypt_token(conn.access_token_encrypted)
        except Exception as e:
            logger.error("token_decryption_failed", user_id=str(user_id), error=str(e))
            return None

    async def revoke_connection(self, user_id: UUID) -> None:
        """Revoke Upstox connection and clear stored tokens."""
        conn = await self._get_connection(user_id)
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
        conn.disconnected_at = datetime.now(timezone.utc)
        conn.oauth_state = None

        await self.db.commit()
        logger.info("oauth_connection_revoked", user_id=str(user_id))

    async def is_connected(self, user_id: UUID) -> bool:
        """Check if user has an active Upstox connection."""
        conn = await self._get_connection(user_id)
        return bool(conn and conn.is_connected and conn.access_token_encrypted)

    # --- Internal helpers ---

    async def _get_or_create_connection(self, user_id: UUID) -> OAuthConnection:
        """Get existing connection or create a new one."""
        conn = await self._get_connection(user_id)
        if conn is None:
            conn = OAuthConnection(user_id=user_id, provider="upstox")
            self.db.add(conn)
            await self.db.flush()
        return conn

    async def _get_connection(self, user_id: UUID) -> Optional[OAuthConnection]:
        """Get the Upstox OAuth connection for a user."""
        result = await self.db.execute(
            select(OAuthConnection).where(
                OAuthConnection.user_id == user_id,
                OAuthConnection.provider == "upstox",
            )
        )
        return result.scalar_one_or_none()

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
