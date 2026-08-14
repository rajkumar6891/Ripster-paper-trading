"""
Regime + sector-VIX study for the win-rate-focused research pass:

1. Sector-differentiated VIX gate: block entries in strongly VIX-correlated
   sectors (semis, |corr| > 0.4 per vix_sector_correlation.py) when VIX is
   "spiking" (above its own 2h SMA); no gate for weakly-correlated sectors.
2. Top-down regime filters: require SPY itself, the stock's sector ETF, or
   both, to be in an uptrend (close > its own EMA50 on 10m bars) before
   taking the existing entry signal.
3. Combined best-of variants.
4. In-sample/out-of-sample check (first half vs second half of the ~60
   trading days) on the top 2-3 candidates, since this is for an academic
   paper and multiple-comparisons overfitting risk is real here.

All variants: existing RVOL/RSI/ADX/cloud-sep filter (current deployed
thresholds) + stop-3% + chandelier-8x exit, unchanged. Only the entry GATE
varies.

Data: raw_bars_wide.json (41 tickers), vix_bars.json (^VIX), sector_etfs.json
(SPY + 8 sector ETFs), same 60-day window throughout.
"""
import bisect
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strategy  # noqa: E402
import indicators  # noqa: E402
import sim_engine as engine  # noqa: E402

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
STOP_PCT = 0.03
CHANDELIER_MULT = 8.0
VIX_SMA_PERIOD = 24  # 2h of 5-min VIX bars
REGIME_EMA_PERIOD = 50

# Sector mapping for the 41-ticker wide set (best-effort; GOOGL/META are
# technically Communication Services (XLC), not fetched here, mapped to
# XLK as the closest available proxy -- noted as a simplification).
SECTOR_ETF = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK", "AMD": "XLK",
    "QCOM": "XLK", "MU": "XLK", "ADI": "XLK", "CRM": "XLK", "NOW": "XLK",
    "ADBE": "XLK", "PANW": "XLK", "GOOGL": "XLK", "META": "XLK",
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY",
    "JPM": "XLF", "BRK.B": "XLF", "V": "XLF", "MA": "XLF", "GS": "XLF", "MS": "XLF", "BAC": "XLF",
    "LLY": "XLV", "UNH": "XLV", "JNJ": "XLV", "ABBV": "XLV", "MRK": "XLV",
    "WMT": "XLP", "COST": "XLP", "PG": "XLP",
    "CAT": "XLI", "RTX": "XLI", "HON": "XLI", "BA": "XLI", "GE": "XLI",
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE",
}
SECTOR_LABEL = {
    "XLK": "Tech/Semis/Software", "XLY": "Consumer Disc.", "XLF": "Financials",
    "XLV": "Healthcare", "XLP": "Staples", "XLI": "Industrials", "XLE": "Energy",
}

# Semis: the sector shown to have strong (|corr|>0.4) negative VIX correlation
# in vix_sector_correlation.py (AMD -0.53, NVDA -0.53, ADI -0.52, MU -0.51,
# AVGO -0.50, QCOM -0.43). Everything else in the wide set had |corr|<0.4.
VIX_SENSITIVE = {"AMD", "NVDA", "ADI", "MU", "AVGO", "QCOM"}


class NearestLookup:
    """Nearest-bar-at-or-before-timestamp lookup, for aligning series that
    don't share an exact grid (VIX has an extended session; ETFs should
    mostly align with equities but this is defensive)."""

    def __init__(self, bars, value_fn):
        self.ts = [b["ts"] for b in bars]
        self.val = [value_fn(b) for b in bars]

    def at(self, t):
        idx = bisect.bisect_right(self.ts, t) - 1
        return self.val[idx] if idx >= 0 else None


def load_all():
    with open(os.path.join(DATA_DIR, "raw_bars_wide.json")) as f:
        wide = json.load(f)
    with open(os.path.join(DATA_DIR, "vix_bars.json")) as f:
        vix = json.load(f)
    with open(os.path.join(DATA_DIR, "sector_etfs.json")) as f:
        etfs = json.load(f)
    return wide, vix, etfs


def precompute_stock(bars):
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)
    return {
        "rsi": indicators.compute_rsi(closes),
        "adx": indicators.compute_adx(bars),
        "rvol": indicators.compute_rvol(bars),
        "cloud_sep": indicators.compute_cloud_sep_pct(closes, clouds),
        "atr": indicators.compute_atr(bars, period=strategy.ATR_PERIOD),
    }


def base_entry_filter(pre):
    n = len(pre["rsi"])
    return [strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i]) for i in range(n)]


def vix_not_spiking_lookup(vix5m):
    """True where VIX close is below its own 2h SMA ("not spiking" / calmer
    than its recent average) -- same construction as vix_study.py's
    falling_regime, exposed as a NearestLookup for reuse here."""
    closes = [b["close"] for b in vix5m]
    sma = [None] * len(closes)
    for i in range(len(closes)):
        if i + 1 >= VIX_SMA_PERIOD:
            sma[i] = sum(closes[i + 1 - VIX_SMA_PERIOD:i + 1]) / VIX_SMA_PERIOD
    flags = [(closes[i] < sma[i]) if sma[i] is not None else None for i in range(len(closes))]
    return _build_lookup(vix5m, flags)


def _build_lookup(bars, precomputed_vals):
    lk = NearestLookup.__new__(NearestLookup)
    lk.ts = [b["ts"] for b in bars]
    lk.val = precomputed_vals
    return lk


def etf_regime_lookup(bars10m):
    """True where the ETF's own close is above its EMA(50) on 10m bars."""
    closes = [b["close"] for b in bars10m]
    ema = strategy.compute_ema(closes, REGIME_EMA_PERIOD)
    flags = [(closes[i] > ema[i]) if ema[i] is not None else None for i in range(len(closes))]
    return _build_lookup(bars10m, flags)


def build_gated_filter(bars, base_ef, ticker, vix_lookup=None, vix_scope="sensitive",
                        spy_lookup=None, sector_lookup=None):
    n = len(base_ef)
    out = [False] * n
    for i in range(n):
        if not base_ef[i]:
            continue
        t = bars[i]["ts"]
        if vix_lookup is not None:
            applies = (ticker in VIX_SENSITIVE) if vix_scope == "sensitive" else True
            if applies:
                flag = vix_lookup.at(t)
                if flag is not True:  # None (no data yet) or False -> blocked
                    continue
        if spy_lookup is not None:
            if spy_lookup.at(t) is not True:
                continue
        if sector_lookup is not None:
            if sector_lookup.at(t) is not True:
                continue
        out[i] = True
    return out


def run_variant(bars_by_ticker, ef_by_ticker, atr_by_ticker):
    all_trades, per_ticker = [], {}
    for t, bars in bars_by_ticker.items():
        trades = engine.simulate(bars, risk_exit="stop", risk_pct=STOP_PCT, take_profit_pct=None,
                                  entry_filter=ef_by_ticker[t], atr=atr_by_ticker[t], chandelier_mult=CHANDELIER_MULT)
        for tr in trades:
            tr["ticker"] = t
        all_trades.extend(trades)
        per_ticker[t] = engine.summarize(trades)
    return engine.summarize(all_trades), per_ticker, all_trades


def print_summary(name, summary):
    wr = f"{summary['win_rate']*100:.1f}%" if summary["win_rate"] is not None else "n/a"
    pf = f"{summary['profit_factor']:.2f}" if isinstance(summary["profit_factor"], float) else str(summary["profit_factor"])
    print(f"{name:55s} trades={summary['trades']:4d}  win_rate={wr:>6s}  "
          f"total_pnl=${summary['total_pnl']:>11,.2f}  avg/trade=${(summary['avg_pnl'] or 0):>8,.2f}  pf={pf}")


def sector_breakdown(trades):
    by_sector = {}
    for tr in trades:
        sec = SECTOR_ETF.get(tr["ticker"], "?")
        by_sector.setdefault(sec, []).append(tr)
    out = {}
    for sec, trs in by_sector.items():
        out[sec] = engine.summarize(trs)
    return out


def main():
    wide, vix, etfs = load_all()
    bars_by_ticker = {t: wide[t]["10m"] for t in wide}
    pre_by_ticker = {t: precompute_stock(bars) for t, bars in bars_by_ticker.items()}
    base_ef_by_ticker = {t: base_entry_filter(pre_by_ticker[t]) for t in bars_by_ticker}
    atr_by_ticker = {t: pre_by_ticker[t]["atr"] for t in bars_by_ticker}

    vix_lookup = vix_not_spiking_lookup(vix["5m"])
    spy_lookup = etf_regime_lookup(etfs["SPY"]["10m"])
    sector_lookups = {etf: etf_regime_lookup(etfs[etf]["10m"]) for etf in set(SECTOR_ETF.values())}

    variants = {}

    # 0. baseline: no gate at all
    variants["baseline (no regime/VIX gate)"] = {t: base_ef_by_ticker[t] for t in bars_by_ticker}

    # 1. VIX gate on semis only
    variants["VIX-not-spiking gate, semis only"] = {
        t: build_gated_filter(bars_by_ticker[t], base_ef_by_ticker[t], t, vix_lookup=vix_lookup, vix_scope="sensitive")
        for t in bars_by_ticker
    }

    # 2. VIX gate on everyone (comparison / sanity check vs prior session's finding)
    variants["VIX-not-spiking gate, ALL tickers"] = {
        t: build_gated_filter(bars_by_ticker[t], base_ef_by_ticker[t], t, vix_lookup=vix_lookup, vix_scope="all")
        for t in bars_by_ticker
    }

    # 3. SPY regime only
    variants["SPY regime (close>EMA50) required"] = {
        t: build_gated_filter(bars_by_ticker[t], base_ef_by_ticker[t], t, spy_lookup=spy_lookup)
        for t in bars_by_ticker
    }

    # 4. sector regime only
    variants["Sector-ETF regime required"] = {
        t: build_gated_filter(bars_by_ticker[t], base_ef_by_ticker[t], t,
                               sector_lookup=sector_lookups.get(SECTOR_ETF.get(t)))
        for t in bars_by_ticker
    }

    # 5. SPY + sector regime
    variants["SPY + sector regime required"] = {
        t: build_gated_filter(bars_by_ticker[t], base_ef_by_ticker[t], t, spy_lookup=spy_lookup,
                               sector_lookup=sector_lookups.get(SECTOR_ETF.get(t)))
        for t in bars_by_ticker
    }

    # 6. combined: VIX-semis-gate + SPY + sector regime
    variants["VIX(semis) + SPY + sector regime"] = {
        t: build_gated_filter(bars_by_ticker[t], base_ef_by_ticker[t], t, vix_lookup=vix_lookup, vix_scope="sensitive",
                               spy_lookup=spy_lookup, sector_lookup=sector_lookups.get(SECTOR_ETF.get(t)))
        for t in bars_by_ticker
    }

    # 7. VIX-semis-gate + sector regime only (no SPY)
    variants["VIX(semis) + sector regime"] = {
        t: build_gated_filter(bars_by_ticker[t], base_ef_by_ticker[t], t, vix_lookup=vix_lookup, vix_scope="sensitive",
                               sector_lookup=sector_lookups.get(SECTOR_ETF.get(t)))
        for t in bars_by_ticker
    }

    print("=" * 110)
    print("REGIME / SECTOR-VIX GATE STUDY")
    print("=" * 110)

    all_results = {}
    for name, ef_map in variants.items():
        summary, per_ticker, trades = run_variant(bars_by_ticker, ef_map, atr_by_ticker)
        print_summary(name, summary)
        all_results[name] = {"summary": summary, "per_ticker": per_ticker, "trades": trades,
                              "sector_breakdown": sector_breakdown(trades)}

    print("\nExit reason breakdown, per variant:")
    for name, r in all_results.items():
        print(f"  {name}:", dict(Counter(t["reason"] for t in r["trades"])))

    print("\nSector breakdown, best-win-rate variant so far will be shown after ranking below.")
    ranked = sorted(all_results.items(), key=lambda kv: (kv[1]["summary"]["win_rate"] or 0), reverse=True)
    print("\nRanked by win rate:")
    for name, r in ranked:
        print_summary(f"  {name}", r["summary"])

    # In-sample / out-of-sample split on the top 3 win-rate variants
    # (excluding the no-gate baseline itself) -- first half vs second half
    # of each ticker's chronological bar history.
    print("\n" + "=" * 110)
    print("IN-SAMPLE / OUT-OF-SAMPLE CHECK (first half vs second half of the ~60-day window)")
    print("=" * 110)
    top_candidates = [name for name, _ in ranked if name != "baseline (no regime/VIX gate)"][:3]
    is_oos_results = {}
    for name in top_candidates:
        ef_map = variants[name]
        first_half_trades, second_half_trades = [], []
        for t, bars in bars_by_ticker.items():
            n = len(bars)
            mid_ts = bars[n // 2]["ts"]
            ef = ef_map[t]
            atr = atr_by_ticker[t]
            trades = engine.simulate(bars, risk_exit="stop", risk_pct=STOP_PCT, take_profit_pct=None,
                                      entry_filter=ef, atr=atr, chandelier_mult=CHANDELIER_MULT)
            for tr in trades:
                tr["ticker"] = t
                (first_half_trades if tr["entry_ts"] < mid_ts else second_half_trades).append(tr)
        s1, s2 = engine.summarize(first_half_trades), engine.summarize(second_half_trades)
        print(f"\n{name}:")
        print_summary("  first half", s1)
        print_summary("  second half", s2)
        is_oos_results[name] = {"first_half": s1, "second_half": s2}

    out_path = os.path.join(DATA_DIR, "regime_vix_study_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "variants": {name: {"summary": r["summary"], "per_ticker": r["per_ticker"],
                                 "sector_breakdown": r["sector_breakdown"]} for name, r in all_results.items()},
            "in_sample_out_of_sample": is_oos_results,
            "sector_map": SECTOR_ETF,
            "vix_sensitive_tickers": sorted(VIX_SENSITIVE),
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
