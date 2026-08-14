"""
VIX study, two parts:

1. Confirm/refute "VIX up -> stocks down, VIX down -> stocks up": compute the
   correlation between VIX 5-minute returns and each stock's 5-minute
   returns across the 41-ticker wide dataset.

2. If the correlation holds, test whether gating entries on the VIX regime
   (only enter when VIX itself is falling / below its own short-term
   average -- a "risk-on" filter) improves the already-validated best config
   (any-time RVOL/RSI/ADX/cloud-sep filter + stop-3% + chandelier-8x exit)
   on the same wide dataset, or just cuts trade count for no benefit.

VIX has no exact shared 10m grid with the equities (its Yahoo feed includes
an extended pre-market session the equities' feed doesn't), so alignment is
done by nearest-VIX-bar-at-or-before-timestamp on the raw 5m series, not by
assuming matching aggregated-10m timestamps.

Data: raw_bars_wide.json (41 tickers, 10-min bars) + vix_bars.json (^VIX,
5-min bars, same 60-day window).
"""

import bisect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy  # noqa: E402
import indicators  # noqa: E402
import sim_engine as engine  # noqa: E402

WIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars_wide.json")
VIX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vix_bars.json")
TIMEFRAME = "10m"
STOP_PCT = 0.03
CHANDELIER_MULT = 8.0
VIX_SMA_PERIOD = 24  # 24 x 5min = 2 hours of VIX history


class VixLookup:
    def __init__(self, vix5m):
        self.ts = [b["ts"] for b in vix5m]
        self.close = [b["close"] for b in vix5m]
        # rolling simple moving average, aligned 1:1 with vix5m
        self.sma = [None] * len(vix5m)
        for i in range(len(vix5m)):
            if i + 1 >= VIX_SMA_PERIOD:
                self.sma[i] = sum(self.close[i + 1 - VIX_SMA_PERIOD:i + 1]) / VIX_SMA_PERIOD

    def at_or_before(self, t):
        """Index of the latest VIX bar with ts <= t, or None if t is before all VIX data."""
        idx = bisect.bisect_right(self.ts, t) - 1
        return idx if idx >= 0 else None

    def close_at(self, t):
        idx = self.at_or_before(t)
        return self.close[idx] if idx is not None else None

    def falling_regime(self, t):
        """True if VIX is below its own 2h moving average at time t (i.e.
        VIX has been trending down / risk-on), False if not, None if
        unavailable."""
        idx = self.at_or_before(t)
        if idx is None or self.sma[idx] is None:
            return None
        return self.close[idx] < self.sma[idx]


def load_data():
    with open(WIDE_PATH, "r") as f:
        equities = json.load(f)
    with open(VIX_PATH, "r") as f:
        vix = json.load(f)
    return equities, vix


def correlation(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5


def part1_correlation(equities, vix):
    print("=" * 90)
    print("PART 1: does VIX actually move opposite to stocks in this data?")
    print("=" * 90)
    vix5m = vix["5m"]
    vix_by_ts = {b["ts"]: b["close"] for b in vix5m}
    vix_ts_sorted = sorted(vix_by_ts)

    corrs = {}
    for ticker, tf in equities.items():
        bars5m = tf["5m"]
        pairs = []
        for i in range(1, len(bars5m)):
            t_prev, t_cur = bars5m[i - 1]["ts"], bars5m[i]["ts"]
            if t_cur - t_prev != 300:
                continue  # skip overnight/session gaps
            if t_prev not in vix_by_ts or t_cur not in vix_by_ts:
                continue
            stock_ret = bars5m[i]["close"] / bars5m[i - 1]["close"] - 1
            vix_ret = vix_by_ts[t_cur] / vix_by_ts[t_prev] - 1
            pairs.append((stock_ret, vix_ret))
        if len(pairs) < 30:
            continue
        stock_rets = [p[0] for p in pairs]
        vix_rets = [p[1] for p in pairs]
        corrs[ticker] = (correlation(stock_rets, vix_rets), len(pairs))

    print(f"{'Ticker':6s} {'corr':>7s} {'n_pairs':>8s}")
    for t, (c, n) in sorted(corrs.items(), key=lambda kv: kv[1][0]):
        print(f"{t:6s} {c:7.3f} {n:8d}")

    vals = [c for c, n in corrs.values()]
    avg = sum(vals) / len(vals)
    negative = sum(1 for c in vals if c < 0)
    print(f"\nAverage 5-min-return correlation across {len(vals)} tickers: {avg:.3f}")
    print(f"Tickers with negative correlation (VIX up -> stock down, as theorized): {negative}/{len(vals)}")
    return avg, corrs


def part2_vix_filter_backtest(equities, vix):
    print("\n" + "=" * 90)
    print("PART 2: does gating entries on VIX regime improve the validated best config?")
    print("(entry: any-time RVOL/RSI/ADX/sep filter; exit: stop-3% + chandelier-8x)")
    print("=" * 90)

    vlook = VixLookup(vix["5m"])
    bars_by_ticker = {t: tf[TIMEFRAME] for t, tf in equities.items()}

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

    pre_by_ticker = {t: precompute(bars) for t, bars in bars_by_ticker.items()}

    def base_filter(bars, pre):
        n = len(pre["rsi"])
        return [strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i]) for i in range(n)]

    def vix_gated_filter(bars, pre, base):
        n = len(base)
        out = [False] * n
        for i in range(n):
            if not base[i]:
                continue
            regime = vlook.falling_regime(bars[i]["ts"])
            out[i] = bool(regime)  # None (no VIX data yet) treated as fail-closed
        return out

    def run_variant(filter_fn):
        all_trades, per_ticker = [], {}
        for t, bars in bars_by_ticker.items():
            pre = pre_by_ticker[t]
            base = base_filter(bars, pre)
            ef = filter_fn(bars, pre, base) if filter_fn else base
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

    base_summary, base_per_ticker, base_trades = run_variant(None)
    print_summary("No VIX filter (current best config)", base_summary)

    gated_summary, gated_per_ticker, gated_trades = run_variant(vix_gated_filter)
    print_summary("+ VIX-falling-regime gate (VIX < its 2h SMA)", gated_summary)

    return {
        "no_vix_filter": {"summary": base_summary, "per_ticker": base_per_ticker},
        "vix_gated": {"summary": gated_summary, "per_ticker": gated_per_ticker},
    }


def main():
    equities, vix = load_data()
    avg_corr, corrs = part1_correlation(equities, vix)
    results2 = part2_vix_filter_backtest(equities, vix)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vix_study_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "correlation": {"average": avg_corr, "per_ticker": {t: c for t, (c, n) in corrs.items()}},
            "vix_filter_backtest": results2,
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
