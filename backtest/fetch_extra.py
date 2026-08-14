"""
Extra fetch for the regime/VIX-sector research: real REIT tickers, pure-play
defense tickers (neither present in raw_bars_wide.json), SPY (macro regime),
and sector ETFs (sector regime). Same 60-day Yahoo 5m window as
fetch_data_wide.py.

Writes to raw_bars_extra.json (equities: REITs+defense, same schema as
raw_bars_wide.json) and sector_etfs.json (SPY + sector ETFs).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data_source  # noqa: E402

REIT_SET = ["PLD", "AMT", "EQIX", "O", "SPG", "PSA", "WELL", "DLR", "VTR"]
DEFENSE_SET = ["LMT", "NOC", "GD", "LHX", "TDY"]
SECTOR_ETFS = ["SPY", "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLRE"]

EXTRA_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars_extra.json")
ETF_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sector_etfs.json")


def aggregate_bars(bars, factor):
    out = []
    for i in range(0, len(bars) - factor + 1, factor):
        chunk = bars[i:i + factor]
        out.append({
            "ts": chunk[0]["ts"], "open": chunk[0]["open"],
            "high": max(b["high"] for b in chunk), "low": min(b["low"] for b in chunk),
            "close": chunk[-1]["close"], "volume": sum((b["volume"] or 0) for b in chunk),
        })
    return out


def fetch_set(tickers):
    data = {}
    failed = []
    for ticker in tickers:
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
    return data, failed


def main():
    equities, eq_failed = fetch_set(REIT_SET + DEFENSE_SET)
    with open(EXTRA_OUT, "w") as f:
        json.dump({"reits": REIT_SET, "defense": DEFENSE_SET, "data": equities}, f)
    print(f"Wrote {EXTRA_OUT} ({len(equities)} tickers, failed: {eq_failed})")

    etfs, etf_failed = fetch_set(SECTOR_ETFS)
    with open(ETF_OUT, "w") as f:
        json.dump(etfs, f)
    print(f"Wrote {ETF_OUT} ({len(etfs)} tickers, failed: {etf_failed})")


if __name__ == "__main__":
    main()
