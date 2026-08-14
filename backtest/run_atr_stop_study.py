"""
ATR-based stop study: replace the current fixed 3% stop-loss with a
volatility-normalized stop (entry_price - atr_mult * ATR(14)-at-entry,
fixed for the trade's life -- the classic Turtle-style "entry - 2xATR"
stop), holding everything else fixed at the live monitor's current
settings (any-time RVOL/RSI/ADX/cloud-sep entry filter, 10% take-profit
cap, cloud-bearish-cross exit).

Sweeps atr_mult in [1.5, 2.0, 2.5, 3.0] against the fixed-3%-stop baseline.

Data: raw_bars.json (10 tickers, 10-minute candles, ~60 trading days,
2026-05-15 to 2026-08-11 -- the same cache the other studies use).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy  # noqa: E402
import indicators  # noqa: E402
import sim_engine as engine  # noqa: E402

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars.json")
TIMEFRAME = "10m"
TAKE_PROFIT_PCT = 0.10  # current live setting
ATR_MULTS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]


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
    print(f"{name:42s} trades={summary['trades']:3d}  win_rate={wr:>6s}  "
          f"total_pnl=${summary['total_pnl']:>10,.2f}  avg/trade=${(summary['avg_pnl'] or 0):>8,.2f}  pf={pf}")


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    pre_by_ticker = {t: precompute(bars_by_ticker[t]) for t in bars_by_ticker}

    print("=" * 100)
    print("ATR-STOP STUDY (entry rule fixed: live monitor's any-time RVOL/RSI/ADX/sep filter, TP=10% fixed)")
    print("=" * 100)

    baseline_summary, baseline_per_ticker, baseline_trades = run_variant(
        bars_by_ticker, pre_by_ticker, risk_exit="stop", risk_pct=0.03, take_profit_pct=TAKE_PROFIT_PCT
    )
    print_summary("Fixed 3% stop + TP-10% (current live)", baseline_summary)

    variant_results = {}
    for mult in ATR_MULTS:
        summary, per_ticker, trades = run_variant(
            bars_by_ticker, pre_by_ticker, risk_exit="atr_stop", atr_mult=mult, take_profit_pct=TAKE_PROFIT_PCT
        )
        print_summary(f"ATR-stop {mult}x ATR(14) + TP-10%", summary)
        variant_results[mult] = {"summary": summary, "per_ticker": per_ticker, "trades": trades}

    # implied stop distance (%) at entry, per multiplier, for context vs the flat 3%
    print("\nImplied stop distance (% of entry price) vs flat 3.0% today:")
    for mult in ATR_MULTS:
        pcts = sorted(t["stop_pct"] * 100 for t in variant_results[mult]["trades"] if "stop_pct" in t)
        if not pcts:
            continue
        n = len(pcts)
        tighter_than_3pct = sum(1 for p in pcts if p < 3.0)
        print(f"  {mult}x: min={pcts[0]:.2f}%  median={pcts[n//2]:.2f}%  max={pcts[-1]:.2f}%  "
              f"mean={sum(pcts)/n:.2f}%  ({tighter_than_3pct}/{n} entries tighter than 3%)")

    print(f"\n{'Ticker':6s} {'baseline_pnl':>13s}", end="")
    for mult in ATR_MULTS:
        print(f" {'atr'+str(mult)+'x_pnl':>13s}", end="")
    print()
    for t in bars_by_ticker:
        print(f"{t:6s} ${baseline_per_ticker[t]['total_pnl']:>11,.2f}", end="")
        for mult in ATR_MULTS:
            s = variant_results[mult]["per_ticker"][t]
            print(f" ${s['total_pnl']:>11,.2f}", end="")
        print()

    print("\nExit reason breakdown, per variant:")
    from collections import Counter
    print("  baseline:", dict(Counter(t["reason"] for t in baseline_trades)))
    for mult in ATR_MULTS:
        print(f"  atr {mult}x:", dict(Counter(t["reason"] for t in variant_results[mult]["trades"])))

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atr_stop_study_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "baseline_stop3_tp10": {"summary": baseline_summary, "per_ticker": baseline_per_ticker, "trades": baseline_trades},
            "atr_variants": {
                str(mult): {"summary": v["summary"], "per_ticker": v["per_ticker"], "trades": v["trades"]}
                for mult, v in variant_results.items()
            },
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
