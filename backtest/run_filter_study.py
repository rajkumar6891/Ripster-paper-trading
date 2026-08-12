"""
Entry-filter study: layer RSI / ADX / RVOL / cloud-separation / time-of-day
filters on top of the cloud-crossover entry (10-minute candles, the
timeframe the earlier study found best), holding the exit fixed at the
best exit variant that study found (stop-3% + 15% take-profit), and see
which filter combination reduces trade count while maximizing total P&L
and per-trade quality.

Grid: rvol_min x rsi_mode x adx_min x cloud_sep_min x skip_open_minutes
    = 3 x 3 x 3 x 3 x 2 = 162 combinations, each run across all 10 tickers.
"""

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy  # noqa: E402
import indicators  # noqa: E402
import sim_engine as engine  # noqa: E402

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars.json")
TIMEFRAME = "10m"

# Fixed exit -- the winner from the timeframe/exit study for 10-minute candles.
EXIT_RISK_MODE, EXIT_RISK_PCT, EXIT_TP_PCT = "stop", 0.03, 0.15

RVOL_MIN_OPTS = [None, 1.5, 2.0]
RSI_MODE_OPTS = ["none", "above50", "50to70"]
ADX_MIN_OPTS = [None, 20, 25]
CLOUD_SEP_MIN_OPTS = [None, 0.003, 0.005]
SKIP_OPEN_MIN_OPTS = [0, 20]


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
        "minutes_since_open": indicators.compute_minutes_since_open(bars),
    }


def build_entry_filter(pre, rvol_min, rsi_mode, adx_min, cloud_sep_min, skip_open_minutes):
    n = len(pre["rsi"])
    out = [True] * n
    for i in range(n):
        ok = True
        if rvol_min is not None:
            v = pre["rvol"][i]
            ok = ok and v is not None and v >= rvol_min
        if rsi_mode == "above50":
            v = pre["rsi"][i]
            ok = ok and v is not None and v > 50
        elif rsi_mode == "50to70":
            v = pre["rsi"][i]
            ok = ok and v is not None and 50 < v < 70
        if adx_min is not None:
            v = pre["adx"][i]
            ok = ok and v is not None and v >= adx_min
        if cloud_sep_min is not None:
            v = pre["cloud_sep"][i]
            ok = ok and v is not None and v >= cloud_sep_min
        if skip_open_minutes:
            m = pre["minutes_since_open"][i]
            ok = ok and m is not None and m >= skip_open_minutes
        out[i] = ok
    return out


def label_for(rvol_min, rsi_mode, adx_min, cloud_sep_min, skip_open_minutes):
    parts = []
    parts.append(f"RVOL>={rvol_min}x" if rvol_min else "RVOL:off")
    parts.append({"none": "RSI:off", "above50": "RSI>50", "50to70": "RSI 50-70"}[rsi_mode])
    parts.append(f"ADX>={adx_min}" if adx_min else "ADX:off")
    parts.append(f"sep>={cloud_sep_min*100:.1f}%" if cloud_sep_min else "sep:off")
    parts.append(f"skip first {skip_open_minutes}m" if skip_open_minutes else "time:off")
    return " | ".join(parts)


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    pre_by_ticker = {t: precompute(bars_by_ticker[t]) for t in bars_by_ticker}

    combos = list(itertools.product(RVOL_MIN_OPTS, RSI_MODE_OPTS, ADX_MIN_OPTS, CLOUD_SEP_MIN_OPTS, SKIP_OPEN_MIN_OPTS))
    print(f"Testing {len(combos)} filter combinations on {TIMEFRAME} candles, "
          f"exit fixed at stop-{EXIT_RISK_PCT*100:.0f}% + {EXIT_TP_PCT*100:.0f}% TP...\n")

    results = []
    # unfiltered baseline for reference (same exit, no entry filter)
    baseline_trades = []
    for t, bars in bars_by_ticker.items():
        baseline_trades.extend(engine.simulate(bars, risk_exit=EXIT_RISK_MODE, risk_pct=EXIT_RISK_PCT,
                                                 take_profit_pct=EXIT_TP_PCT))
    baseline_summary = engine.summarize(baseline_trades)
    print(f"Unfiltered (exit-optimized only): trades={baseline_summary['trades']} "
          f"win_rate={baseline_summary['win_rate']*100:.1f}% total_pnl=${baseline_summary['total_pnl']:,.2f}\n")

    for combo in combos:
        rvol_min, rsi_mode, adx_min, cloud_sep_min, skip_open_minutes = combo
        all_trades = []
        for t, bars in bars_by_ticker.items():
            ef = build_entry_filter(pre_by_ticker[t], *combo)
            trades = engine.simulate(bars, risk_exit=EXIT_RISK_MODE, risk_pct=EXIT_RISK_PCT,
                                      take_profit_pct=EXIT_TP_PCT, entry_filter=ef)
            all_trades.extend(trades)
        summary = engine.summarize(all_trades)
        results.append({"label": label_for(*combo), "combo": combo, **summary})

    results_valid = [r for r in results if r["trades"] >= 15]  # drop combos with too few trades to be meaningful

    print("=" * 100)
    print("TOP 15 BY TOTAL P&L (min 15 trades)")
    print("=" * 100)
    for r in sorted(results_valid, key=lambda r: r["total_pnl"], reverse=True)[:15]:
        wr = f"{r['win_rate']*100:.1f}%" if r["win_rate"] is not None else "n/a"
        print(f"  trades={r['trades']:4d}  win_rate={wr:>6s}  total_pnl=${r['total_pnl']:>9,.2f}  "
              f"avg/trade=${r['avg_pnl']:>7,.2f}  pf={r['profit_factor']:.2f}  | {r['label']}")

    print("\n" + "=" * 100)
    print("TOP 15 BY AVG P&L PER TRADE (min 15 trades) -- 'quality over quantity'")
    print("=" * 100)
    for r in sorted(results_valid, key=lambda r: r["avg_pnl"], reverse=True)[:15]:
        wr = f"{r['win_rate']*100:.1f}%" if r["win_rate"] is not None else "n/a"
        print(f"  trades={r['trades']:4d}  win_rate={wr:>6s}  total_pnl=${r['total_pnl']:>9,.2f}  "
              f"avg/trade=${r['avg_pnl']:>7,.2f}  pf={r['profit_factor']:.2f}  | {r['label']}")

    print("\n" + "=" * 100)
    print(f"COMBOS THAT BEAT UNFILTERED TOTAL P&L (${baseline_summary['total_pnl']:,.2f}) WITH FEWER TRADES "
          f"THAN {baseline_summary['trades']}")
    print("=" * 100)
    better_and_fewer = [r for r in results_valid
                         if r["total_pnl"] > baseline_summary["total_pnl"] and r["trades"] < baseline_summary["trades"]]
    better_and_fewer.sort(key=lambda r: r["total_pnl"], reverse=True)
    if not better_and_fewer:
        print("  (none found)")
    for r in better_and_fewer:
        wr = f"{r['win_rate']*100:.1f}%" if r["win_rate"] is not None else "n/a"
        print(f"  trades={r['trades']:4d}  win_rate={wr:>6s}  total_pnl=${r['total_pnl']:>9,.2f}  "
              f"avg/trade=${r['avg_pnl']:>7,.2f}  pf={r['profit_factor']:.2f}  | {r['label']}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filter_study_results.json")
    with open(out_path, "w") as f:
        json.dump({"baseline": baseline_summary, "results": results}, f, indent=2)
    print(f"\nFull results ({len(results)} combos) written to {out_path}")


if __name__ == "__main__":
    main()
