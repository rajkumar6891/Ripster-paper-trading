"""
Parsing/normalization helpers for market data sourced from the Robinhood
MCP tools (get_equity_historicals, get_earnings_calendar).

Note on architecture: MCP tools can only be called by the Claude agent
itself, not by this plain Python script. So the *fetching* happens in the
cloud routine's own tool calls, which then dump the raw MCP JSON to
market_data.json / earnings.json in the repo checkout. This module only
parses/normalizes that already-fetched JSON -- see run.py for how the two
are wired together.
"""

import datetime

CLOSED_BAR_SECONDS = 3600  # a bar counts as closed once a full hour has
                            # elapsed since it opened (matches the spec's
                            # "a bar isn't finalized until a full hour has
                            # passed since it opened", and works uniformly
                            # regardless of the source's bar-alignment
                            # convention).


def parse_historicals(raw_results):
    """raw_results is the list under data.results from get_equity_historicals
    (one entry per symbol, each with a 'bars' list of begins_at/*_price
    strings). Returns {symbol: [{ts, open, high, low, close, volume}, ...]}
    sorted ascending by ts."""
    out = {}
    for entry in raw_results:
        symbol = entry.get("symbol")
        bars = []
        for b in entry.get("bars", []):
            if b.get("interpolated"):
                continue
            ts = int(datetime.datetime.fromisoformat(b["begins_at"].replace("Z", "+00:00")).timestamp())
            bars.append({
                "ts": ts,
                "open": float(b["open_price"]),
                "high": float(b["high_price"]),
                "low": float(b["low_price"]),
                "close": float(b["close_price"]),
                "volume": int(b["volume"]) if b.get("volume") is not None else None,
            })
        bars.sort(key=lambda x: x["ts"])
        out[symbol] = bars
    return out


def closed_hourly_bars(bars, now_ts=None):
    """Filter to bars whose full hour has elapsed as of now_ts (defaults to
    the current wall-clock time)."""
    if now_ts is None:
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    return [b for b in bars if now_ts >= b["ts"] + CLOSED_BAR_SECONDS]


def parse_earnings_map(raw_results):
    """raw_results is the list under data.results from get_earnings_calendar.
    Returns {symbol: 'YYYY-MM-DD'} using the earliest not-yet-reported
    (eps.actual is null) report date per symbol."""
    earliest = {}
    for entry in raw_results:
        eps = entry.get("eps") or {}
        if eps.get("actual") is not None:
            continue  # already reported, not "upcoming"
        symbol = entry.get("symbol")
        date_str = (entry.get("report") or {}).get("date")
        if not symbol or not date_str:
            continue
        if symbol not in earliest or date_str < earliest[symbol]:
            earliest[symbol] = date_str
    return earliest
