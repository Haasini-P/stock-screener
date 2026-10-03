"""
StockMind AI — SEC EDGAR Fundamentals Compaction
Turns raw XBRL companyfacts JSON (hundreds of us-gaap concepts, each a messy
time series mixing annual/quarterly filings and restated comparatives) into
the same compact, "say what's missing, never fabricate" shape the Indian
fundamentals context already uses (see
app/services/ai/commentary_service.py's _compact_income_statement etc.) —
built for XBRL's {val, end, fy, form} shape instead of Upstox's
{category, history} shape, since the two data sources don't line up field-for-field.
"""

from datetime import date
from typing import Optional

# Different companies tag the same concept under different us-gaap names (a
# known XBRL quirk, not a bug) — try each in order, use the first with data.
_CONCEPT_TAGS: dict[str, list[str]] = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
    "net_income": ["NetIncomeLoss"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "eps_diluted": ["EarningsPerShareDiluted"],
}


def _is_annual_period(point: dict) -> bool:
    """A 10-K's XBRL facts aren't all annual — older Apple filings, for example,
    tag quarterly segment breakdowns under the same concept/form (confirmed live:
    AAPL's "Revenues" concept mixes full-year and single-quarter values, both
    form="10-K", sometimes sharing the same `end` date). "Instant" (point-in-time)
    concepts like Assets/Liabilities have no `start` and are fine as-is; "duration"
    concepts (revenue, net income, cash flow, EPS) must be checked for a
    ~350-380 day span, not just the form tag, to exclude quarterly values."""
    start = point.get("start")
    if not start:
        return True  # instant concept (balance-sheet item) — form=="10-K" alone is enough
    try:
        span_days = (date.fromisoformat(point["end"]) - date.fromisoformat(start)).days
    except ValueError:
        return False
    return 330 <= span_days <= 400


def _latest_annual_facts(company_facts: dict, tags: list[str], years: int = 4) -> Optional[list[dict]]:
    """Pools annual facts across ALL candidate tags rather than stopping at the
    first tag with any data — companies migrate tags over time (confirmed live:
    Apple and Microsoft both reported under "Revenues" in older 10-Ks, then
    switched to "RevenueFromContractWithCustomerExcludingAssessedTax" after
    adopting ASC 606 around 2018; using only the first tag with data would show
    years-stale figures for exactly these companies). Pooling and de-duping by
    period end date picks up each era's filings under whichever tag covers it."""
    gaap = (company_facts.get("facts") or {}).get("us-gaap") or {}
    by_end: dict[str, dict] = {}
    for tag in tags:
        concept = gaap.get(tag)
        if not concept:
            continue
        points = (concept.get("units") or {}).get("USD") or (concept.get("units") or {}).get("USD/shares") or []
        for p in points:
            if p.get("form") != "10-K" or not p.get("end") or not _is_annual_period(p):
                continue
            existing = by_end.get(p["end"])
            if existing is None or p.get("filed", "") >= existing.get("filed", ""):
                by_end[p["end"]] = p

    if not by_end:
        return None
    ordered = sorted(by_end.values(), key=lambda p: p["end"], reverse=True)[:years]
    return [{"value": p["val"], "period": p["end"]} for p in ordered]


def compact_fundamentals(company_facts: dict) -> dict:
    """Returns {revenue, net_income, total_assets, total_liabilities,
    operating_cash_flow, eps_diluted: [{value, period}, ...] | None, unavailable: [...]}."""
    result: dict = {"entity_name": company_facts.get("entityName")}
    unavailable = []
    for concept, tags in _CONCEPT_TAGS.items():
        facts = _latest_annual_facts(company_facts, tags)
        result[concept] = facts
        if facts is None:
            unavailable.append(concept)
    result["unavailable"] = unavailable
    return result


def fundamentals_to_context_text(compact: dict) -> str:
    """Compact text for the AI context, same join style as the Indian
    _compact_income_statement/_compact_balance_sheet helpers."""
    lines = []
    for label, key in (
        ("Revenue", "revenue"), ("Net income", "net_income"),
        ("Total assets", "total_assets"), ("Total liabilities", "total_liabilities"),
        ("Operating cash flow", "operating_cash_flow"), ("EPS (diluted)", "eps_diluted"),
    ):
        points = compact.get(key)
        if not points:
            continue
        joined = ", ".join(f"{p['value']:,.0f} ({p['period']})" if key != "eps_diluted" else f"{p['value']} ({p['period']})" for p in points)
        lines.append(f"{label}: {joined}")
    if compact.get("unavailable"):
        lines.append(f"Not in SEC filings for this company: {', '.join(compact['unavailable'])}")
    return "\n".join(lines)
