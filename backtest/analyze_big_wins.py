"""
Look at the biggest-winning trades from the "any-time filter" backtest (the
variant that matches the live monitor's actual entry logic: cloud bullish +
RVOL/RSI/ADX/cloud-sep filter passes, no freshness requirement) and check
for commonality in entry conditions -- RVOL, RSI, ADX, cloud separation,
time of day, day of week, hold duration, exit reason.

Data: raw_bars.json (10 tickers, 10-minute candles, ~60 trading days).
"""

import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy  # noqa: E402
import indicators  # noqa: E402
import sim_engine as engine  # noqa: E402

ET = ZoneInfo("America/New_York")
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars.json")
TIMEFRAME = "10m"
EXIT_RISK_MODE, EXIT_RISK_PCT, EXIT_TP_PCT = "stop", 0.03, 0.15


def load_data():
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def precompute(bars):
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)
    return {
        "rsi": indicators.compute_rsi(closes),
        "adx": indicators.compute_adx(bars),
        "rvol": indicators.compute_rvol(bars),
        "cloud_sep": indicators.compute_cloud_sep_pct(closes, clouds),
    }


def build_any_time_filter(pre):
    n = len(pre["rsi"])
    return [strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i]) for i in range(n)]


def minutes_since_open(ts):
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).astimezone(ET)
    return (dt.hour * 60 + dt.minute) - (9 * 60 + 30)


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    pre_by_ticker = {t: precompute(bars_by_ticker[t]) for t in bars_by_ticker}

    all_trades = []
    for t, bars in bars_by_ticker.items():
        pre = pre_by_ticker[t]
        ef = build_any_time_filter(pre)
        ts_to_idx = {b["ts"]: i for i, b in enumerate(bars)}
        trades = engine.simulate(bars, risk_exit=EXIT_RISK_MODE, risk_pct=EXIT_RISK_PCT,
                                  take_profit_pct=EXIT_TP_PCT, entry_filter=ef)
        for tr in trades:
            idx = ts_to_idx[tr["entry_ts"]]
            tr["ticker"] = t
            tr["rvol"] = pre["rvol"][idx]
            tr["rsi"] = pre["rsi"][idx]
            tr["adx"] = pre["adx"][idx]
            tr["cloud_sep"] = pre["cloud_sep"][idx]
            tr["minutes_since_open"] = minutes_since_open(tr["entry_ts"])
            tr["hold_minutes"] = (tr["exit_ts"] - tr["entry_ts"]) / 60
            dow = datetime.datetime.fromtimestamp(tr["entry_ts"], tz=datetime.timezone.utc).astimezone(ET)
            tr["day_of_week"] = dow.strftime("%A")
            tr["entry_time_et"] = dow.strftime("%Y-%m-%d %H:%M")
        all_trades.extend(trades)

    all_trades.sort(key=lambda t: t["pnl"], reverse=True)
    n = len(all_trades)
    big_wins = [t for t in all_trades if t["return_pct"] >= 0.03]  # +3% or better
    print(f"Total trades: {n}")
    print(f"Big wins (return >= +3%): {len(big_wins)}\n")

    print("=" * 130)
    print(f"{'ticker':6s} {'entry_time_et':17s} {'ret%':>6s} {'pnl':>9s} {'hold_min':>8s} {'exit':12s} "
          f"{'RVOL':>6s} {'RSI':>5s} {'ADX':>5s} {'sep%':>6s} {'min_since_open':>14s} {'dow':>9s}")
    print("=" * 130)
    for t in big_wins:
        print(f"{t['ticker']:6s} {t['entry_time_et']:17s} {t['return_pct']*100:6.2f} ${t['pnl']:8,.2f} "
              f"{t['hold_minutes']:8.0f} {t['reason']:12s} "
              f"{t['rvol']:6.2f} {t['rsi']:5.1f} {t['adx']:5.1f} {t['cloud_sep']*100:6.2f} "
              f"{t['minutes_since_open']:14d} {t['day_of_week']:>9s}")

    def avg(key, rows):
        vals = [r[key] for r in rows if r[key] is not None]
        return sum(vals) / len(vals) if vals else None

    print("\n" + "=" * 60)
    print("BIG WINS (>=+3%) vs ALL TRADES -- average entry conditions")
    print("=" * 60)
    for key, label in [("rvol", "RVOL"), ("rsi", "RSI"), ("adx", "ADX"),
                        ("cloud_sep", "cloud-sep"), ("minutes_since_open", "min since open"),
                        ("hold_minutes", "hold minutes")]:
        bw = avg(key, big_wins)
        allt = avg(key, all_trades)
        if key == "cloud_sep":
            print(f"{label:16s} big wins avg = {bw*100:6.2f}%   all trades avg = {allt*100:6.2f}%")
        else:
            print(f"{label:16s} big wins avg = {bw:7.2f}   all trades avg = {allt:7.2f}")

    from collections import Counter
    print("\nExit reason (big wins):", dict(Counter(t["reason"] for t in big_wins)))
    print("Exit reason (all trades):", dict(Counter(t["reason"] for t in all_trades)))
    print("\nDay of week (big wins):", dict(Counter(t["day_of_week"] for t in big_wins)))
    print("Ticker (big wins):", dict(Counter(t["ticker"] for t in big_wins)))

    # time-of-day buckets
    def bucket(m):
        if m is None:
            return "?"
        if m < 30:
            return "open (0-30m)"
        if m < 90:
            return "morning (30-90m)"
        if m < 180:
            return "midday (90-180m)"
        if m < 300:
            return "afternoon (180-300m)"
        return "late (300m+)"
    print("\nTime-of-day bucket (big wins):", dict(Counter(bucket(t["minutes_since_open"]) for t in big_wins)))
    print("Time-of-day bucket (all trades):", dict(Counter(bucket(t["minutes_since_open"]) for t in all_trades)))


if __name__ == "__main__":
    main()
