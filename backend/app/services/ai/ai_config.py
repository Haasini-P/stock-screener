"""
StockMind AI — AI Provider Settings
Get/set API credentials for multiple AI providers (Anthropic, Google), each
stored encrypted at rest in its own row — mirrors app/services/broker_config.py's
per-provider pattern. The *active* model is a separate, single setting;
which provider's key it needs is resolved via MODEL_PROVIDER/provider_for_model.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_token, encrypt_token
from app.models.ai_commentary import AIProviderCredential, AISettings

DEFAULT_MODEL = "claude-opus-5-5"

PROVIDERS = ("anthropic", "google")

# Maps every model this app offers to the provider whose API key it needs.
# A model not in this map is rejected when set as the active model.
# Deliberately not using Gemini's "-latest" aliases here — their pricing moves
# with whatever model they currently resolve to, which doesn't fit a fixed
# MODEL_PRICING table. gemini-3.8-flash is a concrete, currently-priced model.
MODEL_PROVIDER = {
    "claude-opus-5-5": "anthropic",
    "claude-sonnet-5-5": "anthropic",
    "claude-haiku-4-5": "anthropic",
    "gemini-3.8-flash": "google",
}


class AIConfigError(Exception):
    pass


def provider_for_model(model: str) -> str:
    provider = MODEL_PROVIDER.get(model)
    if not provider:
        raise AIConfigError(f"Unknown model '{model}'.")
    return provider


async def _settings_row(db: AsyncSession) -> Optional[AISettings]:
    result = await db.execute(select(AISettings).limit(1))
    return result.scalar_one_or_none()


async def _credential_row(db: AsyncSession, provider: str) -> Optional[AIProviderCredential]:
    result = await db.execute(select(AIProviderCredential).where(AIProviderCredential.provider == provider))
    return result.scalar_one_or_none()


async def get_active_model(db: AsyncSession) -> str:
    row = await _settings_row(db)
    return (row.model if row else None) or DEFAULT_MODEL


async def get_provider_key(db: AsyncSession, provider: str) -> str:
    """Decrypted API key for a provider, or "" if none is stored. Internal use only — never return to the browser."""
    row = await _credential_row(db, provider)
    return decrypt_token(row.api_key_encrypted) if row and row.api_key_encrypted else ""


async def get_settings(db: AsyncSession) -> dict:
    """Resolved {api_key, model, provider, configured} for the currently active model. Internal use only."""
    model = await get_active_model(db)
    provider = provider_for_model(model)
    api_key = await get_provider_key(db, provider)
    return {"api_key": api_key, "model": model, "provider": provider, "configured": bool(api_key)}


async def get_settings_public(db: AsyncSession) -> dict:
    """Safe to return to the browser — never includes any secret, just per-provider configured status."""
    s = await get_settings(db)
    providers = {p: {"has_key": bool(await get_provider_key(db, p))} for p in PROVIDERS}
    return {"model": s["model"], "provider": s["provider"], "configured": s["configured"], "providers": providers}


async def set_active_model(db: AsyncSession, model: str, updated_by: str) -> dict:
    """Switch which model (and therefore which provider's key) commentary generation uses."""
    provider_for_model(model)  # raises AIConfigError if unknown
    row = await _settings_row(db)
    if row is None:
        row = AISettings(model=model)
        db.add(row)
    else:
        row.model = model
    row.updated_by = updated_by
    await db.commit()
    return await get_settings_public(db)


async def set_provider_key(db: AsyncSession, provider: str, api_key: str, updated_by: str) -> dict:
    """Save (or overwrite) one provider's API key. A blank key clears it."""
    if provider not in PROVIDERS:
        raise AIConfigError(f"Unknown provider '{provider}'. Must be one of {PROVIDERS}.")
    row = await _credential_row(db, provider)
    if row is None:
        row = AIProviderCredential(provider=provider)
        db.add(row)
    row.api_key_encrypted = encrypt_token(api_key.strip()) if api_key.strip() else None
    row.updated_by = updated_by
    await db.commit()
    return await get_settings_public(db)
