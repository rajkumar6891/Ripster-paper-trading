"""
Wider fetch for validating the chandelier-exit multiplier: same 60-day Yahoo
5m-bar window as fetch_data.py (Yahoo's hard cap for intraday 5m data, so
history can't be lengthened -- only breadth), but ~40 tickers spanning
sectors instead of just the original 10 mega-cap/tech names, to check
whether the chandelier sweet-spot multiplier found on TOP_10 holds up out
of a narrower sample or was overfit to it.

Only fetches 5m (aggregated to 10m) -- these studies don't need 30m/60m.
Writes to raw_bars_wide.json, separate from raw_bars.json so the original
timeframe/exit studies that read raw_bars.json are untouched.

Run once (`python fetch_data_wide.py`) to populate the cache.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data_source  # noqa: E402

# Original 10 (kept for direct before/after comparison) plus ~30 more
# spanning sectors not represented in the mega-cap-tech-heavy original set.
WIDE_SET = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK.B", "JPM",
    "LLY", "UNH", "JNJ", "ABBV", "MRK",           # healthcare
    "V", "MA", "GS", "MS", "BAC",                 # financials
    "HD", "MCD", "COST", "WMT", "PG",             # consumer
    "CAT", "RTX", "HON", "BA", "GE",              # industrials
    "XOM", "CVX", "COP",                          # energy
    "AMD", "QCOM", "MU", "ADI",                   # semis (non-mega)
    "CRM", "NOW", "ADBE", "PANW",                 # software
]

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars_wide.json")


def aggregate_bars(bars, factor):
    out = []
    for i in range(0, len(bars) - factor + 1, factor):
        chunk = bars[i:i + factor]
        out.append({
            "ts": chunk[0]["ts"],
            "open": chunk[0]["open"],
            "high": max(b["high"] for b in chunk),
            "low": min(b["low"] for b in chunk),
            "close": chunk[-1]["close"],
            "volume": sum((b["volume"] or 0) for b in chunk),
        })
    return out


def fetch_all():
    data = {}
    failed = []
    for ticker in WIDE_SET:
        print(f"Fetching {ticker}...")
        try:
            bars5m = data_source.fetch_raw_bars(ticker, range_="60d", interval="5m")
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append(ticker)
            continue
        data[ticker] = {"5m": bars5m, "10m": aggregate_bars(bars5m, 2)}
        print(f"  5m: {len(bars5m)} bars  10m: {len(data[ticker]['10m'])} bars")
        time.sleep(0.15)

    with open(OUT_PATH, "w") as f:
        json.dump(data, f)
    print(f"\nWrote {OUT_PATH} ({len(data)} tickers, {len(failed)} failed: {failed})")


if __name__ == "__main__":
    fetch_all()
