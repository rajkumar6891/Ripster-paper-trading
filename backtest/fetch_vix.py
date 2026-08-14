"""
Fetch VIX (^VIX) intraday bars over the same 60-day Yahoo 5m window as
raw_bars_wide.json, aggregated to 10-minute candles on the same grid, so
they can be joined to the equity bars by timestamp for correlation/filter
studies. VIX has no traded volume (it's a computed index, not a security)
so volume is left as whatever Yahoo returns (typically 0/None).

Run once (`python fetch_vix.py`) to populate vix_bars.json.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data_source  # noqa: E402

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vix_bars.json")


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


def main():
    bars5m = data_source.fetch_raw_bars("^VIX", range_="60d", interval="5m")
    bars10m = aggregate_bars(bars5m, 2)
    print(f"5m: {len(bars5m)} bars  10m: {len(bars10m)} bars")
    with open(OUT_PATH, "w") as f:
        json.dump({"5m": bars5m, "10m": bars10m}, f)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
