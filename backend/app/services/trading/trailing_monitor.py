"""
StockMind AI — Kite Trailing Stop-Loss Monitor
Kite's API has no native trailing stop-loss (confirmed against Kite Connect's
GTT docs), unlike Upstox whose GTT `trailing_gap` is broker-native and needs
no help from us. For Kite brackets with `trailing_amount` set, this loop polls
the current LTP every `trailing_poll_seconds` and, whenever price has moved
favorably by at least that gap since the last adjustment, raises (long) or
lowers (short) the GTT's stop-loss trigger via `modify_gtt` — never regresses
it. This only protects the position while this backend process is running;
that limitation is stated in the UI, not hidden.
"""

import asyncio
from datetime import datetime, timezone

from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decrypt_token
from app.database import async_session_factory
from app.models.tracked_bracket import TrackedBracket
from app.models.user import OAuthConnection
from app.services.broker_config import get_credentials as get_broker_credentials
from app.services.upstox.client import UpstoxDataUnavailableError
from app.services.upstox.provider import UpstoxDataProvider

logger = get_logger(__name__)

KITE_PRODUCT = {"DELIVERY": "CNC", "INTRADAY": "MIS"}

# A single shared, token-less provider for LTP lookups — market data is public
# regardless of which broker account will execute the trade.
_quote_provider: UpstoxDataProvider | None = None


async def _get_ltp(symbol: str) -> float | None:
    global _quote_provider
    from app.config import get_settings

    settings = get_settings()
    if not settings.upstox_analytics_token:
        return None
    if _quote_provider is None:
        _quote_provider = UpstoxDataProvider(access_token=settings.upstox_analytics_token)
    try:
        key = await _quote_provider.resolve_instrument_key(symbol)
        response = await _quote_provider.get_ltp([key])
        data = response.get("data") or {}
        quote = next(iter(data.values()), None)
        return quote.get("last_price") if quote else None
    except UpstoxDataUnavailableError as e:
        logger.warning("trailing_monitor_ltp_unavailable", symbol=symbol, error=str(e))
        return None


async def tick() -> None:
    """One monitoring pass over every active, trailing Kite bracket."""
    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(TrackedBracket).where(
                    TrackedBracket.provider == "kite",
                    TrackedBracket.status == "ACTIVE",
                    TrackedBracket.trailing_amount.isnot(None),
                )
            )
            brackets = result.scalars().all()
            if not brackets:
                return

            for bracket in brackets:
                try:
                    await _trail_one(db, bracket)
                except Exception as e:
                    logger.error("trailing_monitor_bracket_failed", bracket_id=str(bracket.id), symbol=bracket.symbol, error=str(e))
                    bracket.last_error = str(e)[:500]

            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _trail_one(db: AsyncSession, bracket: TrackedBracket) -> None:
    ltp = await _get_ltp(bracket.symbol)
    if ltp is None:
        return

    is_long = bracket.transaction_type == "BUY"
    trail = float(bracket.trailing_amount)
    hwm = float(bracket.high_water_mark or bracket.entry_price)
    current_stop = float(bracket.stop_price)

    improved = ltp > hwm if is_long else ltp < hwm
    if improved:
        bracket.high_water_mark = ltp
        hwm = ltp

    new_stop = hwm - trail if is_long else hwm + trail
    should_trail = (new_stop > current_stop) if is_long else (new_stop < current_stop)
    if not should_trail:
        return

    conn = await db.get(OAuthConnection, bracket.account_id)
    if not conn or not conn.is_connected or not conn.access_token_encrypted:
        bracket.last_error = "Linked Kite account is no longer connected"
        return

    token = decrypt_token(conn.access_token_encrypted)
    creds = await get_broker_credentials(db, "kite")
    kite = KiteConnect(api_key=creds["client_id"], access_token=token)

    exit_side = "SELL" if is_long else "BUY"
    product = KITE_PRODUCT.get(bracket.product, "CNC")
    lo_price, hi_price = sorted([new_stop, float(bracket.target_price)])
    orders = [
        {"transaction_type": exit_side, "quantity": bracket.quantity, "order_type": "LIMIT", "product": product, "price": lo_price},
        {"transaction_type": exit_side, "quantity": bracket.quantity, "order_type": "LIMIT", "product": product, "price": hi_price},
    ]

    try:
        await asyncio.to_thread(
            kite.modify_gtt,
            trigger_id=int(bracket.broker_ref),
            trigger_type=KiteConnect.GTT_TYPE_OCO,
            tradingsymbol=bracket.symbol,
            exchange=KiteConnect.EXCHANGE_NSE,
            trigger_values=[lo_price, hi_price],
            last_price=ltp,
            orders=orders,
        )
    except KiteException as e:
        logger.error("trailing_modify_gtt_failed", bracket_id=str(bracket.id), symbol=bracket.symbol, error=str(e))
        bracket.last_error = str(e)[:500]
        return

    bracket.stop_price = new_stop
    bracket.last_trailed_at = datetime.now(timezone.utc)
    bracket.last_error = None
    logger.info(
        "trailing_stop_adjusted",
        bracket_id=str(bracket.id),
        symbol=bracket.symbol,
        new_stop=new_stop,
        ltp=ltp,
    )


async def run_forever(poll_seconds: int) -> None:
    """Background loop — started from app.main's lifespan, cancelled on shutdown."""
    logger.info("trailing_monitor_started", poll_seconds=poll_seconds)
    while True:
        await asyncio.sleep(poll_seconds)
        try:
            await tick()
        except Exception as e:
            logger.error("trailing_monitor_tick_failed", error=str(e))
