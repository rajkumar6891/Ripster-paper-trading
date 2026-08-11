"""
Ticker universe for the Ripster EMA Cloud paper-trading monitor.

This is a best-effort, hand-curated static snapshot (compiled by an LLM,
not pulled from a live ranked index feed) of:
  - roughly the 100 largest S&P 500 constituents by market cap
  - roughly the 100 largest US-listed technology-sector names by market cap
merged with the original 5-ticker seed watchlist from the spec.

It is illustrative only -- rankings drift over time and this list is not
re-derived automatically. Feel free to edit the lists below directly to
add/remove names; ORIGINAL_WATCHLIST is always kept in the merged universe.
"""

# The original watchlist from the spec -- always included.
ORIGINAL_WATCHLIST = ["DELL", "LLY", "AMAT", "ORCL", "MU"]

# Best-effort top ~100 S&P 500 names by market cap, spanning sectors.
TOP_100_SP500 = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "BRK.B",
    "LLY", "JPM", "V", "MA", "XOM", "UNH", "COST", "PG", "JNJ", "HD",
    "ORCL", "BAC", "MRK", "ABBV", "CVX", "CRM", "KO", "PEP", "WMT", "TMO",
    "ADBE", "MCD", "CSCO", "ACN", "ABT", "LIN", "DHR", "WFC", "AMD", "TXN",
    "NFLX", "PM", "GE", "CAT", "INTU", "IBM", "ISRG", "VZ", "T", "DIS",
    "GS", "MS", "AXP", "NOW", "AMAT", "SPGI", "CB",
    "PFE", "AMGN", "UNP", "RTX", "HON", "LOW", "BLK", "BKNG", "ETN", "SYK",
    "VRTX", "BSX", "MDT", "GILD", "ELV", "REGN", "ADI", "LRCX", "KLAC", "MU",
    "PANW", "CI", "ZTS", "TJX", "SBUX", "MDLZ", "CMG", "PGR", "ICE",
    "CME", "USB", "PNC", "SCHW", "C", "DE", "BA", "LMT", "GD", "UPS",
    "TMUS", "CMCSA", "SLB", "COP", "EOG",
]

# Best-effort top ~100 largest US-listed technology names by market cap
# (semis, software, internet/platform, hardware, IT services). Overlaps
# with TOP_100_SP500 are expected and fine -- deduped at merge time.
TOP_100_TECH = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "ORCL",
    "CRM", "ADBE", "CSCO", "ACN", "AMD", "TXN", "INTU", "IBM", "NOW", "QCOM",
    "AMAT", "MU", "ADI", "LRCX", "KLAC", "PANW", "SNPS", "CDNS", "ADSK",
    "WDAY", "TEAM", "PAYX", "ADP", "FIS", "FISV", "GPN", "VRSN", "AKAM", "CTSH",
    "EPAM", "PTC", "TER", "ENTG", "MPWR", "MCHP", "NXPI", "SWKS", "QRVO", "ON",
    "MRVL", "ANET", "FTNT", "CRWD", "ZS", "NET", "DDOG", "MDB", "SNOW", "PLTR",
    "SHOP", "UBER", "ABNB", "DASH", "SPOT", "PYPL", "XYZ", "COIN", "RBLX", "U",
    "TTD", "PINS", "SNAP", "ETSY", "EBAY", "BKNG", "EXPE", "ZM", "DOCU", "OKTA",
    "HPQ", "HPE", "DELL", "NTAP", "STX", "WDC", "JBL", "GLW", "FFIV",
    "KEYS", "TDY", "TRMB", "ZBRA", "GRMN", "LOGI", "DXC", "GEN", "TSM", "ASML",
]

def build_universe():
    """Return the deduped, order-preserving merged ticker universe."""
    merged = []
    seen = set()
    for group in (ORIGINAL_WATCHLIST, TOP_100_SP500, TOP_100_TECH):
        for t in group:
            if t not in seen:
                seen.add(t)
                merged.append(t)
    return merged


UNIVERSE = build_universe()


if __name__ == "__main__":
    print(f"SP500 list size (raw): {len(TOP_100_SP500)}")
    print(f"Tech list size (raw): {len(TOP_100_TECH)}")
    print(f"Merged universe size: {len(UNIVERSE)}")
    print(UNIVERSE)
