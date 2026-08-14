"""
Tighter entry-filter study, prompted by looking at the live monitor's first
10 real losing trades: every one of them barely cleared the entry filter's
minimum thresholds (cloud-sep 0.30-0.49% against a 0.3% floor, RSI in the
high-60s against a 70 ceiling, several with ADX 25-27 against a 25 floor),
and 5/10 were entered in the last 90 minutes of the session and held
overnight into the reversal. This tests whether raising those thresholds
(demanding more margin over the minimum, not just clearing it) and/or
cutting off entries near the close improves things -- combined with the
two exit-side findings already validated this session (stop-3% floor +
chandelier-8x trailing exit, no hard take-profit cap).

All variants use: any-time signal timing (validated best), stop-3% +
chandelier-8x exit (validated best), wide 41-ticker dataset (validated
against overfitting on the narrow 10-ticker set).

Data: raw_bars_wide.json (41 tickers, 10-minute candles, ~60 trading days).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy  # noqa: E402
import indicators  # noqa: E402
import sim_engine as engine  # noqa: E402

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars_wide.json")
TIMEFRAME = "10m"
STOP_PCT = 0.03
CHANDELIER_MULT = 8.0

# Current live thresholds (the "barely clears the floor" filter).
BASE = dict(rvol_min=1.5, rsi_min=50, rsi_max=70, adx_min=25, sep_min=0.003)

VARIANTS = {
    "current (baseline)": BASE,
    "RSI cap 70->65":      dict(BASE, rsi_max=65),
    "ADX floor 25->30":    dict(BASE, adx_min=30),
    "cloud-sep 0.3%->0.5%": dict(BASE, sep_min=0.005),
    "all three tightened": dict(BASE, rsi_max=65, adx_min=30, sep_min=0.005),
}

LATE_CUTOFF_MIN = 330  # minutes since 9:30 open; 330 = 15:00 ET, last 60min of session blocked


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
        "atr": indicators.compute_atr(bars, period=14),
        "mins_since_open": indicators.compute_minutes_since_open(bars),
    }


def entry_filter_ok(rvol, rsi, adx, sep, rvol_min, rsi_min, rsi_max, adx_min, sep_min):
    if None in (rvol, rsi, adx, sep):
        return False
    return rvol >= rvol_min and rsi_min < rsi < rsi_max and adx >= adx_min and sep >= sep_min


def build_filter(pre, thresholds, late_cutoff=None):
    n = len(pre["rsi"])
    out = [False] * n
    for i in range(n):
        if late_cutoff is not None and pre["mins_since_open"][i] >= late_cutoff:
            continue
        out[i] = entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i], **thresholds)
    return out


def run_variant(bars_by_ticker, pre_by_ticker, thresholds, late_cutoff=None):
    all_trades, per_ticker = [], {}
    for t, bars in bars_by_ticker.items():
        pre = pre_by_ticker[t]
        ef = build_filter(pre, thresholds, late_cutoff)
        trades = engine.simulate(bars, risk_exit="stop", risk_pct=STOP_PCT, take_profit_pct=None,
                                  entry_filter=ef, atr=pre["atr"], chandelier_mult=CHANDELIER_MULT)
        for tr in trades:
            tr["ticker"] = t
        all_trades.extend(trades)
        per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades


def print_summary(name, summary):
    wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
    pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    print(f"{name:45s} trades={summary['trades']:4d}  win_rate={wr:>6s}  "
          f"total_pnl=${summary['total_pnl']:>11,.2f}  avg/trade=${(summary['avg_pnl'] or 0):>8,.2f}  pf={pf}")


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    pre_by_ticker = {t: precompute(bars) for t, bars in bars_by_ticker.items()}

    print("=" * 100)
    print("TIGHTER ENTRY-FILTER STUDY (exit fixed: stop-3% + chandelier-8x, no TP cap)")
    print("=" * 100)

    all_results = {}
    for name, thresholds in VARIANTS.items():
        summary, per_ticker, trades = run_variant(bars_by_ticker, pre_by_ticker, thresholds)
        print_summary(name, summary)
        all_results[name] = {"summary": summary, "per_ticker": per_ticker, "trades": trades}

    print()
    late_summary, late_per_ticker, late_trades = run_variant(
        bars_by_ticker, pre_by_ticker, BASE, late_cutoff=LATE_CUTOFF_MIN
    )
    print_summary("current thresholds + no entries in last 60min", late_summary)
    all_results["current + late-cutoff"] = {"summary": late_summary, "per_ticker": late_per_ticker, "trades": late_trades}

    combo_summary, combo_per_ticker, combo_trades = run_variant(
        bars_by_ticker, pre_by_ticker, VARIANTS["all three tightened"], late_cutoff=LATE_CUTOFF_MIN
    )
    print_summary("all three tightened + no entries in last 60min", combo_summary)
    all_results["all tightened + late-cutoff"] = {"summary": combo_summary, "per_ticker": combo_per_ticker, "trades": combo_trades}

    print("\nExit reason breakdown, per variant:")
    from collections import Counter
    for name, r in all_results.items():
        print(f"  {name}:", dict(Counter(t["reason"] for t in r["trades"])))

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tighter_filter_study_results.json")
    with open(out_path, "w") as f:
        json.dump({name: {"summary": r["summary"], "per_ticker": r["per_ticker"]} for name, r in all_results.items()}, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
