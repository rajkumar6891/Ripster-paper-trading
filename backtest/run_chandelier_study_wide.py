"""
Same chandelier-exit sweep as run_chandelier_study.py, but against the
wider 41-ticker, sector-diverse dataset (raw_bars_wide.json) instead of the
original 10 mega-cap/tech names -- to check whether the sharp 7x peak found
on the narrow sample holds up or was overfit to it.

Data: raw_bars_wide.json (41 tickers, 10-minute candles, ~60 trading days,
same window as raw_bars.json).
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
CHANDELIER_MULTS = [2.0, 3.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 15.0]


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
    }


def build_any_time_filter(pre):
    n = len(pre["rsi"])
    return [strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i]) for i in range(n)]


def run_variant(bars_by_ticker, pre_by_ticker, **sim_kwargs):
    all_trades = []
    per_ticker = {}
    for t, bars in bars_by_ticker.items():
        pre = pre_by_ticker[t]
        ef = build_any_time_filter(pre)
        trades = engine.simulate(bars, entry_filter=ef, atr=pre["atr"], **sim_kwargs)
        for tr in trades:
            tr["ticker"] = t
        all_trades.extend(trades)
        per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades


def print_summary(name, summary):
    wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
    pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    print(f"{name:40s} trades={summary['trades']:4d}  win_rate={wr:>6s}  "
          f"total_pnl=${summary['total_pnl']:>11,.2f}  avg/trade=${(summary['avg_pnl'] or 0):>8,.2f}  pf={pf}")


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    pre_by_ticker = {t: precompute(bars_by_ticker[t]) for t in bars_by_ticker}

    print("=" * 100)
    print(f"CHANDELIER-EXIT STUDY -- WIDE DATASET ({len(bars_by_ticker)} tickers)")
    print("=" * 100)

    baseline_summary, baseline_per_ticker, baseline_trades = run_variant(
        bars_by_ticker, pre_by_ticker, risk_exit="stop", risk_pct=STOP_PCT, take_profit_pct=0.10
    )
    print_summary("Current live (stop-3% + TP-10% + cloud-exit)", baseline_summary)

    nocap_summary, nocap_per_ticker, nocap_trades = run_variant(
        bars_by_ticker, pre_by_ticker, risk_exit="stop", risk_pct=STOP_PCT, take_profit_pct=None
    )
    print_summary("No cap (stop-3% + cloud-exit only)", nocap_summary)

    variant_results = {}
    for mult in CHANDELIER_MULTS:
        summary, per_ticker, trades = run_variant(
            bars_by_ticker, pre_by_ticker, risk_exit="stop", risk_pct=STOP_PCT,
            take_profit_pct=None, chandelier_mult=mult
        )
        print_summary(f"Chandelier {mult}x ATR(14) (stop-3% floor, no TP cap)", summary)
        variant_results[mult] = {"summary": summary, "per_ticker": per_ticker, "trades": trades}

    print("\nExit reason breakdown, per variant:")
    from collections import Counter
    print("  live (stop3+tp10):", dict(Counter(t["reason"] for t in baseline_trades)))
    print("  no-cap (stop3):   ", dict(Counter(t["reason"] for t in nocap_trades)))
    for mult in CHANDELIER_MULTS:
        print(f"  chandelier {mult}x:", dict(Counter(t["reason"] for t in variant_results[mult]["trades"])))

    best_mult = max(variant_results, key=lambda m: variant_results[m]["summary"]["total_pnl"])
    best_trades = sorted(variant_results[best_mult]["trades"], key=lambda t: t["pnl"], reverse=True)[:10]
    print(f"\nTop trades under best chandelier variant ({best_mult}x):")
    for tr in best_trades:
        print(f"  {tr['ticker']:6s} ret={tr['return_pct']*100:6.2f}%  pnl=${tr['pnl']:>8,.2f}  reason={tr['reason']}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chandelier_study_wide_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "baseline_stop3_tp10": {"summary": baseline_summary, "per_ticker": baseline_per_ticker},
            "nocap_stop3": {"summary": nocap_summary, "per_ticker": nocap_per_ticker},
            "chandelier_variants": {
                str(mult): {"summary": v["summary"], "per_ticker": v["per_ticker"], "trades": v["trades"]}
                for mult, v in variant_results.items()
            },
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
