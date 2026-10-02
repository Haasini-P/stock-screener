"""
StockMind AI — Alert Routes
User-defined price / change alerts, evaluated against live Upstox quotes.
Alerts are strictly user-scoped.
"""

import json
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.routes.market import get_market_provider
from app.core.logging import get_logger
from app.database import get_db
from app.models.user import Alert, User

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])
logger = get_logger(__name__)

AlertType = Literal["price_above", "price_below", "change_above", "change_below", "signal_buy"]
MAX_ALERTS_PER_USER = 100
# The same "actionable now" entry classifications the Scanner/Signals/Report badge as BUY —
# see ENTRY_TYPES in app/api/routes/market.py.
BUY_ENTRY_TYPES = {"BUY_NOW", "BUY_ON_RETEST", "BUY_ON_DIP"}


class AlertCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    alert_type: AlertType
    value: Optional[float] = None  # not needed for signal_buy — it fires on the signal itself
    message: Optional[str] = Field(None, max_length=500)


class AlertUpdate(BaseModel):
    is_active: Optional[bool] = None
    value: Optional[float] = None
    message: Optional[str] = Field(None, max_length=500)


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """ISO timestamp with an explicit UTC offset (SQLite returns naive datetimes)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _serialize(alert: Alert) -> dict:
    condition = json.loads(alert.condition or "{}")
    return {
        "id": str(alert.id),
        "symbol": alert.symbol,
        "instrument_key": alert.instrument_key,
        "alert_type": alert.alert_type,
        "value": condition.get("value"),
        "triggered_price": condition.get("triggered_price"),
        # Only populated for a triggered signal_buy alert:
        "entry_type": condition.get("entry_type"),
        "entry_zone": condition.get("entry_zone"),
        "stop_loss": condition.get("stop_loss"),
        "target_1": condition.get("target_1"),
        "message": alert.message,
        "is_active": alert.is_active,
        "is_triggered": alert.is_triggered,
        "triggered_at": _iso_utc(alert.triggered_at),
        "created_at": _iso_utc(alert.created_at),
    }


async def _get_owned(alert_id: UUID, user: User, db: AsyncSession) -> Alert:
    result = await db.execute(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("")
async def list_alerts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Alert).where(Alert.user_id == user.id).order_by(Alert.created_at.desc())
    )
    return {"alerts": [_serialize(a) for a in result.scalars().all()]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Alert.id).where(Alert.user_id == user.id))
    if len(existing.all()) >= MAX_ALERTS_PER_USER:
        raise HTTPException(status_code=400, detail=f"Alert limit reached ({MAX_ALERTS_PER_USER}).")

    if body.alert_type != "signal_buy":
        if body.value is None:
            raise HTTPException(status_code=422, detail="This alert type needs a numeric value.")
        if body.alert_type.startswith("price") and body.value <= 0:
            raise HTTPException(status_code=422, detail="Price alerts need a positive price.")

    provider = await get_market_provider(user, db)
    instrument_key = await provider.resolve_instrument_key(body.symbol)  # validates the symbol

    alert = Alert(
        user_id=user.id,
        alert_type=body.alert_type,
        symbol=body.symbol.upper(),
        instrument_key=instrument_key,
        condition=json.dumps({"value": body.value}),
        message=body.message,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return _serialize(alert)


@router.put("/{alert_id}")
async def update_alert(
    alert_id: UUID,
    body: AlertUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _get_owned(alert_id, user, db)
    if body.value is not None:
        alert.condition = json.dumps({"value": body.value})
        alert.is_triggered = False
        alert.triggered_at = None
    if body.message is not None:
        alert.message = body.message
    if body.is_active is not None:
        alert.is_active = body.is_active
        if body.is_active:  # re-arming resets the trigger
            alert.is_triggered = False
            alert.triggered_at = None
    await db.flush()
    await db.refresh(alert)
    return _serialize(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _get_owned(alert_id, user, db)
    await db.delete(alert)


def _is_hit(alert_type: str, target: float, ltp: float, change_pct: Optional[float]) -> bool:
    if alert_type == "price_above":
        return ltp >= target
    if alert_type == "price_below":
        return ltp <= target
    if change_pct is None:
        return False
    if alert_type == "change_above":
        return change_pct >= target
    return change_pct <= target


@router.post("/check")
async def check_alerts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Evaluate the user's active alerts against live quotes.
    Returns alerts triggered by this check plus all previously triggered ones.
    """
    result = await db.execute(
        select(Alert).where(
            Alert.user_id == user.id, Alert.is_active == True, Alert.is_triggered == False  # noqa: E712
        )
    )
    pending = result.scalars().all()
    price_alerts = [a for a in pending if a.alert_type != "signal_buy"]
    signal_alerts = [a for a in pending if a.alert_type == "signal_buy"]
    newly_triggered = []
    now = datetime.now(timezone.utc)

    if price_alerts:
        provider = await get_market_provider(user, db)
        keys = sorted({a.instrument_key for a in price_alerts if a.instrument_key})
        quotes = await provider.get_quotes(keys)
        by_key = {
            q["instrument_token"]: q
            for q in (quotes.get("data") or {}).values()
            if isinstance(q, dict) and q.get("instrument_token")
        }
        for alert in price_alerts:
            q = by_key.get(alert.instrument_key)
            if not q or q.get("last_price") is None:
                continue
            ltp = q["last_price"]
            net = q.get("net_change")
            change_pct = round(net / (ltp - net) * 100, 2) if net is not None and ltp != net else None
            condition = json.loads(alert.condition or "{}")
            if _is_hit(alert.alert_type, condition.get("value", 0), ltp, change_pct):
                alert.is_triggered = True
                alert.triggered_at = now
                alert.trigger_count = (alert.trigger_count or 0) + 1
                alert.condition = json.dumps({**condition, "triggered_price": ltp})
                newly_triggered.append(alert)

    if signal_alerts:
        from app.api.routes.signals import analyze_stock

        for alert in signal_alerts:
            try:
                analysis = await analyze_stock(alert.symbol, 200000, 0.75, user, db)
            except Exception as e:
                logger.warning("signal_alert_check_failed", symbol=alert.symbol, error=str(e))
                continue
            s = (analysis.get("signal") or {}).get("signal") or {}
            entry_type = s.get("entry")
            if entry_type not in BUY_ENTRY_TYPES:
                continue
            ee = (analysis.get("signal") or {}).get("entry_exit") or {}
            # analysis["quote"] is Upstox's raw get_quote() payload, keyed by "EXCHANGE:SYMBOL" —
            # same shape analyze_stock itself unwraps internally.
            raw_quote = next(iter((analysis.get("quote") or {}).values()), {}) or {}
            condition = json.loads(alert.condition or "{}")
            alert.is_triggered = True
            alert.triggered_at = now
            alert.trigger_count = (alert.trigger_count or 0) + 1
            alert.condition = json.dumps({
                **condition,
                "entry_type": entry_type,
                "entry_zone": ee.get("entry_zone"),
                "stop_loss": ee.get("stop_loss"),
                "target_1": ee.get("target_1"),
                "triggered_price": raw_quote.get("last_price"),
            })
            newly_triggered.append(alert)

    if newly_triggered:
        await db.flush()
        logger.info("alerts_triggered", user_id=str(user.id), count=len(newly_triggered))

    triggered = await db.execute(
        select(Alert)
        .where(Alert.user_id == user.id, Alert.is_triggered == True)  # noqa: E712
        .order_by(Alert.triggered_at.desc())
        .limit(20)
    )
    return {
        "newly_triggered": [_serialize(a) for a in newly_triggered],
        "triggered": [_serialize(a) for a in triggered.scalars().all()],
        "checked": len(pending),
    }
