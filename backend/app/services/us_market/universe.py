"""
StockMind AI — Approved US Stock Universe
Static ticker list (NASDAQ/NYSE), sector-keyed like SECTOR_UNIVERSE in
app/services/analytics/screener.py. Unlike that list, these symbols are NOT
verified against any live instrument search — Upstox has no US equity
resolver — so this is just a plain, hand-picked list. Keep it small; expand
once a real US market-data provider is wired in (see provider.py).
"""

US_STOCK_UNIVERSE: dict[str, list[str]] = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "META", "AMZN"],
    "Semiconductors": ["NVDA", "AVGO", "AMD", "INTC"],
    "EV / Auto": ["TSLA", "F", "GM"],
    "Finance": ["JPM", "BAC", "V", "MA"],
    "Healthcare": ["UNH", "JNJ", "LLY", "PFE"],
    "Consumer": ["WMT", "COST", "KO", "PG"],
}


def us_symbol_sector_lookup() -> dict[str, str]:
    """Flattens US_STOCK_UNIVERSE to {symbol: sector} — mirrors screener.py's
    equivalent helper for the Indian universe."""
    return {symbol: sector for sector, symbols in US_STOCK_UNIVERSE.items() for symbol in symbols}
