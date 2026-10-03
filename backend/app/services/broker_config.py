"""
StockMind AI — Broker App Credentials
Lets Upstox/Kite app-level API credentials (client id/secret, redirect uri)
be configured from Settings and stored encrypted in the database, instead of
only via backend/.env + a restart. A database row always wins; fields left
blank in the database fall back to the matching env var.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decrypt_token, encrypt_token
from app.models.broker_credential import BrokerCredential

settings = get_settings()

_ENV_DEFAULTS = {
    "upstox": {
        "client_id": lambda: settings.upstox_client_id,
        "client_secret": lambda: settings.upstox_client_secret,
        "redirect_uri": lambda: settings.upstox_redirect_uri,
    },
    "kite": {
        "client_id": lambda: settings.kite_api_key,
        "client_secret": lambda: settings.kite_api_secret,
        "redirect_uri": lambda: settings.kite_redirect_uri,
    },
    "alpaca": {
        "client_id": lambda: settings.alpaca_api_key_id,
        "client_secret": lambda: settings.alpaca_api_secret_key,
        "redirect_uri": lambda: "",  # not OAuth — Alpaca is a plain key+secret pair, unused
    },
}


async def _get_row(db: AsyncSession, provider: str) -> Optional[BrokerCredential]:
    result = await db.execute(select(BrokerCredential).where(BrokerCredential.provider == provider))
    return result.scalar_one_or_none()


async def get_credentials(db: AsyncSession, provider: str) -> dict:
    """Resolved {client_id, client_secret, redirect_uri, configured, source} for a provider."""
    env = _ENV_DEFAULTS[provider]
    row = await _get_row(db, provider)

    client_id = (row.client_id if row and row.client_id else None) or env["client_id"]() or ""
    client_secret = (
        decrypt_token(row.client_secret_encrypted) if row and row.client_secret_encrypted else None
    ) or env["client_secret"]() or ""
    redirect_uri = (row.redirect_uri if row and row.redirect_uri else None) or env["redirect_uri"]() or ""

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "configured": bool(client_id and client_secret),
        "source": "database" if row and row.client_id else "env",
    }


async def get_credentials_public(db: AsyncSession, provider: str) -> dict:
    """Same as get_credentials but never includes the secret — safe to return to the browser."""
    creds = await get_credentials(db, provider)
    return {
        "client_id": creds["client_id"],
        "redirect_uri": creds["redirect_uri"],
        "has_secret": bool(creds["client_secret"]),
        "configured": creds["configured"],
        "source": creds["source"],
    }


async def set_credentials(
    db: AsyncSession,
    provider: str,
    client_id: str,
    client_secret: Optional[str],
    redirect_uri: str,
    updated_by: str,
) -> dict:
    """
    Save app credentials for a provider. `client_secret` left blank/None keeps
    whatever secret is already stored (the browser never gets the secret back
    to re-submit, so a blank field must mean "don't change it").
    """
    row = await _get_row(db, provider)
    if row is None:
        row = BrokerCredential(provider=provider)
        db.add(row)

    row.client_id = client_id.strip()
    row.redirect_uri = redirect_uri.strip()
    if client_secret:
        row.client_secret_encrypted = encrypt_token(client_secret.strip())
    row.updated_by = updated_by

    await db.commit()
    return await get_credentials_public(db, provider)
