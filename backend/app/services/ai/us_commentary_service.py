"""
StockMind AI — US Stock "AI Research Notes"
Dispatches per call between two prompt/context families based on whether real
data is available for the requested symbol (Alpaca configured and returning
candles):
  - Real data -> the institutional-grade US_SINGLE_STOCK_ANALYSIS_PROMPT with
    a compact context built from analyze_us_stock()'s output + SEC EDGAR
    fundamentals (mirrors commentary_service.py's _build_context style).
  - No real data (Alpaca not configured, or this symbol's fetch failed) ->
    the existing GENERAL_KNOWLEDGE-only US_RESEARCH_PROMPT, unchanged.
Reuses commentary_service.py's model-dispatch helper (_call_model) and a few
feature-snapshot formatters (_round/_macd_text/_compact_indicators — these
operate on FeatureEngine's output, which is identical for US and Indian
stocks) — the system prompts, cache table (USCommentaryCache) and context
builders are otherwise fully separate, so nothing about the live Indian AI
commentary path is touched.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.paper_trading import USCommentaryCache
from app.models.user import User
from app.services.ai.ai_config import get_settings
from app.services.ai.commentary_service import CommentaryError, _call_model, _compact_indicators, _macd_text, _round
from app.services.analytics.us_research_prompt import US_RESEARCH_PROMPT
from app.services.analytics.us_single_stock_analysis_prompt import US_SINGLE_STOCK_ANALYSIS_PROMPT
from app.services.us_market.analysis import analyze_us_stock
from app.services.us_market.provider import USDataUnavailableError, get_us_provider
from app.services.us_market.sec_compaction import compact_fundamentals, fundamentals_to_context_text
from app.services.us_market.sec_edgar_client import get_company_facts

logger = get_logger(__name__)


def _build_us_general_context(symbol: str, sector: str) -> str:
    return (
        f"Ticker: {symbol}\nSector (StockMind's own classification, not live data): {sector}\n\n"
        "StockMind has no live market data for this ticker (see system prompt). Give the general "
        "business overview described in your instructions."
    )


def _build_us_real_data_context(analysis: dict, fundamentals: Optional[dict]) -> str:
    s = analysis.get("signal") or {}
    ee = s.get("entry_exit") or {}
    tech = s.get("technical") or {}
    pos = s.get("position") or {}
    predictions = analysis.get("predictions") or {}
    evidence = s.get("evidence") or {}
    q = analysis.get("quote") or {}
    snapshot = next((p.get("feature_snapshot") for p in predictions.values() if p.get("feature_snapshot")), None)

    lines = [
        f"Symbol: {analysis.get('symbol')} ({analysis.get('name', '')}, sector: {analysis.get('sector', '')})",
        f"Signal: {(s.get('signal') or {}).get('entry', 'unknown')} / {(s.get('signal') or {}).get('type', '')}",
        f"Technicals: RSI {tech.get('rsi')}, ADX {tech.get('adx')}, MACD {_macd_text(snapshot)}, "
        f"volume ratio {tech.get('volume_ratio')}, trend {tech.get('trend')}",
        f"Entry zone: {ee.get('entry_zone')} | Stop-loss: {ee.get('stop_loss')} | "
        f"Target 1/2: {ee.get('target_1')}/{ee.get('target_2')} | R:R {ee.get('risk_reward')}",
        f"Suggested position (default ${analysis.get('portfolio', {}).get('capital')} paper-trading capital): "
        f"{pos.get('quantity')} shares, value {pos.get('value')}, risk {pos.get('max_risk')}",
    ]

    holding = s.get("holding") or {}
    if holding.get("is_holding"):
        lines.append(
            f"EXISTING PAPER-TRADING POSITION (StockMind's own ledger, not a live broker) — engine says: {holding.get('action')}"
        )

    if q.get("data_available"):
        ohlc = q.get("ohlc") or {}
        lines.append(
            f"Quote: LTP {_round(q.get('ltp'))} (chg {_round(q.get('change'))}, {_round(q.get('change_pct'))}%), "
            f"O/H/L {_round(ohlc.get('open'))}/{_round(ohlc.get('high'))}/{_round(ohlc.get('low'))}, "
            f"volume {q.get('volume')}. {q.get('feed_note', '')}"
        )

    indicators_text = _compact_indicators(snapshot)
    if indicators_text:
        lines.append(f"Other indicators: {indicators_text}")

    if evidence.get("positive"):
        lines.append("Supporting evidence: " + "; ".join(e.get("factor", "") for e in evidence["positive"][:5]))
    if evidence.get("negative"):
        lines.append("Opposing evidence: " + "; ".join(e.get("factor", "") for e in evidence["negative"][:5]))

    for horizon, p in predictions.items():
        dp = p.get("direction_probabilities", {})
        lines.append(
            f"{horizon} model outlook: up {dp.get('up')}, flat {dp.get('flat')}, down {dp.get('down')}, "
            f"expected return {p.get('expected_return')}, confidence {p.get('confidence')}"
        )
    if analysis.get("technical_summary"):
        lines.append(f"Technical summary: {analysis['technical_summary']}")

    news_list = analysis.get("news")
    if news_list:
        headlines = [f"{n.get('heading')} ({n.get('published_at')})" for n in news_list[:8] if n.get("heading")]
        if headlines:
            lines.append("\n--- Recent news (Alpaca/Benzinga) ---\n" + "\n".join(f"- {h}" for h in headlines))

    if fundamentals:
        lines.append("\n--- Fundamentals (SEC EDGAR, annual) ---")
        lines.append(fundamentals_to_context_text(fundamentals))
    else:
        lines.append("\nFundamentals: Data unavailable / not verified (no SEC EDGAR filings found).")

    lines.append(
        "\nProduce the full report structure defined in your system prompt for this stock. Where a section's "
        "data wasn't provided above, say so explicitly (per your FACT/MODEL_PREDICTION/ANALYST_INTERPRETATION/"
        "DATA_NOT_VERIFIED rules) rather than inventing numbers. Be concise: the app already shows the numeric "
        "tables above to the reader next to your commentary, so don't restate them in full — spend your words "
        "on interpretation, and explicitly call out whether this looks favorable for short-term (~5D), "
        "medium-term (~20D) and long-term (structural) holding."
    )
    return "\n".join(lines)


async def generate_us_research(db: AsyncSession, user: Optional[User], symbol: str) -> dict:
    """Generate (or return cached) AI notes for a US symbol — the real-data
    prompt when analyze_us_stock() reports data_available, the GENERAL_KNOWLEDGE
    fallback otherwise. Raises CommentaryError on failure (not configured,
    symbol not approved, model API error)."""
    provider = await get_us_provider(db)
    try:
        inst = await provider.resolve_instrument(symbol)
    except USDataUnavailableError as e:
        raise CommentaryError(str(e))

    settings = await get_settings(db)
    if not settings["configured"]:
        raise CommentaryError(
            f"{settings['provider'].title()} API key not configured. Add it in Settings → AI Commentary."
        )

    analysis = await analyze_us_stock(provider, symbol, user, db)

    if analysis.get("data_available"):
        facts = await get_company_facts(inst["symbol"])
        fundamentals = compact_fundamentals(facts) if facts else None
        prompt_content = US_SINGLE_STOCK_ANALYSIS_PROMPT
        context = _build_us_real_data_context(analysis, fundamentals)
        family = "real"
        max_tokens = 8192
    else:
        prompt_content = US_RESEARCH_PROMPT
        context = _build_us_general_context(inst["symbol"], inst["sector"])
        family = "general"
        max_tokens = 1024

    context_hash = hashlib.sha256(f"{family}:{inst['symbol']}:{prompt_content}:{context}".encode()).hexdigest()

    cached = await db.execute(
        select(USCommentaryCache)
        .where(USCommentaryCache.symbol == inst["symbol"], USCommentaryCache.context_hash == context_hash)
        .order_by(USCommentaryCache.created_at.desc())
        .limit(1)
    )
    row = cached.scalar_one_or_none()
    if row is not None:
        return {
            "content": row.content, "model": row.model_used, "cached": True,
            "data_backed": family == "real", "generated_at": row.created_at.isoformat(),
        }

    try:
        text = await _call_model(
            settings["provider"], settings["model"], settings["api_key"],
            prompt_content, context, None, max_tokens=max_tokens,
        )
    except CommentaryError as e:
        logger.error("us_research_failed", symbol=inst["symbol"], provider=settings["provider"], family=family, error=str(e))
        raise

    row = USCommentaryCache(symbol=inst["symbol"], context_hash=context_hash, content=text, model_used=settings["model"])
    db.add(row)
    await db.commit()

    logger.info("us_research_generated", symbol=inst["symbol"], model=settings["model"], family=family)
    return {
        "content": text, "model": settings["model"], "cached": False,
        "data_backed": family == "real", "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def list_recent_research(db: AsyncSession, limit: int = 5) -> list[dict]:
    """Most recently generated US research notes, one row per distinct symbol
    (a symbol re-generated multiple times only counts once, at its latest
    timestamp) — for the Dashboard's "Recent US Analysis" panel."""
    result = await db.execute(
        select(USCommentaryCache).order_by(USCommentaryCache.created_at.desc()).limit(limit * 4)
    )
    rows = result.scalars().all()
    seen: set[str] = set()
    recent = []
    for row in rows:
        if row.symbol in seen:
            continue
        seen.add(row.symbol)
        recent.append({"symbol": row.symbol, "model": row.model_used, "generated_at": row.created_at.isoformat()})
        if len(recent) >= limit:
            break
    return recent
