#!/usr/bin/env python3
"""
Regression tests for the live strategy.py / engine.py exit logic (stop-3%
floor + ATR chandelier trailing exit + cloud-bearish signal exit, no hard
take-profit cap) added this session. Plain-assert, no pytest dependency --
run with `python test_engine.py`.

Covers:
  1. Exit priority: stop-loss wins over chandelier when both would trigger
     on the same bar (matches sim_engine.py's documented "worst case for
     the trader" convention).
  2. Chandelier exit fires at the correct price and only ratchets up
     (never down) as new bars arrive.
  3. Cloud-bearish "signal" exit still works when neither stop nor
     chandelier trigger.
  4. Backward-compat migration: a position dict from before this change
     (missing "peak"/"chand_stop") gets backfilled from real stored
     history instead of crashing or starting cold.
  5. New entries set peak/chand_stop correctly and log the ATR used.
  6. Equivalence check against the already-validated backtest simulator
     (sim_engine.py) on real historical data for several tickers -- the
     live per-bar loop and the batch backtest loop must produce the same
     closed trades given the same inputs.
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402
import indicators  # noqa: E402
import strategy  # noqa: E402
import state as state_mod  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest"))
import sim_engine  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def make_base_bars(n, ts0, step=600, price=100.0, half_range=0.5):
    """n bars of flat OHLC with a constant $1 high-low range (so ATR(14)
    converges to a known, easily-recomputed value) and steady volume."""
    bars = []
    for i in range(n):
        bars.append({
            "ts": ts0 + i * step,
            "open": price, "close": price,
            "high": price + half_range, "low": price - half_range,
            "volume": 1_000_000,
        })
    return bars


def test_stop_beats_chandelier():
    print("\n1. Stop-loss takes priority over chandelier on the same bar")
    base = make_base_bars(60, ts0=1_700_000_000)
    tstate = state_mod.default_ticker_state()
    tstate["bars"] = base
    tstate["last_processed_ts"] = base[-1]["ts"]
    tstate["position"] = {
        "entry_price": 100.0, "entry_ts": base[0]["ts"], "entry_time_et": "2023-11-14T09:30:00-05:00",
        "shares": 100.0, "peak": 120.0, "chand_stop": 110.0,  # well above the 3% stop level (97)
    }

    crash_bar = {"ts": base[-1]["ts"] + 600, "open": 100, "close": 90, "high": 100, "low": 80, "volume": 1_000_000}
    new_raw = base + [crash_bar]

    tstate2, events = engine.process_ticker("TEST", tstate, new_raw, None, seed_mode=False, now_ts=crash_bar["ts"] + 700)
    exits = [e for e in events if e["type"] == "exit"]
    check("exactly one exit event", len(exits) == 1, f"got {len(exits)}")
    if exits:
        check("exit reason is stop-loss", exits[0]["reason"] == "stop-loss", exits[0]["reason"])
        check("exit price is the 3% stop level", abs(exits[0]["price"] - strategy.stop_price(100.0)) < 1e-9)


def test_chandelier_exit_and_ratchet():
    print("\n2. Chandelier exit fires at the right level and only ratchets up")
    base = make_base_bars(60, ts0=1_700_000_000)
    tstate = state_mod.default_ticker_state()
    tstate["bars"] = base
    tstate["last_processed_ts"] = base[-1]["ts"]
    tstate["position"] = {
        "entry_price": 100.0, "entry_ts": base[0]["ts"], "entry_time_et": "2023-11-14T09:30:00-05:00",
        "shares": 100.0, "peak": 100.0, "chand_stop": None,
    }

    # bar A: price rallies to a new peak of 130 (high=131, low=129, close=130)
    bar_a = {"ts": base[-1]["ts"] + 600, "open": 130, "close": 130, "high": 131, "low": 129, "volume": 1_000_000}
    raw_a = base + [bar_a]
    tstate, events_a = engine.process_ticker("TEST", tstate, raw_a, None, seed_mode=False, now_ts=bar_a["ts"] + 700)
    check("no exit on the rally bar", not any(e["type"] == "exit" for e in events_a))
    atr_a = indicators.compute_atr(raw_a, period=strategy.ATR_PERIOD)[-1]
    expected_chand_a = strategy.chandelier_candidate(131.0, atr_a)  # peak = max(100, high=131)
    check("chand_stop matches hand-computed value after the rally",
          abs(tstate["position"]["chand_stop"] - expected_chand_a) < 1e-6,
          f"{tstate['position']['chand_stop']} vs {expected_chand_a}")
    chand_after_a = tstate["position"]["chand_stop"]

    # bar B: a small pullback that must NOT lower the ratcheted stop, and
    # must not itself trigger (low stays above the stop).
    bar_b = {"ts": bar_a["ts"] + 600, "open": 128, "close": 127, "high": 128, "low": max(chand_after_a + 1, 120), "volume": 1_000_000}
    raw_b = raw_a + [bar_b]
    tstate, events_b = engine.process_ticker("TEST", tstate, raw_b, None, seed_mode=False, now_ts=bar_b["ts"] + 700)
    check("no exit on the small pullback bar", not any(e["type"] == "exit" for e in events_b))
    check("chand_stop did not decrease after the pullback", tstate["position"]["chand_stop"] >= chand_after_a - 1e-9)

    # bar C: a deeper pullback that breaches the ratcheted stop but stays
    # well above the flat 3% stop (97), so this must exit as "chandelier-exit".
    stop_level = strategy.stop_price(100.0)
    breach_low = min(chand_after_a - 1, bar_b["low"] - 1)
    assert breach_low > stop_level, "test setup bug: breach level must stay above the flat stop"
    bar_c = {"ts": bar_b["ts"] + 600, "open": bar_b["low"], "close": breach_low, "high": bar_b["low"], "low": breach_low, "volume": 1_000_000}
    raw_c = raw_b + [bar_c]
    tstate, events_c = engine.process_ticker("TEST", tstate, raw_c, None, seed_mode=False, now_ts=bar_c["ts"] + 700)
    exits = [e for e in events_c if e["type"] == "exit"]
    check("exactly one exit on the breach bar", len(exits) == 1, f"got {len(exits)}")
    if exits:
        check("exit reason is chandelier-exit", exits[0]["reason"] == "chandelier-exit", exits[0]["reason"])
        check("exit price did not fall below the flat stop", exits[0]["price"] > stop_level)


def test_signal_exit_when_no_risk_exit_triggers():
    print("\n3. Cloud-bearish signal exit fires when neither stop nor chandelier trigger")
    # A gradual downtrend (0.1/bar, slow enough that the 3% stop from an
    # entry taken partway through isn't breached before the slow EMA cloud
    # actually flips bearish) so the fast cloud eventually crosses fully
    # below the slow cloud, with the position's protective levels set far
    # below price so they're never touched.
    ts0 = 1_700_000_000
    bars = []
    price = 100.0
    for i in range(120):
        price -= 0.1
        bars.append({"ts": ts0 + i * 600, "open": price, "close": price, "high": price + 0.3, "low": price - 0.3, "volume": 1_000_000})

    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)
    entry_idx = 90
    bearish_idx = next(i for i in range(entry_idx + 1, 120)
                        if clouds[5][i] is not None and clouds[50][i] is not None
                        and strategy.bearish_exit_signal(closes[i], clouds[5][i], clouds[12][i], clouds[34][i], clouds[50][i]))
    entry_price = closes[entry_idx]
    stop_lvl = strategy.stop_price(entry_price)
    assert closes[bearish_idx] > stop_lvl, \
        f"test setup bug: decline too fast, price {closes[bearish_idx]} already past stop {stop_lvl} by bar {bearish_idx}"

    tstate = state_mod.default_ticker_state()
    tstate["bars"] = bars[:entry_idx + 1]
    tstate["last_processed_ts"] = bars[entry_idx]["ts"]
    tstate["position"] = {
        "entry_price": entry_price, "entry_ts": bars[entry_idx]["ts"], "entry_time_et": "2023-11-14T09:30:00-05:00",
        "shares": 10.0, "peak": entry_price, "chand_stop": 1.0,  # absurdly low, never triggers
    }

    tstate, events = engine.process_ticker("TEST", tstate, bars[:bearish_idx + 1], None, seed_mode=False,
                                            now_ts=bars[bearish_idx]["ts"] + 700)
    exits = [e for e in events if e["type"] == "exit"]
    check("exactly one exit event", len(exits) == 1, f"got {len(exits)}")
    if exits:
        check("exit reason is signal", exits[0]["reason"] == "signal", exits[0]["reason"])


def test_migration_backfills_peak_from_history():
    print("\n4. Old-format open position (no peak/chand_stop) migrates from real history, doesn't crash")
    base = make_base_bars(60, ts0=1_700_000_000)  # flat ~$100, $1 true range -> ATR(14) converges to ~1.0
    # Overwrite one bar's high so there's a known true peak-since-entry,
    # modest enough (peak - 8*ATR ~= 104 - 8 = 96, below the flat ~$100
    # price) that an immediate migration doesn't itself look like a stale
    # position that should already be closed.
    entry_ts = base[10]["ts"]
    base[25]["high"] = 104.0  # the true peak since entry
    tstate = state_mod.default_ticker_state()
    tstate["bars"] = base
    tstate["last_processed_ts"] = base[-1]["ts"]
    tstate["position"] = {  # old-format position: no "peak", no "chand_stop"
        "entry_price": 100.0, "entry_ts": entry_ts, "entry_time_et": "2023-11-14T09:30:00-05:00",
        "shares": 10.0,
    }

    next_bar = {"ts": base[-1]["ts"] + 600, "open": 100, "close": 100, "high": 100.5, "low": 99.5, "volume": 1_000_000}
    try:
        tstate, events = engine.process_ticker("TEST", tstate, base + [next_bar], None, seed_mode=False,
                                                 now_ts=next_bar["ts"] + 700)
        check("no exception during migration", True)
    except Exception as e:  # noqa: BLE001
        check("no exception during migration", False, str(e))
        return
    pos = tstate.get("position")
    check("position still open (no false exit)", pos is not None, [e["reason"] for e in events if e["type"] == "exit"])
    if pos:
        check("peak backfilled from real stored history (104.0, not just entry/current)", pos["peak"] == 104.0, pos["peak"])
        check("chand_stop is now populated", pos.get("chand_stop") is not None)


def test_new_entry_sets_peak_and_chand_stop():
    print("\n5. New entries initialize peak=entry price and a valid chand_stop, log ATR")
    # Build a real bullish setup using actual market data so the entry
    # filter (RVOL/RSI/ADX/cloud-sep) genuinely passes, rather than faking it.
    wide_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest", "raw_bars_wide.json")
    with open(wide_path) as f:
        data = json.load(f)
    bars = data["MSFT"]["10m"]

    pre = precompute_for_sim(bars)
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)

    def bullish(i):
        e5, e12, e34, e50 = clouds[5][i], clouds[12][i], clouds[34][i], clouds[50][i]
        return None not in (e5, e12, e34, e50) and strategy.bullish_entry_signal(closes[i], e5, e12, e34, e50)

    ef = [strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i]) for i in range(len(bars))]
    entry_idx = next(i for i in range(len(bars)) if ef[i] and bullish(i) and pre["atr"][i] is not None)

    tstate = state_mod.default_ticker_state()
    tstate["bars"] = bars[:entry_idx]
    tstate["last_processed_ts"] = bars[entry_idx - 1]["ts"] if entry_idx > 0 else None

    tstate, events = engine.process_ticker("MSFT", tstate, bars[:entry_idx + 1], None, seed_mode=False,
                                            now_ts=bars[entry_idx]["ts"] + 700)
    entries = [e for e in events if e["type"] == "entry"]
    check("an entry event was produced at the expected bar", len(entries) == 1, f"got {len(entries)}")
    pos = tstate.get("position")
    check("position opened", pos is not None)
    if pos and entries:
        check("peak initialized to entry price", pos["peak"] == pos["entry_price"])
        check("chand_stop is below entry price (long trailing stop)", pos["chand_stop"] < pos["entry_price"])
        check("entry event logs the ATR used", entries[0].get("atr") is not None)


def precompute_for_sim(bars):
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)
    return {
        "rsi": indicators.compute_rsi(closes),
        "adx": indicators.compute_adx(bars),
        "rvol": indicators.compute_rvol(bars),
        "cloud_sep": indicators.compute_cloud_sep_pct(closes, clouds),
        "atr": indicators.compute_atr(bars, period=strategy.ATR_PERIOD),
    }


def test_matches_backtest_simulator_on_real_data():
    print("\n6. Live engine.py matches sim_engine.py (the validated backtest simulator) on real data")
    print("   (compared over a <=400-bar slice, i.e. within engine.py's MAX_BARS_KEPT rolling window --")
    print("   beyond that window, engine.py recomputes EMAs from a shorter history than a full-series")
    print("   backtest by design, a pre-existing characteristic unrelated to this session's changes.)")
    wide_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest", "raw_bars_wide.json")
    with open(wide_path) as f:
        data = json.load(f)

    for ticker in ["MSFT", "AAPL", "NVDA", "GOOGL", "AVGO"]:
        bars = data[ticker]["10m"][-min(400, engine.MAX_BARS_KEPT):]
        pre = precompute_for_sim(bars)
        ef = [strategy.entry_filter_ok(pre["rvol"][i], pre["rsi"][i], pre["adx"][i], pre["cloud_sep"][i]) for i in range(len(bars))]

        bt_trades = sim_engine.simulate(bars, risk_exit="stop", risk_pct=strategy.STOP_LOSS_PCT, take_profit_pct=None,
                                         entry_filter=ef, atr=pre["atr"], chandelier_mult=strategy.CHANDELIER_MULT)

        # Run the live engine over the whole history in one pass (now_ts far
        # past the last bar so everything counts as "closed").
        tstate = state_mod.default_ticker_state()
        tstate, events = engine.process_ticker(ticker, tstate, bars, None, seed_mode=False, now_ts=bars[-1]["ts"] + 10_000)
        live_exits = [e for e in events if e["type"] == "exit"]

        # sim_engine forbids opening a new position on the very last bar
        # (nothing to evaluate after it); live has no such restriction. So
        # compare all CLOSED trades except allow the live series to have at
        # most one extra trailing trade opened on the final bar.
        bt_closed = [t for t in bt_trades if t["reason"] != "end-of-data"]
        live_closed = live_exits

        n = min(len(bt_closed), len(live_closed))
        check(f"{ticker}: trade counts match (or differ by <=1 for the last-bar edge case)",
              abs(len(bt_closed) - len(live_closed)) <= 1,
              f"backtest={len(bt_closed)} live={len(live_closed)}")

        mismatches = []
        for i in range(n):
            bt, lv = bt_closed[i], live_closed[i]
            bt_entry_iso = engine.bar_et_iso(bt["entry_ts"])
            if bt_entry_iso != lv["entry_time_et"]:
                mismatches.append((i, "entry_ts", bt_entry_iso, lv["entry_time_et"]))
            reason_map = {"stop": "stop-loss", "chandelier": "chandelier-exit", "cloud-exit": "signal"}
            if reason_map.get(bt["reason"], bt["reason"]) != lv["reason"]:
                mismatches.append((i, "reason", bt["reason"], lv["reason"]))
            if abs(bt["pnl"] - lv["pnl"]) > 0.02:
                mismatches.append((i, "pnl", bt["pnl"], lv["pnl"]))
        check(f"{ticker}: first {n} trades match exactly (entry_ts, exit reason, pnl)",
              len(mismatches) == 0, f"{mismatches[:5]}")


def main():
    test_stop_beats_chandelier()
    test_chandelier_exit_and_ratchet()
    test_signal_exit_when_no_risk_exit_triggers()
    test_migration_backfills_peak_from_history()
    test_new_entry_sets_peak_and_chand_stop()
    test_matches_backtest_simulator_on_real_data()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
