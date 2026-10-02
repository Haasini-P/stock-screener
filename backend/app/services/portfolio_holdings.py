"""
StockMind AI — Live Holdings Lookup
Shared helper so Scanner/Daily Signals/Stock Report can recognize symbols the
user already holds (to recommend ADD/HOLD/REDUCE instead of a blanket AVOID)
without SignalEngine's pure scoring logic doing any I/O itself.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.user import User
from app.services.upstox.auth import UpstoxAuthService
from app.services.upstox.provider import UpstoxDataProvider

logger = get_logger(__name__)


async def get_held_symbols(user: Optional[User], db: AsyncSession) -> set[str]:
    """
    Trading symbols in the user's connected Upstox holdings, or an empty set
    if there's no logged-in user, no connected broker, or the lookup fails —
    "holdings unknown" is treated the same as "not held", never as a reason
    to block the rest of the analysis.
    """
    if not user:
        return set()
    try:
        token = await UpstoxAuthService(db).get_access_token(user.id)
        if not token:
            return set()
        provider = UpstoxDataProvider(access_token=token)
        holdings = await provider.get_holdings()
        rows = holdings.get("data") or []
        return {h["trading_symbol"].upper() for h in rows if h.get("trading_symbol")}
    except Exception as e:
        logger.warning("held_symbols_lookup_failed", user_id=str(user.id), error=str(e))
        return set()
