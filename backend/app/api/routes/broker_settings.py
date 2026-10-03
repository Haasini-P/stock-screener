"""
StockMind AI — Broker App Credentials Routes
Lets Upstox/Kite app-level API credentials be viewed (never the secret) and
updated from Settings, instead of only via backend/.env + a restart.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.broker_config import get_credentials_public, set_credentials

router = APIRouter(prefix="/api/settings/brokers", tags=["Broker Settings"])


class BrokerCredentialUpdate(BaseModel):
    client_id: str = Field(min_length=1, max_length=255)
    client_secret: Optional[str] = Field(None, max_length=1000)
    redirect_uri: str = Field(min_length=1, max_length=500)


class AlpacaCredentialUpdate(BaseModel):
    """No redirect_uri — Alpaca is a plain API Key ID + Secret pair, not OAuth."""
    client_id: str = Field(min_length=1, max_length=255)
    client_secret: Optional[str] = Field(None, max_length=1000)


@router.get("")
async def get_broker_settings(db: AsyncSession = Depends(get_db)):
    """Current Upstox/Kite/Alpaca app credential status — secrets are never returned."""
    return {
        "upstox": await get_credentials_public(db, "upstox"),
        "kite": await get_credentials_public(db, "kite"),
        "alpaca": await get_credentials_public(db, "alpaca"),
    }


@router.put("/upstox")
async def update_upstox_settings(
    body: BrokerCredentialUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the Upstox app's Client ID / Client Secret / Redirect URI."""
    return await set_credentials(db, "upstox", body.client_id, body.client_secret, body.redirect_uri, user.email)


@router.put("/kite")
async def update_kite_settings(
    body: BrokerCredentialUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the Kite Connect app's API Key / API Secret / Redirect URI."""
    return await set_credentials(db, "kite", body.client_id, body.client_secret, body.redirect_uri, user.email)


@router.put("/alpaca")
async def update_alpaca_settings(
    body: AlpacaCredentialUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save Alpaca's API Key ID / Secret Key (free tier, no KYC — app.alpaca.markets/signup).
    Powers real US stock quotes/candles/news on the US Stocks page."""
    return await set_credentials(db, "alpaca", body.client_id, body.client_secret, "", user.email)
