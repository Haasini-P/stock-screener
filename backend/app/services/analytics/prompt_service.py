"""
StockMind AI — System Prompt Suggestion
Builds a suggested AI system prompt from the live market regime snapshot, so
the prompt that steers AI commentary stays grounded in current conditions
instead of going stale.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.single_stock_analysis_prompt import SINGLE_STOCK_ANALYSIS_PROMPT

# The seed content for a brand-new SystemPrompt row (get_current_prompt, below) — not
# applied to an already-existing row. An existing row is only updated by the user
# through Settings -> AI Prompt (PUT /api/prompt), or by a one-off migration.
DEFAULT_PROMPT = SINGLE_STOCK_ANALYSIS_PROMPT


def _trend_phrase(change: float | None, noun: str) -> str | None:
    if change is None:
        return None
    if change > 0.3:
        return f"{noun} up {change:.2f}%"
    if change < -0.3:
        return f"{noun} down {abs(change):.2f}%"
    return f"{noun} flat ({change:+.2f}%)"


def build_suggested_prompt(regime: dict[str, Any]) -> dict[str, Any]:
    """
    Return {content, based_on} — a system prompt tailored to the current
    regime/mood/sector-rotation/FII-DII snapshot from /api/signals/regime.
    """
    regime_name = (regime.get("regime") or "neutral").replace("_", " ")
    mood = (regime.get("mood") or "neutral").replace("_", " ")
    indian = regime.get("indian_market", {})
    institutional = regime.get("institutional", {})
    sectors = regime.get("sectors", {})

    nifty_change = (indian.get("nifty_50") or {}).get("change")
    vix = (indian.get("india_vix") or {}).get("value")
    vix_change = (indian.get("india_vix") or {}).get("change")
    fii_trend = institutional.get("fii_trend") or "neutral"
    dii_trend = institutional.get("dii_trend") or "neutral"
    strong_sectors = sectors.get("strong") or []
    weak_sectors = sectors.get("weak") or []

    context_lines = [f"Current market regime: {regime_name} (mood: {mood})."]

    nifty_phrase = _trend_phrase(nifty_change, "Nifty 50")
    if nifty_phrase:
        context_lines.append(f"{nifty_phrase}.")
    if vix is not None:
        vix_desc = "elevated" if vix >= 18 else "low" if vix <= 12 else "moderate"
        context_lines.append(f"India VIX at {vix:.2f} ({vix_desc} volatility" + (f", {vix_change:+.2f}% today)." if vix_change is not None else ")."))

    flow_bits = []
    if fii_trend != "neutral":
        flow_bits.append(f"FIIs {fii_trend.replace('_', ' ')}")
    if dii_trend != "neutral":
        flow_bits.append(f"DIIs {dii_trend.replace('_', ' ')}")
    if flow_bits:
        context_lines.append(", ".join(flow_bits) + ".")

    if strong_sectors:
        context_lines.append(f"Leading sectors: {', '.join(strong_sectors)}.")
    if weak_sectors:
        context_lines.append(f"Lagging sectors: {', '.join(weak_sectors)}.")

    risk_alerts = regime.get("risk_alerts") or []
    guidance = []
    if regime_name in ("risk off", "extreme risk off"):
        guidance.append(
            "Market is risk-off — bias new ideas toward capital preservation, favor defensive sectors, "
            "demand tighter stop-losses, and flag that fresh long entries carry above-average risk right now."
        )
    elif regime_name in ("risk on", "mild risk on"):
        guidance.append(
            "Market is risk-on — momentum and breakout setups are more favorable, but still require a stated "
            "stop-loss and risk/reward before any entry idea."
        )
    else:
        guidance.append(
            "Market is in a neutral/transitional regime — prefer range-bound and mean-reversion setups over "
            "aggressive breakout chasing until the regime clarifies."
        )
    if vix is not None and vix >= 20:
        guidance.append("VIX is elevated — widen stop-loss buffers and reduce suggested position size versus the default risk-per-trade.")
    if risk_alerts:
        triggers = "; ".join(a.get("trigger", "") for a in risk_alerts if a.get("trigger"))
        if triggers:
            guidance.append(f"Active risk alerts to respect: {triggers}.")
    if strong_sectors:
        guidance.append(f"When screening for ideas, give {', '.join(strong_sectors)} extra weight given current sector leadership.")
    if weak_sectors:
        guidance.append(f"Treat new long ideas in {', '.join(weak_sectors)} with extra scrutiny given current sector weakness.")

    content = (
        "You are StockMind AI, an institutional-grade equity research assistant for NSE/BSE stocks.\n\n"
        "Ground every statement in the data provided — never fabricate CMP, RSI, MACD, volume, fundamentals, or "
        "news. Label each claim with its confidence: FACT (verified Upstox data), MODEL_PREDICTION (ML estimate "
        "with a stated range), ANALYST_INTERPRETATION (rule-based read of indicators), or DATA_NOT_VERIFIED "
        "(source unavailable).\n\n"
        "Current market context (refresh this prompt periodically — conditions change intraday):\n"
        + "\n".join(f"- {line}" for line in context_lines)
        + "\n\nGuidance for this regime:\n"
        + "\n".join(f"- {line}" for line in guidance)
        + "\n\nThis is a decision-support tool, not an autonomous trader. Always state direction as a probability, "
        "surface the strongest counter-argument to any thesis, name a thesis-invalidation level alongside any "
        "entry idea, and size positions against the user's stated capital and risk-per-trade. Be concise and "
        "quantitative — prefer numbers and named indicators over adjectives."
    )

    return {
        "content": content,
        "based_on": {
            "regime": regime.get("regime"),
            "mood": regime.get("mood"),
            "nifty_50_change": nifty_change,
            "india_vix": vix,
            "fii_trend": fii_trend,
            "dii_trend": dii_trend,
            "strong_sectors": strong_sectors,
            "weak_sectors": weak_sectors,
            "risk_alerts": [a.get("trigger") for a in risk_alerts if a.get("trigger")],
            "timestamp": regime.get("timestamp"),
        },
    }


async def get_current_prompt(db: AsyncSession):
    """The current SystemPrompt row, creating the default one if none exists yet."""
    from app.models.prompt import SystemPrompt  # local import avoids a module import cycle

    result = await db.execute(select(SystemPrompt).order_by(SystemPrompt.updated_at.desc()).limit(1))
    row = result.scalar_one_or_none()
    if row is None:
        row = SystemPrompt(content=DEFAULT_PROMPT, source="manual", updated_by="system")
        db.add(row)
        await db.flush()
    return row
