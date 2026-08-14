#!/usr/bin/env python3
"""
Main entry point for the Ripster EMA Cloud paper-trading monitor.

Each invocation:
  1. Loads persisted state (or starts fresh/"seed" on the very first run).
  2. Refreshes the earnings-date cache if it's stale.
  3. Fetches latest 5-minute bars per ticker from Yahoo Finance, aggregates
     to 10-minute candles, evaluates the strategy (RVOL/RSI/ADX/cloud-
     separation entry filter; stop-3% + ATR-chandelier trailing exit, no
     hard take-profit cap -- see strategy.py) against any newly-closed
     candles, updates positions/trade log/P&L.
  4. Saves state, appends the report to run_log.txt, prints it, and emails
     it (only when something actually happened -- see should_email below).

Runs locally only -- Yahoo Finance/Nasdaq are unreachable from a sandboxed
cloud environment, so this needs to run somewhere with open internet
access (Windows Task Scheduler, every 10 minutes during market hours).

Paper trading only -- no brokerage integration, no live orders.
"""

import datetime
import os
import sys
import time

from zoneinfo import ZoneInfo

import data_source
import email_sender
import engine
import state as state_mod
import universe

ET = ZoneInfo("America/New_York")

REQUEST_PAUSE_SECONDS = 0.05
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_log.txt")


def get_earnings_map():
    cached = state_mod.load_earnings_cache()
    if cached is not None:
        return cached
    earnings_map = data_source.fetch_upcoming_earnings_map()
    state_mod.save_earnings_cache(earnings_map)
    return earnings_map


def run():
    st = state_mod.load_state()
    seed_mode = not st.get("seeded", False)
    earnings_map = get_earnings_map()
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

    all_events = []
    errors = []
    tickers = universe.UNIVERSE
    fetch_range = "60d" if seed_mode else "5d"  # 60d = Yahoo's max for 5m bars

    for i, ticker in enumerate(tickers):
        tstate = st["tickers"].setdefault(ticker, state_mod.default_ticker_state())
        try:
            raw_5m = data_source.fetch_raw_bars(ticker, range_=fetch_range, interval="5m")
            raw_bars = data_source.aggregate_bars(raw_5m, factor=2)
            tstate, events = engine.process_ticker(
                ticker, tstate, raw_bars, earnings_map.get(ticker), seed_mode=seed_mode, now_ts=now_ts
            )
            all_events.extend(events)
        except Exception as e:  # noqa: BLE001 - one bad ticker shouldn't kill the run
            errors.append(f"{ticker}: {e}")
        if i < len(tickers) - 1:
            time.sleep(REQUEST_PAUSE_SECONDS)

    if seed_mode:
        st["seeded"] = True
    st["last_run_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state_mod.save_state(st)

    report = build_report(st, tickers, all_events, errors, seed_mode)
    print(report)
    append_log(report)

    entries = [e for e in all_events if e["type"] == "entry"]
    exits = [e for e in all_events if e["type"] == "exit"]
    if seed_mode or entries or exits:
        subject_stamp = datetime.datetime.now(ET).strftime("%Y-%m-%d %I:%M %p ET")
        email_result = email_sender.send_report_email(report, entries, seed_mode, subject_stamp)
        if email_result.get("sent"):
            print(f"Emailed report to {email_result['to']}.")
        elif email_result.get("reason"):
            print(f"Email not sent: {email_result['reason']}")
    else:
        print("No entries/exits this run -- skipping email (still logged above).")

    return report


def append_log(report):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n===== {stamp} =====\n{report}\n")


def build_report(st, tickers, all_events, errors, seed_mode):
    lines = []

    if seed_mode:
        lines.append(
            f"Baseline seeded: {len(tickers)} tickers loaded, all flat (no phantom trades)."
        )
        if errors:
            lines.append(f"{len(errors)} ticker(s) failed to seed: " + "; ".join(errors[:10]))
        return "\n".join(lines)

    entries = [e for e in all_events if e["type"] == "entry"]
    exits = [e for e in all_events if e["type"] == "exit"]

    open_positions = []
    cumulative_realized_pnl = 0.0
    for ticker in tickers:
        tstate = st["tickers"].get(ticker)
        if not tstate:
            continue
        cumulative_realized_pnl += tstate.get("cumulative_realized_pnl", 0.0)
        pos = tstate.get("position")
        if pos:
            price = tstate.get("regular_market_price") or pos["entry_price"]
            unrealized = (price - pos["entry_price"]) * pos["shares"]
            open_positions.append({
                "ticker": ticker, "entry_price": pos["entry_price"],
                "entry_time_et": pos["entry_time_et"], "price": price,
                "unrealized_pnl": unrealized,
            })

    if not entries and not exits and not open_positions:
        line = (
            f"No signals this run. Flat across all {len(tickers)} tickers. "
            f"Cumulative realized P&L: ${cumulative_realized_pnl:,.2f}."
        )
        if errors:
            line += f" ({len(errors)} ticker(s) had fetch errors.)"
        return line

    if entries or exits:
        lines.append("Trades this run:")
        for e in exits:
            lines.append(
                f"  EXIT  {e['ticker']:6s} @ ${e['price']:.2f}  ({e['reason']})  "
                f"{e['time_et']}  entry ${e['entry_price']:.2f} -> P&L ${e['pnl']:,.2f}"
            )
        for e in entries:
            lines.append(
                f"  ENTRY {e['ticker']:6s} @ ${e['price']:.2f}  {e['time_et']}  "
                f"shares {e['shares']:.4f}"
            )
            lines.append(
                f"        signal: RVOL {e['rvol']:.2f}x, RSI {e['rsi']:.0f}, "
                f"ADX {e['adx']:.1f}, cloud-sep {e['cloud_sep_pct']*100:.2f}%"
            )
    else:
        lines.append("No new entries/exits this run.")

    if open_positions:
        lines.append("")
        lines.append(f"Open positions ({len(open_positions)}):")
        for p in open_positions:
            lines.append(
                f"  {p['ticker']:6s} entry ${p['entry_price']:.2f} ({p['entry_time_et']})  "
                f"last ${p['price']:.2f}  unrealized P&L ${p['unrealized_pnl']:,.2f}"
            )
    else:
        lines.append("")
        lines.append("Open positions: none (flat).")

    lines.append("")
    lines.append(f"Cumulative realized P&L: ${cumulative_realized_pnl:,.2f}")

    if errors:
        lines.append(f"({len(errors)} ticker(s) had fetch errors: " + "; ".join(errors[:10]) + ")")

    return "\n".join(lines)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL ERROR: {exc}", file=sys.stderr)
        raise
