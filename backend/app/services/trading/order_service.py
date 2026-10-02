"""
StockMind AI — Order Execution
Places a REAL order against a user's linked broker account (Upstox or Kite),
optionally with a target + stop-loss (and trailing stop-loss) bracket attached.
This moves real money — every attempt is logged (never the token) for an
audit trail, and the account is always ownership-checked against the
requesting user before anything is sent to a broker.

Bracket mechanics differ by broker (see app/services/upstox/provider.py and
app/services/kite/... for the researched API details):
- Upstox: a single GTT order (ENTRY + TARGET + STOPLOSS rules) replaces the
  plain entry order entirely. Trailing is broker-native (`trailing_gap`) — our
  trailing monitor never touches Upstox brackets.
- Kite: the plain entry order is placed as usual, then a second, OCO GTT
  order (TARGET + STOPLOSS) protects it. Kite's API has no native trailing,
  so a `TrackedBracket` row is recorded and app/services/trading/trailing_monitor.py
  periodically raises its stop via `modify_gtt`.
"""

import asyncio
from typing import Literal, Optional
from uuid import UUID

from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decrypt_token
from app.models.tracked_bracket import TrackedBracket
from app.models.user import User
from app.services.accounts import get_connection_for_user
from app.services.broker_config import get_credentials as get_broker_credentials
from app.services.upstox.client import UpstoxAPIError
from app.services.upstox.provider import UpstoxDataProvider

logger = get_logger(__name__)

UPSTOX_PRODUCT = {"DELIVERY": "D", "INTRADAY": "I"}
KITE_PRODUCT = {"DELIVERY": "CNC", "INTRADAY": "MIS"}


class OrderRequest(BaseModel):
    account_id: UUID
    symbol: str = Field(min_length=1, max_length=50)
    transaction_type: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"]
    product: Literal["DELIVERY", "INTRADAY"]
    price: Optional[float] = None
    validity: Literal["DAY"] = "DAY"

    # Optional bracket — target/stop-loss (and trailing) attached to the entry.
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    trailing_amount: Optional[float] = None  # absolute ₹ gap, matches Upstox's trailing_gap units

    @property
    def has_bracket(self) -> bool:
        return self.target_price is not None or self.stop_price is not None

    @model_validator(mode="after")
    def price_required_for_limit(self):
        if self.order_type == "LIMIT" and not self.price:
            raise ValueError("price is required for a LIMIT order")
        return self

    @model_validator(mode="after")
    def validate_bracket(self):
        if not self.has_bracket:
            if self.trailing_amount:
                raise ValueError("trailing_amount requires a stop_price")
            return self

        if self.target_price is None or self.stop_price is None:
            raise ValueError("A bracket needs both target_price and stop_price")
        if not self.price:
            raise ValueError("A bracket order requires an entry price (used as the GTT/reference entry)")
        if self.trailing_amount is not None and self.trailing_amount <= 0:
            raise ValueError("trailing_amount must be greater than 0")

        # Ordering must be sane for the direction of the entry, regardless of broker —
        # a backwards bracket (e.g. stop above target on a BUY) is a real hazard, not
        # just a UX nicety.
        if self.transaction_type == "BUY":
            if not (self.stop_price < self.price < self.target_price):
                raise ValueError("For a BUY bracket, stop-loss must be below entry price, which must be below target")
        else:
            if not (self.target_price < self.price < self.stop_price):
                raise ValueError("For a SELL bracket, target must be below entry price, which must be below stop-loss")
        return self

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v):
        return v.strip().upper()


class OrderError(Exception):
    """Raised when a broker rejects or fails to process an order request."""


async def place_order(db: AsyncSession, user: User, req: OrderRequest) -> dict:
    """Place a live order (optionally with a bracket) on the user's chosen linked account."""
    conn = await get_connection_for_user(db, user.id, req.account_id)
    if not conn:
        raise OrderError("That account is not linked to your profile.")
    if not conn.is_connected or not conn.access_token_encrypted:
        raise OrderError(f"{conn.nickname or conn.provider.title()} is not connected. Reconnect it in Settings.")

    token = decrypt_token(conn.access_token_encrypted)
    account_label = conn.nickname or f"{conn.provider.title()} account"

    logger.info(
        "order_place_attempt",
        user_id=str(user.id),
        account_id=str(conn.id),
        provider=conn.provider,
        symbol=req.symbol,
        side=req.transaction_type,
        quantity=req.quantity,
        order_type=req.order_type,
        bracket=req.has_bracket,
        trailing=bool(req.trailing_amount),
    )

    try:
        if conn.provider == "upstox":
            result = await _place_upstox_order(token, req)
        elif conn.provider == "kite":
            result = await _place_kite_order(db, token, req)
        else:
            raise OrderError(f"Order placement is not supported for provider '{conn.provider}'.")
    except (UpstoxAPIError, KiteException) as e:
        logger.warning(
            "order_place_failed",
            user_id=str(user.id),
            account_id=str(conn.id),
            provider=conn.provider,
            error=str(e),
        )
        raise OrderError(str(e))

    if req.has_bracket:
        db.add(
            TrackedBracket(
                user_id=user.id,
                account_id=conn.id,
                provider=conn.provider,
                symbol=req.symbol,
                instrument_token=result.get("instrument_token"),
                transaction_type=req.transaction_type,
                product=req.product,
                quantity=req.quantity,
                entry_price=req.price,
                target_price=req.target_price,
                stop_price=req.stop_price,
                trailing_amount=req.trailing_amount,
                high_water_mark=req.price,
                broker_ref=str(result.get("bracket_ref")) if result.get("bracket_ref") is not None else None,
                status="ACTIVE",
            )
        )
        await db.commit()

    logger.info(
        "order_place_succeeded",
        user_id=str(user.id),
        account_id=str(conn.id),
        provider=conn.provider,
        order_id=result.get("order_id"),
    )
    return {
        "order_id": result.get("order_id"),
        "status": result.get("status"),
        "provider": conn.provider,
        "account_nickname": account_label,
        "bracket_placed": req.has_bracket,
    }


async def _place_upstox_order(token: str, req: OrderRequest) -> dict:
    provider = UpstoxDataProvider(access_token=token)
    instrument_token = await provider.resolve_instrument_key(req.symbol)

    if req.has_bracket:
        # The GTT *is* the entry mechanism here — see provider.place_gtt's docstring.
        response = await provider.place_gtt(
            instrument_token=instrument_token,
            transaction_type=req.transaction_type,
            quantity=req.quantity,
            product=UPSTOX_PRODUCT[req.product],
            entry_trigger_type="IMMEDIATE",
            entry_price=req.price,
            target_price=req.target_price,
            stop_price=req.stop_price,
            trailing_gap=req.trailing_amount,
        )
        data = response.get("data") or {}
        gtt_ids = data.get("gtt_order_ids") or []
        return {
            "order_id": gtt_ids[0] if gtt_ids else None,
            "status": response.get("status") or "placed",
            "bracket_ref": gtt_ids[0] if gtt_ids else None,
            "instrument_token": instrument_token,
            "raw": data,
        }

    response = await provider.place_order(
        instrument_token=instrument_token,
        transaction_type=req.transaction_type,
        quantity=req.quantity,
        order_type=req.order_type,
        product=UPSTOX_PRODUCT[req.product],
        price=req.price or 0,
        validity=req.validity,
    )
    data = response.get("data") or {}
    order_ids = data.get("order_ids") or []
    return {
        "order_id": order_ids[0] if order_ids else None,
        "status": response.get("status") or "placed",
        "instrument_token": instrument_token,
        "raw": data,
    }


async def _place_kite_order(db: AsyncSession, token: str, req: OrderRequest) -> dict:
    creds = await get_broker_credentials(db, "kite")
    kite = KiteConnect(api_key=creds["client_id"], access_token=token)

    order_id = await asyncio.to_thread(
        kite.place_order,
        variety=KiteConnect.VARIETY_REGULAR,
        exchange=KiteConnect.EXCHANGE_NSE,
        tradingsymbol=req.symbol,
        transaction_type=req.transaction_type,
        quantity=req.quantity,
        product=KITE_PRODUCT[req.product],
        order_type=req.order_type,
        price=req.price if req.order_type == "LIMIT" else None,
        validity=req.validity,
    )

    if not req.has_bracket:
        return {"order_id": order_id, "status": "placed", "raw": {"order_id": order_id}}

    exit_side = "SELL" if req.transaction_type == "BUY" else "BUY"
    product = KITE_PRODUCT[req.product]
    # Kite expects trigger_values ascending; map each to its corresponding order.
    lo_price, hi_price = sorted([req.stop_price, req.target_price])
    lo_order = {"transaction_type": exit_side, "quantity": req.quantity, "order_type": "LIMIT", "product": product, "price": lo_price}
    hi_order = {"transaction_type": exit_side, "quantity": req.quantity, "order_type": "LIMIT", "product": product, "price": hi_price}

    try:
        gtt_result = await asyncio.to_thread(
            kite.place_gtt,
            trigger_type=KiteConnect.GTT_TYPE_OCO,
            tradingsymbol=req.symbol,
            exchange=KiteConnect.EXCHANGE_NSE,
            trigger_values=[lo_price, hi_price],
            last_price=req.price,
            orders=[lo_order, hi_order],
        )
    except KiteException as e:
        # Entry already filled/queued — surface the bracket failure distinctly so the
        # user knows their entry went through but isn't protected yet.
        logger.error("kite_bracket_gtt_failed", order_id=order_id, error=str(e))
        raise OrderError(
            f"Entry order {order_id} was placed, but the protective target/stop-loss GTT failed: {e}. "
            "Place the stop-loss manually on Kite."
        )

    trigger_id = gtt_result.get("trigger_id") if isinstance(gtt_result, dict) else gtt_result
    return {"order_id": order_id, "status": "placed", "bracket_ref": trigger_id, "raw": {"order_id": order_id, "gtt": gtt_result}}


def serialize_bracket(b: TrackedBracket) -> dict:
    return {
        "id": str(b.id),
        "provider": b.provider,
        "symbol": b.symbol,
        "transaction_type": b.transaction_type,
        "quantity": b.quantity,
        "entry_price": float(b.entry_price) if b.entry_price is not None else None,
        "target_price": float(b.target_price) if b.target_price is not None else None,
        "stop_price": float(b.stop_price) if b.stop_price is not None else None,
        "trailing_amount": float(b.trailing_amount) if b.trailing_amount is not None else None,
        "status": b.status,
        "last_error": b.last_error,
        "last_trailed_at": b.last_trailed_at.isoformat() if b.last_trailed_at else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


async def list_brackets(db: AsyncSession, user: User) -> list[dict]:
    result = await db.execute(
        select(TrackedBracket).where(TrackedBracket.user_id == user.id).order_by(TrackedBracket.created_at.desc())
    )
    return [serialize_bracket(b) for b in result.scalars().all()]


async def cancel_bracket(db: AsyncSession, user: User, bracket_id: UUID) -> dict:
    """Cancel the broker-side GTT behind a tracked bracket and mark it cancelled."""
    result = await db.get(TrackedBracket, bracket_id)
    if not result or result.user_id != user.id:
        raise OrderError("Bracket not found.")
    if result.status != "ACTIVE":
        raise OrderError(f"Bracket is already {result.status.lower()}.")

    conn = await get_connection_for_user(db, user.id, result.account_id)
    if not conn or not conn.access_token_encrypted:
        raise OrderError("The linked account for this bracket is no longer connected.")
    token = decrypt_token(conn.access_token_encrypted)

    try:
        if result.provider == "upstox":
            provider = UpstoxDataProvider(access_token=token)
            await provider.cancel_gtt(result.broker_ref)
        elif result.provider == "kite":
            creds = await get_broker_credentials(db, "kite")
            kite = KiteConnect(api_key=creds["client_id"], access_token=token)
            await asyncio.to_thread(kite.delete_gtt, int(result.broker_ref))
    except (UpstoxAPIError, KiteException) as e:
        raise OrderError(f"Could not cancel at the broker: {e}")

    result.status = "CANCELLED"
    await db.commit()
    return serialize_bracket(result)
