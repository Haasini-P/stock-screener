"""
StockMind AI — Order Placement Routes
Places a REAL order on one of the user's linked broker accounts. This moves
real money — see app/services/trading/order_service.py for the safety checks
(ownership verification, structured audit logging) applied to every request.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.trading.order_service import OrderError, OrderRequest, cancel_bracket, list_brackets, place_order

router = APIRouter(prefix="/api/orders", tags=["Orders"])


@router.post("/place")
async def place_order_route(
    req: OrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a live BUY/SELL order (optionally with a target/stop-loss bracket) on the chosen linked broker account."""
    try:
        return await place_order(db, user, req)
    except OrderError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/brackets")
async def list_brackets_route(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The user's target/stop-loss brackets, active and historical."""
    return await list_brackets(db, user)


@router.delete("/brackets/{bracket_id}")
async def cancel_bracket_route(
    bracket_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel the broker-side GTT behind a tracked bracket."""
    try:
        return await cancel_bracket(db, user, bracket_id)
    except OrderError as e:
        raise HTTPException(status_code=422, detail=str(e))
