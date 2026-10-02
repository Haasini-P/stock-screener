"""
StockMind AI — Authentication Routes
Handles user registration, login, and Upstox OAuth flow.
"""

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import OAuthConnection, User
from app.services.kite.auth import KiteAuthService
from app.services.upstox.auth import UpstoxAuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
settings = get_settings()


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


# --- Endpoints ---

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    # Check if email exists
    existing = await db.execute(
        select(User).where(User.email == request.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
    )
    db.add(user)
    await db.flush()

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.is_admin),
        refresh_token=create_refresh_token(user.id),
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": bool(user.is_admin),
        },
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email and password."""
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    user.last_login = datetime.now(timezone.utc)
    await db.flush()

    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.is_admin),
        refresh_token=create_refresh_token(user.id),
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
        },
    )


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current user profile."""
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# --- Upstox OAuth ---

@router.get("/upstox/connect")
async def upstox_connect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate Upstox OAuth authorization URL.
    The user is redirected to Upstox login — we NEVER ask for their Upstox password.
    """
    auth_service = UpstoxAuthService(db)
    try:
        auth_url = await auth_service.generate_auth_url(user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"authorization_url": auth_url}


@router.get("/callback")
async def upstox_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle the Upstox OAuth callback: exchange the code for a token, store it
    encrypted, then send the browser back to the app's settings view.
    """
    def back_to_app(result: str, message: str = "") -> RedirectResponse:
        query = f"upstox={result}" + (f"&message={quote(message)}" if message else "")
        return RedirectResponse(f"{settings.frontend_url}/?{query}#settings", status_code=302)

    if error or not code or not state:
        return back_to_app("error", error or "Upstox did not return an authorization code.")

    result = await db.execute(select(OAuthConnection).where(OAuthConnection.oauth_state == state))
    conn = result.scalar_one_or_none()
    if not conn:
        return back_to_app("error", "Invalid or expired OAuth session. Please try connecting again.")

    try:
        await UpstoxAuthService(db).handle_callback(conn.id, code, state)
    except ValueError as e:
        return back_to_app("error", str(e)[:200])

    return back_to_app("connected")


@router.get("/kite/callback")
async def kite_callback(
    request_token: Optional[str] = Query(None),
    kite_status: Optional[str] = Query(None, alias="status"),
    action: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle the Kite Connect login redirect. Kite's redirect carries no state
    of ours (see KiteAuthService docstring), so this resolves to the most
    recently initiated, not-yet-completed Kite connection attempt.
    """
    def back_to_app(result: str, message: str = "") -> RedirectResponse:
        query = f"kite={result}" + (f"&message={quote(message)}" if message else "")
        return RedirectResponse(f"{settings.frontend_url}/?{query}#settings", status_code=302)

    if kite_status == "error" or not request_token:
        return back_to_app("error", "Kite did not return a request token.")

    result = await db.execute(
        select(OAuthConnection)
        .where(OAuthConnection.provider == "kite", OAuthConnection.oauth_state.isnot(None))
        .order_by(OAuthConnection.created_at.desc())
        .limit(1)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        return back_to_app("error", "No pending Kite connection found. Please try connecting again.")

    try:
        await KiteAuthService(db).handle_callback(conn.id, request_token)
    except ValueError as e:
        return back_to_app("error", str(e)[:200])

    return back_to_app("connected")


@router.post("/upstox/disconnect")
async def upstox_disconnect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Upstox account and revoke tokens."""
    auth_service = UpstoxAuthService(db)
    await auth_service.revoke_connection(user.id)
    return {"status": "disconnected"}


@router.get("/upstox/status")
async def upstox_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check Upstox connection status."""
    auth_service = UpstoxAuthService(db)
    connected = await auth_service.is_connected(user.id)
    return {"connected": connected}
