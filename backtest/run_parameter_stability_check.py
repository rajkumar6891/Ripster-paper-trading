"""
Distinguishes two different things the IS/OOS collapse (run_baseline_is_oos.py)
could mean:

1. PARAMETER OVERFITTING: chandelier_mult=8 and cloud_sep_min=0.5% were
   selected by sweeping many values on this exact 60-day/41-ticker sample
   and picking the best -- if the *optimal* value is wildly different in
   the first half vs the second half, that's evidence the specific numbers
   are fit to noise in this sample, not a real structural optimum.

2. REGIME DEPENDENCE: a trend-following EMA-cloud strategy is structurally
   expected to perform worse in choppier/less-trending conditions even with
   *correctly-chosen, stable* parameters -- if the same-ish multiplier/
   threshold remains best (or near-best) in both halves independently, but
   absolute performance still drops in the second half, that points to (2)
   rather than (1): the edge is real but conditional on market regime, not
   an artifact of curve-fitting the parameter values themselves.

This re-sweeps chandelier_mult and cloud_sep_min SEPARATELY on the first
half and second half of the same 41-ticker dataset used throughout this
session, to see which story the data actually supports.
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

CHANDELIER_SWEEP = [4.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]
CLOUD_SEP_SWEEP = [0.003, 0.004, 0.005, 0.006, 0.007, 0.008]


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


def run(bars_by_ticker, chandelier_mult, cloud_sep_min):
    all_trades = []
    for t, bars in bars_by_ticker.items():
        if len(bars) < 60:
            continue
        ef, atr = precompute(bars, cloud_sep_min)
        trades = engine.simulate(bars, risk_exit="stop", risk_pct=strategy.STOP_LOSS_PCT, take_profit_pct=None,
                                  entry_filter=ef, atr=atr, chandelier_mult=chandelier_mult)
        all_trades.extend(trades)
    return engine.summarize(all_trades)


def sweep_and_report(label, bars_by_ticker):
    print(f"\n{'='*90}\n{label}\n{'='*90}")

    print(f"\n-- Chandelier multiplier sweep (cloud_sep fixed at {strategy.CLOUD_SEP_MIN*100:.1f}%) --")
    chand_results = {}
    for mult in CHANDELIER_SWEEP:
        s = run(bars_by_ticker, mult, strategy.CLOUD_SEP_MIN)
        chand_results[mult] = s
        wr = f"{s['win_rate']*100:.1f}%" if s["win_rate"] is not None else "n/a"
        pf = f"{s['profit_factor']:.2f}" if isinstance(s["profit_factor"], float) else str(s["profit_factor"])
        print(f"  {mult:4.1f}x  trades={s['trades']:4d}  win_rate={wr:>6s}  total_pnl=${s['total_pnl']:>10,.2f}  pf={pf}")
    best_chand = max(chand_results, key=lambda m: chand_results[m]["total_pnl"])
    print(f"  BEST chandelier mult in {label}: {best_chand}x (deployed value: 8.0x)")

    print(f"\n-- Cloud-sep threshold sweep (chandelier fixed at {strategy.CHANDELIER_MULT}x) --")
    sep_results = {}
    for sep in CLOUD_SEP_SWEEP:
        s = run(bars_by_ticker, strategy.CHANDELIER_MULT, sep)
        sep_results[sep] = s
        wr = f"{s['win_rate']*100:.1f}%" if s["win_rate"] is not None else "n/a"
        pf = f"{s['profit_factor']:.2f}" if isinstance(s["profit_factor"], float) else str(s["profit_factor"])
        print(f"  {sep*100:4.1f}%  trades={s['trades']:4d}  win_rate={wr:>6s}  total_pnl=${s['total_pnl']:>10,.2f}  pf={pf}")
    best_sep = max(sep_results, key=lambda s: sep_results[s]["total_pnl"])
    print(f"  BEST cloud-sep in {label}: {best_sep*100:.1f}% (deployed value: 0.5%)")

    return {
        "chandelier_sweep": {str(k): v for k, v in chand_results.items()}, "best_chandelier": best_chand,
        "cloud_sep_sweep": {str(k): v for k, v in sep_results.items()}, "best_cloud_sep": best_sep,
    }


def main():
    data = load_data()
    bars_by_ticker = {t: data[t][TIMEFRAME] for t in data}
    first_half = {t: bars[:len(bars) // 2] for t, bars in bars_by_ticker.items()}
    second_half = {t: bars[len(bars) // 2:] for t, bars in bars_by_ticker.items()}

    full_result = sweep_and_report("FULL WINDOW (what the deployed params were chosen on)", bars_by_ticker)
    first_result = sweep_and_report("FIRST HALF ONLY", first_half)
    second_result = sweep_and_report("SECOND HALF ONLY", second_half)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parameter_stability_results.json")
    with open(out_path, "w") as f:
        json.dump({"full_window": full_result, "first_half": first_result, "second_half": second_result}, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
