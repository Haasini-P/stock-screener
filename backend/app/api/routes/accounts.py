"""
StockMind AI — Linked Broker Accounts Routes
List, connect, activate and remove the broker accounts (Upstox, Kite) a user
has linked. Order placement routes to whichever account is marked active.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.accounts import get_connection_for_user, list_connections, serialize_connection, set_active
from app.services.kite.auth import KiteAuthService
from app.services.upstox.auth import UpstoxAuthService

router = APIRouter(prefix="/api/accounts", tags=["Broker Accounts"])


@router.get("")
async def list_accounts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """All broker accounts linked to the current user."""
    conns = await list_connections(db, user.id)
    return [serialize_connection(c) for c in conns]


@router.get("/upstox/connect")
async def connect_upstox(
    nickname: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start linking a NEW Upstox account (you can link more than one)."""
    try:
        auth_url = await UpstoxAuthService(db).generate_auth_url(user.id, nickname=nickname)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"authorization_url": auth_url}


@router.get("/kite/connect")
async def connect_kite(
    nickname: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start linking a NEW Zerodha Kite account."""
    try:
        auth_url = await KiteAuthService(db).generate_auth_url(user.id, nickname=nickname)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"authorization_url": auth_url}


@router.post("/{account_id}/activate")
async def activate_account(account_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Mark one linked account as active — order placement routes to it by default."""
    try:
        conn = await set_active(db, user.id, account_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return serialize_connection(conn)


@router.delete("/{account_id}")
async def remove_account(account_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Disconnect and unlink a broker account."""
    conn = await get_connection_for_user(db, user.id, account_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Account not found")

    if conn.provider == "upstox":
        await UpstoxAuthService(db).revoke_connection_by_id(conn.id)
    elif conn.provider == "kite":
        await KiteAuthService(db).revoke_connection_by_id(conn.id)

    await db.delete(conn)
    await db.commit()
    return {"status": "removed"}
