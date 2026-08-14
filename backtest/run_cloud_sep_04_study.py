"""
Proper backtest of cloud-sep=0.4% as a candidate replacement for the
deployed 0.5%, prompted by run_parameter_stability_check.py showing 0.4%
beats 0.5% on full-window total P&L and profit factor (just not win rate),
and does better in the second half specifically.

This does what was actually promised: (1) re-sweep the chandelier
multiplier AT cloud-sep=0.4% (not just reuse the 8x chosen for 0.5% --
the best exit multiplier could differ once the entry filter changes), to
find the best paired config for 0.4%, then (2) run the same IS/OOS
first-half/second-half check on that config that was applied to the
0.5% baseline, for a fair side-by-side.

Data: raw_bars_wide.json (41 tickers, 10-minute candles).
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
CLOUD_SEP_04 = 0.004
CHANDELIER_SWEEP = [4.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]


def load_data():
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def precompute(bars, cloud_sep_min):
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)
    rsi = indicators.compute_rsi(closes)
    adx = indicators.compute_adx(bars)
    rvol = indicators.compute_rvol(bars)
    cloud_sep = indicators.compute_cloud_sep_pct(closes, clouds)
    atr = indicators.compute_atr(bars, period=strategy.ATR_PERIOD)
    n = len(closes)
    ef = [
        (rvol[i] is not None and rsi[i] is not None and adx[i] is not None and cloud_sep[i] is not None
         and rvol[i] >= strategy.RVOL_MIN and strategy.RSI_MIN < rsi[i] < strategy.RSI_MAX
         and adx[i] >= strategy.ADX_MIN and cloud_sep[i] >= cloud_sep_min)
        for i in range(n)
    ]
    return ef, atr


def run(bars_by_ticker, chandelier_mult, cloud_sep_min, track_per_ticker=False):
    all_trades = []
    per_ticker = {}
    for t, bars in bars_by_ticker.items():
        if len(bars) < 60:
            per_ticker[t] = engine.summarize([])
            continue
        ef, atr = precompute(bars, cloud_sep_min)
        trades = engine.simulate(bars, risk_exit="stop", risk_pct=strategy.STOP_LOSS_PCT, take_profit_pct=None,
                                  entry_filter=ef, atr=atr, chandelier_mult=chandelier_mult)
        for tr in trades:
            tr["ticker"] = t
        all_trades.extend(trades)
        if track_per_ticker:
            per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades


def print_summary(name, summary):
    wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
    pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    print(f"{name:45s} trades={summary['trades']:4d}  win_rate={wr:>6s}  "
          f"total_pnl=${summary['total_pnl']:>10,.2f}  avg/trade=${(summary['avg_pnl'] or 0):>8,.2f}  pf={pf}")


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    first_half = {t: bars[:len(bars) // 2] for t, bars in bars_by_ticker.items()}
    second_half = {t: bars[len(bars) // 2:] for t, bars in bars_by_ticker.items()}

    print("=" * 100)
    print(f"STEP 1: re-sweep chandelier multiplier AT cloud-sep={CLOUD_SEP_04*100:.1f}% (full window)")
    print("=" * 100)
    chand_results = {}
    for mult in CHANDELIER_SWEEP:
        s, _, _ = run(bars_by_ticker, mult, CLOUD_SEP_04)
        chand_results[mult] = s
        print_summary(f"  {mult}x chandelier @ cloud-sep 0.4%", s)
    best_mult = max(chand_results, key=lambda m: chand_results[m]["total_pnl"])
    print(f"\nBest chandelier multiplier at cloud-sep=0.4%: {best_mult}x "
          f"(for comparison, deployed pair is 8x @ cloud-sep=0.5%)")

    print("\n" + "=" * 100)
    print(f"STEP 2: full IS/OOS check on the paired config (chandelier={best_mult}x, cloud-sep=0.4%)")
    print("=" * 100)
    full_summary, full_per_ticker, full_trades = run(bars_by_ticker, best_mult, CLOUD_SEP_04, track_per_ticker=True)
    print_summary(f"Full window ({best_mult}x, 0.4%)", full_summary)
    first_summary, _, _ = run(first_half, best_mult, CLOUD_SEP_04)
    print_summary(f"First half ({best_mult}x, 0.4%)", first_summary)
    second_summary, _, _ = run(second_half, best_mult, CLOUD_SEP_04)
    print_summary(f"Second half ({best_mult}x, 0.4%)", second_summary)

    print("\n" + "=" * 100)
    print("STEP 3: also check the DEPLOYED chandelier value (8x) paired with cloud-sep=0.4%,")
    print("in case the deployed exit shouldn't change even if the filter threshold does")
    print("=" * 100)
    full8_summary, _, _ = run(bars_by_ticker, 8.0, CLOUD_SEP_04)
    print_summary("Full window (8x, 0.4%)", full8_summary)
    first8_summary, _, _ = run(first_half, 8.0, CLOUD_SEP_04)
    print_summary("First half (8x, 0.4%)", first8_summary)
    second8_summary, _, _ = run(second_half, 8.0, CLOUD_SEP_04)
    print_summary("Second half (8x, 0.4%)", second8_summary)

    print("\n" + "=" * 100)
    print("REFERENCE: deployed config (8x, cloud-sep=0.5%) for side-by-side")
    print("=" * 100)
    dep_full, _, _ = run(bars_by_ticker, 8.0, strategy.CLOUD_SEP_MIN)
    print_summary("Full window (deployed: 8x, 0.5%)", dep_full)
    dep_first, _, _ = run(first_half, 8.0, strategy.CLOUD_SEP_MIN)
    print_summary("First half (deployed: 8x, 0.5%)", dep_first)
    dep_second, _, _ = run(second_half, 8.0, strategy.CLOUD_SEP_MIN)
    print_summary("Second half (deployed: 8x, 0.5%)", dep_second)

    print("\nPer-ticker P&L, best 0.4% config:")
    rows = sorted(full_per_ticker.items(), key=lambda kv: kv[1]["total_pnl"], reverse=True)
    for t, s in rows:
        if s["trades"] == 0:
            continue
        wr = f"{s['win_rate']*100:.1f}%" if s["win_rate"] is not None else "n/a"
        print(f"  {t:6s} trades={s['trades']:3d}  win_rate={wr:>6s}  total_pnl=${s['total_pnl']:>9,.2f}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_sep_04_study_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "chandelier_sweep_at_0.4pct": {str(k): v for k, v in chand_results.items()},
            "best_mult_at_0.4pct": best_mult,
            "best_config_full": full_summary, "best_config_first_half": first_summary, "best_config_second_half": second_summary,
            "best_config_per_ticker": full_per_ticker,
            "chand8_at_0.4pct_full": full8_summary, "chand8_at_0.4pct_first": first8_summary, "chand8_at_0.4pct_second": second8_summary,
            "deployed_full": dep_full, "deployed_first": dep_first, "deployed_second": dep_second,
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
