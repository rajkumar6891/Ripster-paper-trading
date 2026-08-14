"""
Fresh-cross entry study: unlike the live monitor (which will enter on ANY
closed bar where the cloud is currently bullish-aligned AND the RVOL/RSI/
ADX/cloud-sep filter passes, even hours after the cloud first turned
bullish), this variant only takes a trade on the exact bar where the cloud
crosses from not-bullish to bullish -- and only if the same entry filter
passes on that same bar. If the filter fails on the crossover bar, that
setup is skipped entirely (no waiting for the filter to catch up later).

Exit is unchanged: stop-3% + 15% take-profit + cloud bearish-exit (the
live monitor's current exit rule).

Data: raw_bars.json (10 tickers, 10-minute candles, ~60 trading days,
2026-05-15 to 2026-08-11 -- the same cache run_filter_study.py uses).
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
EXIT_RISK_MODE, EXIT_RISK_PCT, EXIT_TP_PCT = "stop", 0.03, 0.15


def load_data():
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def precompute(bars):
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)
    n = len(closes)
    bullish = [False] * n
    for i in range(n):
        e5, e12, e34, e50 = clouds[5][i], clouds[12][i], clouds[34][i], clouds[50][i]
        if None in (e5, e12, e34, e50):
            continue
        bullish[i] = strategy.bullish_entry_signal(closes[i], e5, e12, e34, e50)
    return {
        "bullish": bullish,
        "rsi": indicators.compute_rsi(closes),
        "adx": indicators.compute_adx(bars),
        "rvol": indicators.compute_rvol(bars),
        "cloud_sep": indicators.compute_cloud_sep_pct(closes, clouds),
    }


def build_fresh_cross_filter(pre):
    """True only on the bar where bullish state flips False/None -> True,
    AND the RVOL/RSI/ADX/cloud-sep filter (strategy.entry_filter_ok --
    same thresholds the live monitor uses) also passes on that same bar."""
    n = len(pre["bullish"])
    out = [False] * n
    for i in range(n):
        if not pre["bullish"][i]:
            continue
        prev_bullish = pre["bullish"][i - 1] if i > 0 else False
        if prev_bullish:
            continue  # not a fresh cross, already in a bullish streak
        filt_ok = strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i])
        out[i] = filt_ok
    return out


def build_within_window_filter(pre, max_bars):
    """True while (a) we're within max_bars of the most recent fresh cross
    AND (b) the cloud has stayed continuously bullish since that cross
    (a reversion to non-bullish resets the window -- the next bullish flip
    is a brand new cross), AND (c) the RVOL/RSI/ADX/sep filter passes on
    this bar. Once a trade fires inside the window, sim_engine's own
    position-is-None gate naturally stops further entries until it exits."""
    n = len(pre["bullish"])
    out = [False] * n
    last_cross_idx = None
    for i in range(n):
        if pre["bullish"][i]:
            if i == 0 or not pre["bullish"][i - 1]:
                last_cross_idx = i
        else:
            last_cross_idx = None
        within_window = last_cross_idx is not None and (i - last_cross_idx) <= max_bars
        if within_window:
            filt_ok = strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i])
            out[i] = filt_ok
    return out


def build_any_time_filter(pre):
    """Live-monitor-equivalent: filter must pass on the bar, no freshness
    requirement (bullish state can have been true for a while already)."""
    n = len(pre["bullish"])
    out = [False] * n
    for i in range(n):
        out[i] = strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i])
    return out


def run_variant(data, bars_by_ticker, pre_by_ticker, filter_builder):
    all_trades = []
    per_ticker = {}
    cross_counts = {}
    for t, bars in bars_by_ticker.items():
        pre = pre_by_ticker[t]
        ef = filter_builder(pre)
        # count how many fresh crosses existed at all (regardless of filter) for context
        n = len(pre["bullish"])
        crosses = sum(1 for i in range(n) if pre["bullish"][i] and not (pre["bullish"][i - 1] if i > 0 else False))
        cross_counts[t] = crosses
        trades = engine.simulate(bars, risk_exit=EXIT_RISK_MODE, risk_pct=EXIT_RISK_PCT,
                                  take_profit_pct=EXIT_TP_PCT, entry_filter=ef)
        all_trades.extend(trades)
        per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades, cross_counts


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    pre_by_ticker = {t: precompute(bars_by_ticker[t]) for t in bars_by_ticker}

    print("=" * 90)
    print("FRESH-CROSS + SAME-CANDLE FILTER  (requested variant)")
    print("Entry: cloud crosses bullish on this bar, AND RVOL/RSI/ADX/sep filter passes on this SAME bar.")
    print("If filter fails on the cross bar, that setup is skipped -- no waiting.")
    print("=" * 90)
    summary, per_ticker, trades, cross_counts = run_variant(data, bars_by_ticker, pre_by_ticker, build_fresh_cross_filter)
    total_crosses = sum(cross_counts.values())
    wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
    pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    print(f"\nTotal fresh bullish crosses across all tickers: {total_crosses}")
    print(f"Trades actually taken (cross + filter passed same bar): {summary['trades']}")
    print(f"Total P&L: ${summary['total_pnl']:,.2f}   Win rate: {wr}   Avg P&L/trade: ${(summary['avg_pnl'] or 0):,.2f}   Profit factor: {pf}\n")
    print(f"{'Ticker':6s} {'crosses':>8s} {'trades':>7s} {'win_rate':>9s} {'total_pnl':>12s} {'avg_pnl':>10s}")
    for t in bars_by_ticker:
        s = per_ticker[t]
        wr_t = f"{s['win_rate']*100:.1f}%" if s["win_rate"] is not None else "n/a"
        print(f"{t:6s} {cross_counts[t]:8d} {s['trades']:7d} {wr_t:>9s} ${s['total_pnl']:>10,.2f} "
              f"${(s['avg_pnl'] or 0):>8,.2f}")

    print("\nIndividual trades:")
    for tr in sorted(trades, key=lambda x: x["entry_ts"]):
        print(f"  entry ${tr['entry_price']:.2f} -> exit ${tr['exit_price']:.2f} ({tr['reason']:12s}) "
              f"pnl=${tr['pnl']:>8,.2f}  ret={tr['return_pct']*100:>6.2f}%")

    print("\n" + "=" * 90)
    print("WITHIN 30 MINUTES OF THE CROSS (filter can pass on the cross bar or up to 3 bars / 30min later,")
    print("as long as the cloud has stayed continuously bullish since the cross)")
    print("=" * 90)
    summary3, per_ticker3, trades3, _ = run_variant(
        data, bars_by_ticker, pre_by_ticker, lambda pre: build_within_window_filter(pre, max_bars=3)
    )
    wr3 = f"{summary3['win_rate']*100:.1f}%" if summary3["win_rate"] is not None else "n/a"
    pf3 = f"{summary3['profit_factor']:.2f}" if isinstance(summary3["profit_factor"], float) else str(summary3["profit_factor"])
    print(f"Trades: {summary3['trades']}   Total P&L: ${summary3['total_pnl']:,.2f}   Win rate: {wr3}   "
          f"Avg P&L/trade: ${(summary3['avg_pnl'] or 0):,.2f}   Profit factor: {pf3}\n")
    print(f"{'Ticker':6s} {'trades':>7s} {'win_rate':>9s} {'total_pnl':>12s} {'avg_pnl':>10s}")
    for t in bars_by_ticker:
        s = per_ticker3[t]
        wr_t = f"{s['win_rate']*100:.1f}%" if s["win_rate"] is not None else "n/a"
        print(f"{t:6s} {s['trades']:7d} {wr_t:>9s} ${s['total_pnl']:>10,.2f} ${(s['avg_pnl'] or 0):>8,.2f}")
    print("\nIndividual trades:")
    for tr in sorted(trades3, key=lambda x: x["entry_ts"]):
        print(f"  entry ${tr['entry_price']:.2f} -> exit ${tr['exit_price']:.2f} ({tr['reason']:12s}) "
              f"pnl=${tr['pnl']:>8,.2f}  ret={tr['return_pct']*100:>6.2f}%")

    print("\n" + "=" * 90)
    print("FOR COMPARISON: same filter, no freshness requirement (how the live monitor behaves today)")
    print("=" * 90)
    summary2, per_ticker2, trades2, _ = run_variant(data, bars_by_ticker, pre_by_ticker, build_any_time_filter)
    wr2 = f"{summary2['win_rate']*100:.1f}%" if summary2["win_rate"] is not None else "n/a"
    pf2 = f"{summary2['profit_factor']:.2f}" if isinstance(summary2["profit_factor"], float) else str(summary2["profit_factor"])
    print(f"Trades: {summary2['trades']}   Total P&L: ${summary2['total_pnl']:,.2f}   Win rate: {wr2}   "
          f"Avg P&L/trade: ${(summary2['avg_pnl'] or 0):,.2f}   Profit factor: {pf2}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fresh_cross_study_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "fresh_cross": {"summary": summary, "per_ticker": per_ticker, "trades": trades, "total_crosses": total_crosses},
            "within_30min": {"summary": summary3, "per_ticker": per_ticker3, "trades": trades3},
            "any_time_filter": {"summary": summary2, "per_ticker": per_ticker2},
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
