"""
Exit-strategy comparison: pure cloud-exit only (fast cloud crosses back
below slow cloud -> exit, no stop-loss, no take-profit cap) vs. the current
live exit (stop-3% + take-profit-15% + cloud-exit).

Entry rule held fixed at the live monitor's actual logic ("any-time"
filter: cloud bullish-aligned + RVOL/RSI/ADX/cloud-sep filter passes, no
freshness requirement).

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


def worst_intrabar_drawdown(bars, entry_ts, entry_price, exit_ts):
    """Worst (lowest) low reached while the position was open, as a % move
    from entry -- to show the downside risk pure cloud-exit is exposed to
    with no stop."""
    worst = 0.0
    for b in bars:
        if entry_ts <= b["ts"] <= exit_ts:
            dd = (b["low"] - entry_price) / entry_price
            worst = min(worst, dd)
    return worst


def run_variant(bars_by_ticker, pre_by_ticker, risk_exit, risk_pct, take_profit_pct, track_drawdown=False):
    all_trades = []
    per_ticker = {}
    for t, bars in bars_by_ticker.items():
        pre = pre_by_ticker[t]
        ef = build_any_time_filter(pre)
        trades = engine.simulate(bars, risk_exit=risk_exit, risk_pct=risk_pct,
                                  take_profit_pct=take_profit_pct, entry_filter=ef)
        for tr in trades:
            tr["ticker"] = t
            if track_drawdown:
                tr["worst_dd"] = worst_intrabar_drawdown(bars, tr["entry_ts"], tr["entry_price"], tr["exit_ts"])
        all_trades.extend(trades)
        per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades


def print_summary(name, summary):
    wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
    pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    print(f"{name:40s} trades={summary['trades']:3d}  win_rate={wr:>6s}  "
          f"total_pnl=${summary['total_pnl']:>10,.2f}  avg/trade=${(summary['avg_pnl'] or 0):>8,.2f}  pf={pf}")


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    pre_by_ticker = {t: precompute(bars_by_ticker[t]) for t in bars_by_ticker}

    print("=" * 100)
    print("EXIT-STRATEGY COMPARISON (entry rule fixed: live monitor's any-time RVOL/RSI/ADX/sep filter)")
    print("=" * 100)

    baseline_summary, baseline_per_ticker, baseline_trades = run_variant(
        bars_by_ticker, pre_by_ticker, risk_exit="stop", risk_pct=0.03, take_profit_pct=0.15
    )
    print_summary("Current live (stop-3% + TP-15% + cloud-exit)", baseline_summary)

    pure_summary, pure_per_ticker, pure_trades = run_variant(
        bars_by_ticker, pre_by_ticker, risk_exit=None, risk_pct=None, take_profit_pct=None, track_drawdown=True
    )
    print_summary("Pure cloud-exit only (no stop, no TP)", pure_summary)

    print("\nPer-ticker, pure cloud-exit only:")
    print(f"{'Ticker':6s} {'trades':>7s} {'win_rate':>9s} {'total_pnl':>12s} {'avg_pnl':>10s}")
    for t in bars_by_ticker:
        s = pure_per_ticker[t]
        wr_t = f"{s['win_rate']*100:.1f}%" if s["win_rate"] is not None else "n/a"
        print(f"{t:6s} {s['trades']:7d} {wr_t:>9s} ${s['total_pnl']:>10,.2f} ${(s['avg_pnl'] or 0):>8,.2f}")

    print("\nIndividual trades, pure cloud-exit only (sorted by P&L):")
    print(f"{'ticker':6s} {'ret%':>7s} {'pnl':>10s} {'worst_dd%':>10s} {'hold_days':>10s}")
    for tr in sorted(pure_trades, key=lambda t: t["pnl"], reverse=True):
        hold_days = (tr["exit_ts"] - tr["entry_ts"]) / 86400
        print(f"{tr['ticker']:6s} {tr['return_pct']*100:7.2f} ${tr['pnl']:9,.2f} {tr['worst_dd']*100:10.2f} {hold_days:10.1f}")

    n = len(pure_trades)
    worst_dds = sorted((t["worst_dd"] for t in pure_trades))
    print(f"\nWorst intrabar drawdown across all {n} pure-cloud-exit trades: {worst_dds[0]*100:.2f}%")
    print(f"Median intrabar drawdown: {worst_dds[n//2]*100:.2f}%")
    beyond_3pct = sum(1 for d in worst_dds if d <= -0.03)
    beyond_5pct = sum(1 for d in worst_dds if d <= -0.05)
    beyond_10pct = sum(1 for d in worst_dds if d <= -0.10)
    print(f"Trades that dipped 3%+ below entry at some point: {beyond_3pct}/{n}")
    print(f"Trades that dipped 5%+ below entry at some point: {beyond_5pct}/{n}")
    print(f"Trades that dipped 10%+ below entry at some point: {beyond_10pct}/{n}")

    losers = [t for t in pure_trades if t["pnl"] < 0]
    print(f"\nWorst losing trades (pure cloud-exit, no stop):")
    for tr in sorted(losers, key=lambda t: t["pnl"])[:5]:
        print(f"  {tr['ticker']:6s} entry ${tr['entry_price']:.2f} -> exit ${tr['exit_price']:.2f}  "
              f"ret={tr['return_pct']*100:.2f}%  pnl=${tr['pnl']:,.2f}  worst_dd={tr['worst_dd']*100:.2f}%")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pure_cloud_exit_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "baseline_stop3_tp15": {"summary": baseline_summary, "per_ticker": baseline_per_ticker},
            "pure_cloud_exit": {"summary": pure_summary, "per_ticker": pure_per_ticker, "trades": pure_trades},
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
