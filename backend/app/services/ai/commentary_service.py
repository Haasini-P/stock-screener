"""
StockMind AI — Claude-Powered Stock Commentary
Generates on-demand AI commentary for a stock using the stored system prompt
(app/services/analytics/prompt_service.py) and the same analysis data already
shown on the Stock Report. This is the first thing that actually reads the
system prompt — previously it was edited but never used anywhere.

Always on-demand, never automatic: commentary can be requested from the
Scanner, Daily Signals, and Stock Report, all of which can list many stocks
at once, so every call is cached per (symbol, context_hash, day) to avoid
re-billing the Claude API for an unchanged signal.
"""

import asyncio
import base64
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.ai_commentary import AIBatchCommentary, AICommentary
from app.models.user import User
from app.services.ai.ai_config import get_settings
from app.services.ai.chart_renderer import render_candlestick_chart
from app.services.analytics.prompt_service import get_current_prompt

logger = get_logger(__name__)

MODEL_PRICING = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}

MAX_BATCH_SYMBOLS = 8


class CommentaryError(Exception):
    """Raised when commentary can't be generated (not configured, or the API call failed)."""


def _build_context(analysis: dict, fundamentals: Optional[dict], regime: Optional[dict]) -> str:
    """A structured brief from data this app already computes — analysis from
    /api/signals/analyze/{symbol}, fundamentals from /api/stocks/{symbol}/fundamentals,
    and the live market regime. Covers what the detailed research-report system
    prompt expects: technicals/signal/predictions, valuation/fundamentals, and
    market context — so its sections have real numbers instead of "not available"."""
    s = analysis.get("signal") or {}
    ee = s.get("entry_exit") or {}
    tech = s.get("technical") or {}
    pos = s.get("position") or {}
    predictions = analysis.get("predictions") or {}
    evidence = s.get("evidence") or {}
    q = analysis.get("quote") or {}

    fundamental_signal = s.get("fundamental") or {}

    lines = [
        f"Symbol: {analysis.get('symbol')} ({analysis.get('name', '')})",
        f"Regime: {analysis.get('metadata', {}).get('regime', 'unknown')}",
        f"Signal: {(s.get('signal') or {}).get('entry', 'unknown')} / {(s.get('signal') or {}).get('type', '')}",
        f"Technicals: RSI {tech.get('rsi')}, ADX {tech.get('adx')}, MACD {tech.get('macd')}, "
        f"volume ratio {tech.get('volume_ratio')}, trend {tech.get('trend')}",
        f"Entry zone: {ee.get('entry_zone')} | Stop-loss: {ee.get('stop_loss')} | "
        f"Target 1/2: {ee.get('target_1')}/{ee.get('target_2')} | R:R {ee.get('risk_reward')}",
        f"Suggested position: {pos.get('quantity')} shares, value {pos.get('value')}, risk {pos.get('max_risk')}",
    ]
    if fundamental_signal:
        lines.append(
            f"Quick fundamentals (rule engine): P/E {fundamental_signal.get('pe')}, ROE {fundamental_signal.get('roe')}, "
            f"revenue growth {fundamental_signal.get('revenue_growth')} — {fundamental_signal.get('summary', '')}"
        )
    if q:
        lines.append(f"Quote data: {json.dumps(q)[:1500]}")

    # Full computed indicator set (MACD value/signal, Bollinger, Stochastic, ATR,
    # support/resistance, 52-week range, VWAP, volume z-score, etc.) — every
    # horizon's prediction carries the same snapshot, so any one horizon will do.
    snapshot = next((p.get("feature_snapshot") for p in predictions.values() if p.get("feature_snapshot")), None)
    if snapshot:
        lines.append(f"Full technical indicator snapshot: {json.dumps(snapshot)[:3000]}")

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

    news_items = analysis.get("news")
    news_list = news_items.get("news") if isinstance(news_items, dict) else news_items
    if news_list:
        headlines = []
        for n in news_list[:8]:
            heading = n.get("heading") or n.get("title") or n.get("headline")
            published = n.get("published_at") or n.get("publishedAt") or n.get("date")
            if heading:
                headlines.append(f"{heading} ({published})" if published else heading)
        if headlines:
            lines.append("\n--- Recent news (from Upstox) ---\n" + "\n".join(f"- {h}" for h in headlines))

    if fundamentals:
        lines.append("\n--- Fundamentals (from Upstox) ---")
        if fundamentals.get("profile"):
            lines.append(f"Profile: {json.dumps(fundamentals['profile'])[:1000]}")
        if fundamentals.get("key_ratios"):
            lines.append(f"Key ratios: {json.dumps(fundamentals['key_ratios'])[:1500]}")
        if fundamentals.get("shareholding"):
            lines.append(f"Shareholding: {json.dumps(fundamentals['shareholding'])[:1000]}")
        if fundamentals.get("corporate_actions"):
            lines.append(f"Corporate actions: {json.dumps(fundamentals['corporate_actions'])[:800]}")
        if fundamentals.get("competitors"):
            lines.append(f"Peers/competitors: {json.dumps(fundamentals['competitors'])[:1200]}")
        if fundamentals.get("unavailable"):
            lines.append(f"Not available from Upstox for this stock: {', '.join(fundamentals['unavailable'])}")

    if regime:
        lines.append("\n--- Market context (live) ---")
        indian = regime.get("indian_market", {})
        lines.append(
            f"Regime: {regime.get('regime')} (mood: {regime.get('mood')}). "
            f"Nifty50 change {indian.get('nifty_50', {}).get('change')}%, "
            f"India VIX {indian.get('india_vix', {}).get('value')}. "
            f"FII trend: {regime.get('institutional', {}).get('fii_trend')}, "
            f"DII trend: {regime.get('institutional', {}).get('dii_trend')}. "
            f"Strong sectors: {regime.get('sectors', {}).get('strong')}, "
            f"weak sectors: {regime.get('sectors', {}).get('weak')}."
        )
        # Crude oil, INR, US markets/Treasury yields and global risk sentiment are
        # fields this app's regime schema has reserved but never wires to a real data
        # source — always null today. Say so plainly rather than silently omitting
        # them, so "Market context" doesn't look guessed when it reports them unverifiable.
        lines.append(
            "Note: this app does not currently source crude oil, INR, US market indices, "
            "US Treasury yields or global risk sentiment from any provider — treat those as "
            "DATA_NOT_VERIFIED rather than inferring them."
        )

    lines.append(
        "\nProduce the full report structure defined in your system prompt for this stock. Where a section's "
        "data wasn't provided above, say so explicitly (per your FACT/ESTIMATE/OPINION rules) rather than "
        "inventing numbers — do not skip a section silently, just mark it not verifiable from available data."
    )
    return "\n".join(lines)


def _context_hash(symbol: str, context: str, prompt_content: str) -> str:
    """
    Folds the current system prompt's content into the cache key — otherwise
    editing the prompt in Settings would silently have no effect on any stock
    whose market-data context hasn't changed since it was last cached.
    """
    return hashlib.sha256(f"{symbol}:{prompt_content}:{context}".encode()).hexdigest()


async def generate_commentary(db: AsyncSession, user: Optional[User], symbol: str) -> dict:
    """Generate (or return cached) AI commentary for a symbol. Raises CommentaryError on failure."""
    settings = await get_settings(db)
    if not settings["configured"]:
        raise CommentaryError(
            "Claude API key not configured. Add it in Settings → AI Commentary."
        )

    # Reuse the exact same analysis/fundamentals/regime logic the rest of the app already has —
    # no duplicate data-fetching code, and it stays in sync if those change.
    from app.api.routes.market import get_market_provider, get_stock_fundamentals
    from app.api.routes.signals import analyze_stock
    from app.services.analytics.market_state import get_market_state

    try:
        analysis = await analyze_stock(symbol, 200000, 0.75, user, db)
    except Exception as e:
        raise CommentaryError(f"Could not load analysis for {symbol}: {e}")

    fundamentals = None
    try:
        fundamentals = await get_stock_fundamentals(symbol, user, db)
    except Exception as e:
        logger.warning("ai_commentary_fundamentals_unavailable", symbol=symbol, error=str(e))

    regime = None
    try:
        provider = await get_market_provider(user, db)
        state = await get_market_state(provider)
        regime = state["regime"]
    except Exception as e:
        logger.warning("ai_commentary_regime_unavailable", symbol=symbol, error=str(e))

    # A real candlestick-plus-volume chart (with 20/50/200-day MAs) rendered from the
    # same Upstox OHLCV candles the rest of the app uses — this is the only way the
    # model actually "sees" price structure/wicks instead of inferring it from numbers.
    chart_png = None
    try:
        provider = await get_market_provider(user, db)
        instrument_key = analysis.get("instrument_key")
        if instrument_key:
            from_date = (date.today() - timedelta(days=300)).isoformat()
            candle_response = await provider.get_historical_candles(instrument_key, "day", from_date=from_date)
            candle_rows = (candle_response.get("data") or {}).get("candles") or []
            chart_png = render_candlestick_chart(candle_rows, symbol.upper())
    except Exception as e:
        logger.warning("ai_commentary_chart_unavailable", symbol=symbol, error=str(e))

    context = _build_context(analysis, fundamentals, regime)
    if chart_png:
        context += "\n\nA candlestick chart (with 20/50/200-day moving averages, where enough history exists) is attached as an image — use it for price-structure, support/resistance and candle-pattern analysis (section 6/7)."

    prompt_row = await get_current_prompt(db)
    context_hash = _context_hash(symbol, context, prompt_row.content)

    cached = await db.execute(
        select(AICommentary)
        .where(AICommentary.symbol == symbol.upper(), AICommentary.context_hash == context_hash)
        .order_by(AICommentary.created_at.desc())
        .limit(1)
    )
    row = cached.scalar_one_or_none()
    if row is not None:
        return {
            "content": row.content, "model": row.model_used, "cached": True,
            "chart_included": row.chart_included, "generated_at": row.created_at.isoformat(),
        }

    client = anthropic.Anthropic(api_key=settings["api_key"])

    user_content: list[dict] = []
    if chart_png:
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(chart_png).decode()},
        })
    user_content.append({"type": "text", "text": context})

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=settings["model"],
            # The full research-report system prompt asks for ~16 structured
            # sections — 600 tokens (a quick take) isn't nearly enough for it.
            max_tokens=4096,
            system=prompt_row.content,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIError as e:
        logger.error("ai_commentary_failed", symbol=symbol, error=str(e))
        raise CommentaryError(f"Claude API error: {e}")

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise CommentaryError("Claude returned an empty response.")

    row = AICommentary(
        symbol=symbol.upper(),
        context_hash=context_hash,
        content=text,
        model_used=settings["model"],
        chart_included=bool(chart_png),
    )
    db.add(row)
    await db.commit()

    logger.info("ai_commentary_generated", symbol=symbol, model=settings["model"], chart_included=bool(chart_png))
    return {
        "content": text, "model": settings["model"], "cached": False,
        "chart_included": bool(chart_png), "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _quick_context(analysis: dict) -> str:
    """A condensed per-stock brief for the multi-stock batch scan — deliberately
    lighter than _build_context (no fundamentals/regime/chart) so a batch of
    several stocks in one call stays cheap, per the "combined call" tradeoff."""
    s = analysis.get("signal") or {}
    ee = s.get("entry_exit") or {}
    tech = s.get("technical") or {}
    q = analysis.get("quote") or {}
    evidence = s.get("evidence") or {}
    predictions = analysis.get("predictions") or {}
    p5d = predictions.get("5D") or next(iter(predictions.values()), {})
    dp = p5d.get("direction_probabilities", {})

    lines = [
        f"### {analysis.get('symbol')} ({analysis.get('name', '')})",
        f"CMP: {q.get('last_price', 'n/a')} | Signal: {(s.get('signal') or {}).get('entry', 'unknown')} | "
        f"RSI {tech.get('rsi')}, trend {tech.get('trend')}",
        f"Entry: {ee.get('entry_zone')} | Stop: {ee.get('stop_loss')} | Target: {ee.get('target_1')} | R:R {ee.get('risk_reward')}",
        f"5D model: up {dp.get('up')}, down {dp.get('down')}, confidence {p5d.get('confidence')}",
    ]
    top_positive = (evidence.get("positive") or [{}])[0].get("factor")
    top_negative = (evidence.get("negative") or [{}])[0].get("factor")
    if top_positive:
        lines.append(f"Top positive: {top_positive}")
    if top_negative:
        lines.append(f"Top risk: {top_negative}")
    return "\n".join(lines)


async def generate_batch_commentary(db: AsyncSession, user: Optional[User], symbols: list[str]) -> dict:
    """
    One cheaper, shallower Claude call covering several stocks at once — a
    condensed verdict per stock rather than the full 16-section report.
    """
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    if not symbols:
        raise CommentaryError("No symbols given.")
    if len(symbols) > MAX_BATCH_SYMBOLS:
        raise CommentaryError(f"Batch analysis is capped at {MAX_BATCH_SYMBOLS} stocks at a time (got {len(symbols)}).")

    settings = await get_settings(db)
    if not settings["configured"]:
        raise CommentaryError("Claude API key not configured. Add it in Settings → AI Commentary.")

    from app.api.routes.signals import analyze_stock

    sorted_symbols = sorted(set(symbols))
    blocks = []
    failed = []
    for symbol in sorted_symbols:
        try:
            analysis = await analyze_stock(symbol, 200000, 0.75, user, db)
            blocks.append(_quick_context(analysis))
        except Exception as e:
            logger.warning("ai_batch_commentary_symbol_failed", symbol=symbol, error=str(e))
            failed.append(symbol)

    if not blocks:
        raise CommentaryError("Could not load analysis for any of the given symbols.")

    context = (
        "This is a MULTI-STOCK QUICK SCAN, not a single deep-dive report. For EACH stock below, "
        "give a condensed verdict in this exact shape — do not use the full 16-section report format "
        "from your system prompt for this request:\n\n"
        "**SYMBOL** — FINAL ACTION (one of: BUY NOW — SMALL STARTER / BUY ON DIP / WAIT FOR BREAKOUT "
        "CONFIRMATION / WATCH / AVOID) — one-line reason citing the specific numbers given, labeled "
        "FACT/ESTIMATE/OPINION per your system prompt's rules. Also flag if the stock is already in my "
        "listed holdings (existing holding — do not recommend fresh allocation).\n\n"
        + "\n\n".join(blocks)
    )
    if failed:
        context += f"\n\n(Could not load data for: {', '.join(failed)} — mark these DATA_NOT_VERIFIED, don't guess.)"

    symbols_key = ",".join(sorted_symbols)
    prompt_row = await get_current_prompt(db)
    context_hash = hashlib.sha256(f"{prompt_row.content}:{context}".encode()).hexdigest()

    cached = await db.execute(
        select(AIBatchCommentary)
        .where(AIBatchCommentary.symbols == symbols_key, AIBatchCommentary.context_hash == context_hash)
        .order_by(AIBatchCommentary.created_at.desc())
        .limit(1)
    )
    row = cached.scalar_one_or_none()
    if row is not None:
        return {"content": row.content, "model": row.model_used, "cached": True, "symbols": sorted_symbols, "generated_at": row.created_at.isoformat()}

    client = anthropic.Anthropic(api_key=settings["api_key"])
    max_tokens = min(300 * len(blocks) + 400, 3000)

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=settings["model"],
            max_tokens=max_tokens,
            system=prompt_row.content,
            messages=[{"role": "user", "content": context}],
        )
    except anthropic.APIError as e:
        logger.error("ai_batch_commentary_failed", symbols=symbols_key, error=str(e))
        raise CommentaryError(f"Claude API error: {e}")

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise CommentaryError("Claude returned an empty response.")

    row = AIBatchCommentary(symbols=symbols_key, context_hash=context_hash, content=text, model_used=settings["model"])
    db.add(row)
    await db.commit()

    logger.info("ai_batch_commentary_generated", symbols=symbols_key, model=settings["model"])
    return {"content": text, "model": settings["model"], "cached": False, "symbols": sorted_symbols, "generated_at": datetime.now(timezone.utc).isoformat()}
