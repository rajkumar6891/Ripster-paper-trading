"""
One-shot fetch of historical intraday bars for the timeframe/exit study.

Yahoo caps intraday history at 60 days for 5m/30m bars (60m/1h can go back
2 years, but we use the same 60-day window across all three timeframes so
the comparison is apples-to-apples). 10-minute bars aren't a native Yahoo
interval, so they're built by aggregating pairs of 5-minute bars.

Run once (`python fetch_data.py`) to populate raw_bars.json; the rest of
the study reads from that cache instead of re-hitting Yahoo every time.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data_source  # noqa: E402

TOP_10 = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK.B", "JPM"]

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars.json")


def aggregate_bars(bars, factor):
    """Combine every `factor` consecutive bars into one OHLCV bar."""
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
    for ticker in TOP_10:
        print(f"Fetching {ticker}...")
        data[ticker] = {}
        for interval in ("5m", "30m", "60m"):
            bars = data_source.fetch_raw_bars(ticker, range_="60d", interval=interval)
            data[ticker][interval] = bars
            print(f"  {interval}: {len(bars)} bars")
            time.sleep(0.1)
        data[ticker]["10m"] = aggregate_bars(data[ticker]["5m"], 2)
        print(f"  10m (aggregated): {len(data[ticker]['10m'])} bars")

    with open(OUT_PATH, "w") as f:
        json.dump(data, f)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    fetch_all()
