"""
In-sample/out-of-sample check for the currently DEPLOYED baseline config
itself (stop-3% + chandelier-8x + RVOL/RSI/ADX/cloud-sep>=0.5% filter),
prompted by run_regime_vix_study.py finding that several filter variants
looked like genuine win-rate improvements in the first half of the 60-day
window and then collapsed in the second half. That check never covered the
baseline -- this closes that gap: is the config we actually deployed stable
across the two halves, or is it *also* a first-half artifact?

Splits each ticker's ~60 trading days at the midpoint (chronological, per
ticker) and runs the exact deployed parameters on each half independently,
using the same entry filter, exit logic, and dataset as every other study
this session.

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
        "atr": indicators.compute_atr(bars, period=strategy.ATR_PERIOD),
    }


def build_filter(pre):
    n = len(pre["rsi"])
    return [strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i]) for i in range(n)]


def run_on_bars(bars_by_ticker):
    all_trades, per_ticker = [], {}
    for t, bars in bars_by_ticker.items():
        if len(bars) < 60:  # not enough history for indicators to matter
            per_ticker[t] = engine.summarize([])
            continue
        pre = precompute(bars)
        ef = build_filter(pre)
        trades = engine.simulate(bars, risk_exit="stop", risk_pct=strategy.STOP_LOSS_PCT, take_profit_pct=None,
                                  entry_filter=ef, atr=pre["atr"], chandelier_mult=strategy.CHANDELIER_MULT)
        for tr in trades:
            tr["ticker"] = t
        all_trades.extend(trades)
        per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades


def print_summary(name, summary):
    wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
    pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    print(f"{name:30s} trades={summary['trades']:4d}  win_rate={wr:>6s}  "
          f"total_pnl=${summary['total_pnl']:>11,.2f}  avg/trade=${(summary['avg_pnl'] or 0):>8,.2f}  pf={pf}")


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}

    full_summary, full_per_ticker, full_trades = run_on_bars(bars_by_ticker)
    print_summary("Full window (baseline, deployed)", full_summary)

    first_half = {t: bars[:len(bars) // 2] for t, bars in bars_by_ticker.items()}
    second_half = {t: bars[len(bars) // 2:] for t, bars in bars_by_ticker.items()}

    first_summary, first_per_ticker, first_trades = run_on_bars(first_half)
    print_summary("First half (~first 30 trading days)", first_summary)

    second_summary, second_per_ticker, second_trades = run_on_bars(second_half)
    print_summary("Second half (~last 30 trading days)", second_summary)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_is_oos_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "full_window": {"summary": full_summary, "per_ticker": full_per_ticker},
            "first_half": {"summary": first_summary, "per_ticker": first_per_ticker},
            "second_half": {"summary": second_summary, "per_ticker": second_per_ticker},
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
