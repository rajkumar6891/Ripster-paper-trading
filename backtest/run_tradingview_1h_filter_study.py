# 1h-trend-filter study: does gating the existing 10-min entry signal on
# real TradingView 1-hour EMA34/EMA50 cross alerts (as opposed to a
# self-computed proxy like the earlier SPY/sector-ETF regime filter)
# improve the deployed config? User framing: 1h crosses show the
# underlying trend, 10-min filters show current movement.
#
# Alert stream only covers 2026-07-29 onward (verified via Gmail search
# date-range bisection -- nothing earlier exists), so this is backtested
# ONLY over the overlap between that alert window and the price data
# (raw_bars_wide.json), not the full 60-day window used elsewhere in this
# project. That overlap is roughly 2026-07-29 to whenever the price cache
# ends -- computed at runtime below, not hardcoded, since the cache is a
# live rolling file. This is a MUCH smaller sample than the other studies
# in this project -- expect trade counts in the dozens, not hundreds.
#
# Gate logic: at a given 10-min bar for a ticker, the "current 1h state"
# is whatever direction the most recent alert (of either direction) at or
# before that timestamp said. No known state yet (before the ticker's
# first alert in-window) fails CLOSED (no entry), consistent with how
# missing indicator data is treated elsewhere in this project. Tickers
# with zero alerts in-window (CRM, NOW, WMT -- confirmed via a broadened
# non-phrase Gmail search, not a search artifact) simply never pass the
# gate.

import bisect
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy  # noqa: E402
import indicators  # noqa: E402
import sim_engine as engine  # noqa: E402

WIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_bars_wide.json")
ALERTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tradingview_1h_cross_alerts.json")
TIMEFRAME = "10m"
MIN_TRADES_TO_TRUST = 15


def load():
    with open(WIDE_PATH) as f:
        wide = json.load(f)
    with open(ALERTS_PATH) as f:
        alerts = json.load(f)
    return wide, alerts


def parse_iso_ts(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


class AlertLookup:
    def __init__(self, alerts_for_ticker):
        rows = sorted(alerts_for_ticker, key=lambda a: a["ts_utc"])
        self.ts = [parse_iso_ts(a["ts_utc"]) for a in rows]
        self.direction = [a["direction"] for a in rows]

    def bullish_at(self, t):
        idx = bisect.bisect_right(self.ts, t) - 1
        if idx < 0:
            return None
        return self.direction[idx] == "bullish"


def precompute(bars):
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)
    rsi = indicators.compute_rsi(closes)
    adx = indicators.compute_adx(bars)
    rvol = indicators.compute_rvol(bars)
    cloud_sep = indicators.compute_cloud_sep_pct(closes, clouds)
    atr = indicators.compute_atr(bars, period=strategy.ATR_PERIOD)
    n = len(closes)
    base_ef = [
        (rvol[i] is not None and rsi[i] is not None and adx[i] is not None and cloud_sep[i] is not None
         and rvol[i] >= strategy.RVOL_MIN and strategy.RSI_MIN < rsi[i] < strategy.RSI_MAX
         and adx[i] >= strategy.ADX_MIN and cloud_sep[i] >= strategy.CLOUD_SEP_MIN)
        for i in range(n)
    ]
    return base_ef, atr


def run_variant(bars_by_ticker, alerts_by_ticker, gated):
    all_trades, per_ticker = [], {}
    for t, bars in bars_by_ticker.items():
        if len(bars) < 60:
            per_ticker[t] = engine.summarize([])
            continue
        base_ef, atr = precompute(bars)
        if gated:
            lookup = AlertLookup(alerts_by_ticker.get(t, []))
            ef = [base_ef[i] and (lookup.bullish_at(bars[i]["ts"]) is True) for i in range(len(bars))]
        else:
            ef = base_ef
        trades = engine.simulate(bars, risk_exit="stop", risk_pct=strategy.STOP_LOSS_PCT, take_profit_pct=None,
                                  entry_filter=ef, atr=atr, chandelier_mult=strategy.CHANDELIER_MULT)
        for tr in trades:
            tr["ticker"] = t
        all_trades.extend(trades)
        per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades


def print_summary(name, summary):
    wr = "{:.1f}%".format(summary["win_rate"] * 100) if summary["win_rate"] is not None else "n/a"
    pf = "{:.2f}".format(summary["profit_factor"]) if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    flag = "  [SMALL SAMPLE]" if summary["trades"] < MIN_TRADES_TO_TRUST else ""
    print("{:35s} trades={:4d}  win_rate={:>6s}  total_pnl=${:>10,.2f}  pf={}{}".format(
        name, summary["trades"], wr, summary["total_pnl"], pf, flag))


def main():
    wide, alerts = load()

    alert_min_ts = min(parse_iso_ts(a["ts_utc"]) for rows in alerts.values() for a in rows)
    alert_max_ts = max(parse_iso_ts(a["ts_utc"]) for rows in alerts.values() for a in rows)
    price_max_ts = max(b["ts"] for t in wide for b in wide[t][TIMEFRAME])
    overlap_start = alert_min_ts
    overlap_end = min(alert_max_ts, price_max_ts)

    print("=" * 100)
    print("TRADINGVIEW 1H TREND-FILTER STUDY")
    print("=" * 100)
    print("Alert window: {} to {}".format(
        datetime.datetime.fromtimestamp(alert_min_ts, tz=datetime.timezone.utc).isoformat(),
        datetime.datetime.fromtimestamp(alert_max_ts, tz=datetime.timezone.utc).isoformat()))
    print("Price data available through: {}".format(
        datetime.datetime.fromtimestamp(price_max_ts, tz=datetime.timezone.utc).isoformat()))
    print("Overlap window used for backtest: {} to {}".format(
        datetime.datetime.fromtimestamp(overlap_start, tz=datetime.timezone.utc).isoformat(),
        datetime.datetime.fromtimestamp(overlap_end, tz=datetime.timezone.utc).isoformat()))
    n_days = (overlap_end - overlap_start) / 86400
    print("That is {:.1f} calendar days -- a MUCH smaller sample than the 60-day studies elsewhere in this project.".format(n_days))

    bars_by_ticker = {}
    for t in wide:
        bars = [b for b in wide[t][TIMEFRAME] if overlap_start <= b["ts"] <= overlap_end]
        bars_by_ticker[t] = bars

    tickers_with_alerts = [t for t in wide if alerts.get(t)]
    print("\nTickers with usable alert coverage: {}/{}".format(len(tickers_with_alerts), len(wide)))
    print("Zero-alert tickers (never gate open): {}".format(sorted(t for t in wide if not alerts.get(t))))

    print("\n" + "-" * 100)
    ungated_summary, ungated_per_ticker, ungated_trades = run_variant(bars_by_ticker, alerts, gated=False)
    print_summary("Ungated (current deployed filter, same window)", ungated_summary)

    gated_summary, gated_per_ticker, gated_trades = run_variant(bars_by_ticker, alerts, gated=True)
    print_summary("+ 1h TradingView bullish-state gate", gated_summary)

    print("\nExit reason breakdown:")
    from collections import Counter
    print("  ungated:", dict(Counter(tr["reason"] for tr in ungated_trades)))
    print("  gated:  ", dict(Counter(tr["reason"] for tr in gated_trades)))

    print("\nPer-ticker (ungated vs gated), tickers with any trades in either:")
    print("{:8s} {:>16s} {:>16s}".format("ticker", "ungated_pnl(n)", "gated_pnl(n)"))
    for t in sorted(wide):
        u = ungated_per_ticker.get(t, engine.summarize([]))
        g = gated_per_ticker.get(t, engine.summarize([]))
        if u["trades"] == 0 and g["trades"] == 0:
            continue
        print("{:8s} {:>10,.2f}({:2d}) {:>10,.2f}({:2d})".format(t, u["total_pnl"], u["trades"], g["total_pnl"], g["trades"]))

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tradingview_1h_filter_study_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "overlap_window": {"start_utc": overlap_start, "end_utc": overlap_end, "days": n_days},
            "tickers_with_alerts": tickers_with_alerts,
            "ungated": {"summary": ungated_summary, "per_ticker": ungated_per_ticker},
            "gated": {"summary": gated_summary, "per_ticker": gated_per_ticker},
        }, f, indent=2)
    print("\nFull results written to " + out_path)


if __name__ == "__main__":
    main()
