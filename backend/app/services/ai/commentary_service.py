"""
StockMind AI — AI-Powered Stock Commentary (Claude or Gemini)
Generates on-demand AI commentary for a stock using the stored system prompt
(app/services/analytics/prompt_service.py) and the same analysis data already
shown on the Stock Report. This is the first thing that actually reads the
system prompt — previously it was edited but never used anywhere.

Supports multiple providers — Anthropic (Claude) and Google (Gemini) — each
with its own stored API key (app/services/ai/ai_config.py); which one is used
is resolved from the currently active model. _call_model dispatches to
whichever provider that model belongs to.

Always on-demand, never automatic: commentary can be requested from the
Scanner, Daily Signals, and Stock Report, all of which can list many stocks
at once, so every call is cached per (symbol, context_hash, day) to avoid
re-billing the API for an unchanged signal.
"""

import asyncio
import base64
import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

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
    # Current as of Oct 2026 per ai.google.dev/gemini-api/docs/pricing — a promotional
    # rate through Dec 31 2026, rising to $1.50/$7.50 after. Also has a separate,
    # rate-limited FREE tier via a Google AI Studio key (ai.google.dev), which is the
    # usual reason to pick it over a paid-only Claude model.
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
}

MAX_BATCH_SYMBOLS = 8


class CommentaryError(Exception):
    """Raised when commentary can't be generated (not configured, or the API call failed)."""


def _call_anthropic(api_key: str, model: str, system_prompt: str, text: str, image_png: Optional[bytes], max_tokens: int) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    user_content: list[dict] = []
    if image_png:
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(image_png).decode()},
        })
    user_content.append({"type": "text", "text": text})

    try:
        response = client.messages.create(
            model=model, max_tokens=max_tokens, system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIError as e:
        raise CommentaryError(f"Claude API error: {e}")

    result = "".join(block.text for block in response.content if block.type == "text").strip()
    if not result:
        raise CommentaryError("Claude returned an empty response.")
    return result


def _call_gemini(api_key: str, model: str, system_prompt: str, text: str, image_png: Optional[bytes], max_tokens: int) -> str:
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    contents: list = []
    if image_png:
        contents.append(genai_types.Part.from_bytes(data=image_png, mime_type="image/png"))
    contents.append(text)

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=genai_types.GenerateContentConfig(system_instruction=system_prompt, max_output_tokens=max_tokens),
        )
    except genai_errors.APIError as e:
        raise CommentaryError(f"Gemini API error: {e.message}")

    result = (response.text or "").strip()
    if not result:
        raise CommentaryError("Gemini returned an empty response.")
    return result


async def _call_model(
    provider: str, model: str, api_key: str, system_prompt: str, text: str,
    image_png: Optional[bytes], max_tokens: int,
) -> str:
    """Dispatches to whichever provider's SDK the active model needs. Both SDKs
    are synchronous, so both run via asyncio.to_thread rather than blocking the event loop."""
    fn = _call_anthropic if provider == "anthropic" else _call_gemini
    return await asyncio.to_thread(fn, api_key, model, system_prompt, text, image_png, max_tokens)


def _round(v: Any, nd: int = 2) -> Any:
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def _compact_quote(quote: Optional[dict]) -> str:
    """Upstox's raw quote payload also carries market-depth (bid/ask ladder), instrument
    IDs and OI fields a research report never uses — pull just the levels that matter
    instead of dumping the whole object as JSON."""
    row = next(iter((quote or {}).values()), {}) if quote else {}
    if not row:
        return ""
    ohlc = row.get("ohlc") or {}
    return (
        f"LTP {_round(row.get('last_price'))} (chg {_round(row.get('net_change'))}), "
        f"O/H/L {_round(ohlc.get('open'))}/{_round(ohlc.get('high'))}/{_round(ohlc.get('low'))}, "
        f"volume {row.get('volume')}"
    )


def _compact_indicators(snapshot: Optional[dict]) -> str:
    """The feature snapshot has ~70 fields at full float precision (e.g. 15+ significant
    figures) — most already stated elsewhere in this context (RSI/ADX/volume ratio/trend
    are in the Technicals line). This surfaces only what isn't, rounded to a sane
    precision, as compact text instead of a raw (and previously truncated mid-structure,
    i.e. invalid) JSON dump."""
    if not snapshot:
        return ""
    dist_200 = snapshot.get("dist_sma_200")
    dist_high = snapshot.get("dist_52w_high")
    parts = [
        f"Bollinger {_round(snapshot.get('bollinger_lower'))}-{_round(snapshot.get('bollinger_upper'))} (%B {_round(snapshot.get('bollinger_pct_b'))})",
        f"Stochastic K{_round(snapshot.get('stochastic_k'), 1)}/D{_round(snapshot.get('stochastic_d'), 1)}",
        f"ATR(14) {_round(snapshot.get('atr_14'))}",
        f"support/resistance {_round(snapshot.get('support_1'))}/{_round(snapshot.get('resistance_1'))}",
        f"52w range {_round(snapshot.get('low_52w'))}-{_round(snapshot.get('high_52w'))}"
        + (f" ({_round(dist_high * 100, 1)}% from high)" if dist_high is not None else ""),
        f"VWAP {_round(snapshot.get('vwap'))}",
        f"volume z-score {_round(snapshot.get('volume_zscore'))}",
    ]
    if dist_200 is not None:
        parts.append(f"{_round(dist_200 * 100, 1)}% {'above' if dist_200 >= 0 else 'below'} 200-day MA")
    return ", ".join(parts)


def _macd_text(snapshot: Optional[dict]) -> str:
    """tech.get('macd') (StockSignal.macd_signal_status) is never populated by the
    signal engine — always empty — so pull the real value from the feature snapshot
    instead of silently rendering 'MACD ,' with nothing after it."""
    if not snapshot:
        return "n/a"
    hist = snapshot.get("macd_histogram")
    macd, sig = snapshot.get("macd"), snapshot.get("macd_signal")
    if macd is None or sig is None:
        return "n/a"
    bias = "bullish" if (hist or 0) > 0 else "bearish" if (hist or 0) < 0 else "flat"
    return f"{_round(macd, 2)} vs signal {_round(sig, 2)} ({bias})"


def _compact_profile(profile: Optional[dict], limit: int = 320) -> str:
    if not profile:
        return ""
    text = (profile.get("company_profile") or "").strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    sector = profile.get("sector")
    return f"{text} (Sector: {sector})" if sector else text


def _compact_key_ratios(key_ratios: Optional[list]) -> str:
    if not key_ratios:
        return ""
    parts = []
    for r in key_ratios:
        name, cv, sv = r.get("name"), r.get("company_value"), r.get("sector_value")
        if name is None or cv is None:
            continue
        parts.append(f"{name} {cv}" + (f" (sector {sv})" if sv is not None else ""))
    return ", ".join(parts)


def _compact_shareholding(shareholding: Optional[list]) -> str:
    """Each category carries a multi-quarter history — a research report only needs
    the latest print, not the trend table, so this keeps history[0] per category."""
    if not shareholding:
        return ""
    parts = []
    for cat in shareholding:
        latest = (cat.get("history") or [{}])[0]
        if latest.get("value") is None:
            continue
        parts.append(f"{cat.get('category')} {latest['value']}% ({latest.get('period', '')})")
    return ", ".join(parts)


def _compact_corporate_actions(actions: Optional[list], limit: int = 5) -> str:
    if not actions:
        return ""
    parts = []
    for a in actions[:limit]:
        bits = [a.get("name") or "Action"]
        if a.get("amount") is not None:
            bits.append(f"amount {a['amount']}")
        if a.get("ratio"):
            bits.append(f"ratio {a['ratio']}")
        if a.get("expiry_date"):
            bits.append(f"ex-date {a['expiry_date']}")
        parts.append(" ".join(bits))
    return "; ".join(parts)


def _compact_competitors(competitors: Optional[list], limit: int = 5, name_chars: int = 90) -> str:
    """Competitor rows carry no name field — only a company_profile paragraph that
    starts with the name — so truncate hard rather than dumping full paragraphs
    per peer (confirmed live: 8 peers x full profiles was most of the fundamentals cost)."""
    if not competitors:
        return ""
    parts = []
    for c in competitors[:limit]:
        text = (c.get("company_profile") or "").strip()
        if len(text) > name_chars:
            text = text[:name_chars].rsplit(" ", 1)[0] + "…"
        parts.append(text)
    return "; ".join(parts)


def _humanize(s: Optional[str]) -> str:
    return s.replace("_", " ").title() if s else ""


def _compact_income_statement(income_statement: Optional[dict], years: int = 3) -> str:
    """income_statement['income_statement'] is a list of {category, history: [{value,
    period, change}, ...]} rows (revenue / operating_profit / net_profit) — this app's
    system prompt asks for real Growth/Profitability figures (section 5) that were
    previously never surfaced at all, leaving the model with nothing to analyze there."""
    rows = (income_statement or {}).get("income_statement")
    if not rows:
        return ""
    units = (income_statement or {}).get("units_in", "")
    parts = []
    for row in rows:
        history = (row.get("history") or [])[:years]
        if not history:
            continue
        points = ", ".join(
            f"{_round(h.get('value'), 0)} ({h.get('period')}" + (f", {h['change']} YoY)" if h.get("change") else ")")
            for h in history
        )
        parts.append(f"{_humanize(row.get('category'))}: {points}")
    if not parts:
        return ""
    return f"({units}) " + "; ".join(parts) if units else "; ".join(parts)


def _compact_balance_sheet(balance_sheet: Optional[dict], years: int = 3) -> str:
    history = (balance_sheet or {}).get("history")
    if not history:
        return ""
    units = (balance_sheet or {}).get("units_in", "")
    parts = [
        f"assets {_round(h.get('total_asset'), 0)} / liabilities {_round(h.get('total_liability'), 0)} ({h.get('period')})"
        for h in history[:years] if h.get("total_asset") is not None
    ]
    if not parts:
        return ""
    return (f"({units}) " if units else "") + "; ".join(parts)


def _compact_cash_flow(cash_flow: Optional[dict], years: int = 2) -> str:
    rows = (cash_flow or {}).get("cash_flow")
    if not rows:
        return ""
    units = (cash_flow or {}).get("units_in", "")
    parts = []
    for row in rows:
        history = (row.get("history") or [])[:years]
        if not history:
            continue
        points = ", ".join(f"{_round(h.get('value'), 0)} ({h.get('period')})" for h in history)
        parts.append(f"{_humanize(row.get('category'))}: {points}")
    if not parts:
        return ""
    return (f"({units}) " if units else "") + "; ".join(parts)


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

    # Every horizon's prediction carries the same snapshot, so any one horizon will do.
    snapshot = next((p.get("feature_snapshot") for p in predictions.values() if p.get("feature_snapshot")), None)

    lines = [
        f"Symbol: {analysis.get('symbol')} ({analysis.get('name', '')})",
        f"Regime: {analysis.get('metadata', {}).get('regime', 'unknown')}",
        f"Signal: {(s.get('signal') or {}).get('entry', 'unknown')} / {(s.get('signal') or {}).get('type', '')}",
        f"Technicals: RSI {tech.get('rsi')}, ADX {tech.get('adx')}, MACD {_macd_text(snapshot)}, "
        f"volume ratio {tech.get('volume_ratio')}, trend {tech.get('trend')}",
        f"Entry zone: {ee.get('entry_zone')} | Stop-loss: {ee.get('stop_loss')} | "
        f"Target 1/2: {ee.get('target_1')}/{ee.get('target_2')} | R:R {ee.get('risk_reward')}",
        f"Suggested position: {pos.get('quantity')} shares, value {pos.get('value')}, risk {pos.get('max_risk')}",
    ]
    holding = s.get("holding") or {}
    if holding.get("is_holding"):
        lines.append(f"EXISTING HOLDING (from the user's live broker account) — engine says: {holding.get('action')}")
    # pe/roe/revenue_growth are never populated on this code path (generate_signal()
    # is called without a fundamentals arg) — only emit this line when there's a
    # real summary, instead of three "None"s that waste tokens and look like data.
    if fundamental_signal.get("summary"):
        pe, roe, rev = fundamental_signal.get("pe"), fundamental_signal.get("roe"), fundamental_signal.get("revenue_growth")
        stats = ", ".join(f"{k} {v}" for k, v in (("P/E", pe), ("ROE", roe), ("rev growth", rev)) if v is not None)
        lines.append(f"Quick fundamentals (rule engine): {stats + ' — ' if stats else ''}{fundamental_signal['summary']}")
    quote_text = _compact_quote(q)
    if quote_text:
        lines.append(f"Quote data: {quote_text}")

    # Other computed indicators not already covered above (Bollinger, Stochastic,
    # ATR, support/resistance, 52-week range, VWAP, volume z-score, 200-day MA).
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
        profile_text = _compact_profile(fundamentals.get("profile"))
        if profile_text:
            lines.append(f"Profile: {profile_text}")
        ratios_text = _compact_key_ratios(fundamentals.get("key_ratios"))
        if ratios_text:
            lines.append(f"Key ratios: {ratios_text}")
        income_text = _compact_income_statement(fundamentals.get("income_statement"))
        if income_text:
            lines.append(f"Income statement (yearly): {income_text}")
        balance_text = _compact_balance_sheet(fundamentals.get("balance_sheet"))
        if balance_text:
            lines.append(f"Balance sheet (yearly): {balance_text}")
        cash_flow_text = _compact_cash_flow(fundamentals.get("cash_flow"))
        if cash_flow_text:
            lines.append(f"Cash flow (yearly): {cash_flow_text}")
        shareholding_text = _compact_shareholding(fundamentals.get("shareholding"))
        if shareholding_text:
            lines.append(f"Shareholding (latest): {shareholding_text}")
        actions_text = _compact_corporate_actions(fundamentals.get("corporate_actions"))
        if actions_text:
            lines.append(f"Corporate actions: {actions_text}")
        competitors_text = _compact_competitors(fundamentals.get("competitors"))
        if competitors_text:
            lines.append(f"Peers/competitors: {competitors_text}")
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
        "data wasn't provided above, say so explicitly (per your FACT/MODEL_PREDICTION/ANALYST_INTERPRETATION/"
        "DATA_NOT_VERIFIED rules) rather than "
        "inventing numbers — do not skip a section silently, just mark it not verifiable from available data. "
        "Be concise: the app already shows the numeric tables above (predictions, entry/stop/targets, indicators) "
        "to the reader next to your commentary, so don't restate them in full — reference them briefly and spend "
        "your words on interpretation. Explicitly call out, in a short line each, whether this stock looks "
        "favorable for SHORT-TERM (days, ~5D horizon), MEDIUM-TERM (weeks, ~20D horizon) and LONG-TERM "
        "(structural, 200-day trend) holding — the app renders these as a table, so state each verdict plainly."
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
            f"{settings['provider'].title()} API key not configured. Add it in Settings → AI Commentary."
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

    try:
        text = await _call_model(
            settings["provider"], settings["model"], settings["api_key"],
            prompt_row.content, context, chart_png,
            # The institutional-grade research prompt asks for 25 structured sections
            # plus a final decision table — a stricter cap here risks silently truncating
            # the report mid-section rather than running short, which is worse.
            max_tokens=8192,
        )
    except CommentaryError as e:
        logger.error("ai_commentary_failed", symbol=symbol, provider=settings["provider"], error=str(e))
        raise

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
    holding = s.get("holding") or {}
    if holding.get("is_holding"):
        lines.append(f"EXISTING HOLDING (from the user's live broker account) — engine says: {holding.get('action')}")
    top_positive = (evidence.get("positive") or [{}])[0].get("factor")
    top_negative = (evidence.get("negative") or [{}])[0].get("factor")
    if top_positive:
        lines.append(f"Top positive: {top_positive}")
    if top_negative:
        lines.append(f"Top risk: {top_negative}")
    return "\n".join(lines)


async def generate_batch_commentary(db: AsyncSession, user: Optional[User], symbols: list[str]) -> dict:
    """
    One cheaper, shallower call (whichever provider is active) covering several stocks at once — a
    condensed verdict per stock rather than the full 16-section report.
    """
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    if not symbols:
        raise CommentaryError("No symbols given.")
    if len(symbols) > MAX_BATCH_SYMBOLS:
        raise CommentaryError(f"Batch analysis is capped at {MAX_BATCH_SYMBOLS} stocks at a time (got {len(symbols)}).")

    settings = await get_settings(db)
    if not settings["configured"]:
        raise CommentaryError(f"{settings['provider'].title()} API key not configured. Add it in Settings → AI Commentary.")

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
        "give a condensed verdict in this exact shape — do not use the full multi-section report format "
        "from your system prompt for this request:\n\n"
        "**SYMBOL** — FINAL ACTION (one of: BUY NOW — SMALL STARTER / BUY ON DIP / ACCUMULATE / WAIT FOR "
        "BREAKOUT CONFIRMATION / WATCH / AVOID) — one-line reason citing the specific numbers given, labeled "
        "FACT/MODEL_PREDICTION/ANALYST_INTERPRETATION/DATA_NOT_VERIFIED per your system prompt's rules. "
        "Stocks marked EXISTING HOLDING below are "
        "already in my live portfolio — for those, say ADD / HOLD / REDUCE instead of a fresh-buy verdict. "
        "Don't assume any other stock is held.\n\n"
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

    max_tokens = min(300 * len(blocks) + 400, 3000)

    try:
        text = await _call_model(
            settings["provider"], settings["model"], settings["api_key"],
            prompt_row.content, context, None, max_tokens,
        )
    except CommentaryError as e:
        logger.error("ai_batch_commentary_failed", symbols=symbols_key, provider=settings["provider"], error=str(e))
        raise

    row = AIBatchCommentary(symbols=symbols_key, context_hash=context_hash, content=text, model_used=settings["model"])
    db.add(row)
    await db.commit()

    logger.info("ai_batch_commentary_generated", symbols=symbols_key, model=settings["model"])
    return {"content": text, "model": settings["model"], "cached": False, "symbols": sorted_symbols, "generated_at": datetime.now(timezone.utc).isoformat()}
