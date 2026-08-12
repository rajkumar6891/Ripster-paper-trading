"""
Runs the full timeframe x exit-variant study over the cached bar data
(raw_bars.json, produced by fetch_data.py) and prints/saves results.

Two questions being answered:
  1. Which candle timeframe (10m / 30m / 1h) performs better, using the
     exact exit rule the live monitor uses (cloud-exit OR 5% stop)?
  2. For each timeframe, which exit variant (stop tightness, trailing
     stop, added take-profit) produces the best total P&L?

Caveat: this backtest does NOT apply the earnings blackout the live
monitor uses (no free historical earnings-date source was readily
available), so entry counts here will run slightly higher than the live
monitor would in practice around earnings. Everything else (entry rule,
cloud-exit rule, position sizing, one-at-a-time) matches exactly.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sim_engine as engine  # noqa: E402

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars.json")
TIMEFRAMES = ["10m", "30m", "60m"]
TIMEFRAME_LABELS = {"10m": "10-minute", "30m": "30-minute", "60m": "1-hour"}

RISK_VARIANTS = [
    ("cloud-only", None, None),
    ("stop-3%", "stop", 0.03),
    ("stop-5% (baseline)", "stop", 0.05),
    ("stop-8%", "stop", 0.08),
    ("trailing-5%", "trailing", 0.05),
    ("trailing-8%", "trailing", 0.08),
]
TAKE_PROFIT_VARIANTS = [(None, "no TP"), (0.10, "+10% TP"), (0.15, "+15% TP")]


def load_data():
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def run_variant(data, timeframe, risk_exit, risk_pct, take_profit_pct):
    all_trades = []
    per_ticker = {}
    for ticker, by_tf in data.items():
        bars = by_tf[timeframe]
        trades = engine.simulate(bars, risk_exit=risk_exit, risk_pct=risk_pct, take_profit_pct=take_profit_pct)
        all_trades.extend(trades)
        per_ticker[ticker] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker


def main():
    data = load_data()

    print("=" * 78)
    print("PART 1: TIMEFRAME COMPARISON (baseline exit: cloud-cross OR 5% stop)")
    print("=" * 78)
    timeframe_results = {}
    for tf in TIMEFRAMES:
        summary, per_ticker = run_variant(data, tf, "stop", 0.05, None)
        timeframe_results[tf] = (summary, per_ticker)
        wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
        pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
        print(f"\n{TIMEFRAME_LABELS[tf]:12s} trades={summary['trades']:4d}  win_rate={wr:>6s}  "
              f"total_pnl=${summary['total_pnl']:>10,.2f}  avg_pnl/trade=${(summary['avg_pnl'] or 0):>8,.2f}  "
              f"profit_factor={pf}")

    print("\n" + "=" * 78)
    print("PART 2: EXIT-STRATEGY OPTIMIZATION (per timeframe, all variants)")
    print("=" * 78)
    best_per_tf = {}
    all_variant_results = {}
    for tf in TIMEFRAMES:
        print(f"\n--- {TIMEFRAME_LABELS[tf]} ---")
        rows = []
        for risk_name, risk_exit, risk_pct in RISK_VARIANTS:
            for tp_pct, tp_name in TAKE_PROFIT_VARIANTS:
                summary, _ = run_variant(data, tf, risk_exit, risk_pct, tp_pct)
                label = f"{risk_name} / {tp_name}"
                rows.append((label, summary))
        rows.sort(key=lambda r: r[1]["total_pnl"], reverse=True)
        all_variant_results[tf] = rows
        for label, summary in rows:
            wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
            pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
            print(f"  {label:28s} trades={summary['trades']:4d}  win_rate={wr:>6s}  "
                  f"total_pnl=${summary['total_pnl']:>10,.2f}  profit_factor={pf}")
        best_per_tf[tf] = rows[0]

    print("\n" + "=" * 78)
    print("BEST EXIT VARIANT PER TIMEFRAME")
    print("=" * 78)
    for tf in TIMEFRAMES:
        label, summary = best_per_tf[tf]
        print(f"{TIMEFRAME_LABELS[tf]:12s} -> {label}  (total_pnl=${summary['total_pnl']:,.2f}, "
              f"win_rate={summary['win_rate']*100:.1f}%, trades={summary['trades']})")

    out = {
        "timeframe_baseline": {tf: timeframe_results[tf][0] for tf in TIMEFRAMES},
        "timeframe_baseline_per_ticker": {tf: timeframe_results[tf][1] for tf in TIMEFRAMES},
        "variant_results": {tf: [{"label": l, **s} for l, s in all_variant_results[tf]] for tf in TIMEFRAMES},
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "study_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
