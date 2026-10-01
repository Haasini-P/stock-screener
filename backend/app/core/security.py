"""
StockMind AI — Security Module
JWT authentication, password hashing, token encryption, CSRF protection.
Upstox access tokens are NEVER sent to the browser.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import base64
import hashlib

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()

# Fernet encryption for Upstox tokens at rest
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Lazily initialize Fernet cipher."""
    global _fernet
    if _fernet is None:
        key = settings.encryption_key
        if key == "change-this-to-a-fernet-key":
            # Development fallback: derive a stable key from the JWT secret so stored
            # Upstox tokens survive restarts. In production ENCRYPTION_KEY MUST be set.
            key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest()).decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


# --- Password Operations ---

# bcrypt only uses the first 72 bytes of a password (and bcrypt>=4.1 rejects longer input)
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode()[:_BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode()[:_BCRYPT_MAX_BYTES], hashed_password.encode())
    except ValueError:
        return False


# --- JWT Operations ---

def create_access_token(
    user_id: UUID,
    email: str,
    is_admin: bool = False,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expiration_minutes)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + expires_delta,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID) -> str:
    """Create a longer-lived refresh token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=30),
        "type": "refresh",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    Raises JWTError on invalid/expired token.
    """
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )


def verify_token_type(token: str, expected_type: str = "access") -> dict:
    """Decode a token and verify its type."""
    payload = decode_token(token)
    if payload.get("type") != expected_type:
        raise JWTError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")
    return payload


# --- Token Encryption (for Upstox tokens at rest) ---

def encrypt_token(token: str) -> str:
    """Encrypt an Upstox access/refresh token for database storage."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an Upstox token from database storage."""
    return _get_fernet().decrypt(encrypted_token.encode()).decode()


# --- CSRF / OAuth State ---

def generate_oauth_state() -> str:
    """Generate a cryptographically random OAuth state parameter."""
    return secrets.token_urlsafe(32)


def generate_session_id() -> str:
    """Generate a secure session identifier."""
    return secrets.token_hex(32)
