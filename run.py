#!/usr/bin/env python3
"""
Main entry point for the Ripster EMA Cloud paper-trading monitor.

Each invocation:
  1. Loads persisted state (or starts fresh/"seed" on the very first run).
  2. Refreshes the earnings-date cache if it's stale.
  3. Fetches latest bars per ticker in the universe, evaluates the strategy
     against any newly-closed 1h candles, updates positions/trade log/P&L.
  4. Saves state and prints a chat-ready report.

Paper trading only -- no brokerage integration, no live orders.
"""

import datetime
import sys
import time

import data_source
import engine
import state as state_mod
import universe

REQUEST_PAUSE_SECONDS = 0.05


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

    all_events = []
    errors = []
    tickers = universe.UNIVERSE

    for i, ticker in enumerate(tickers):
        tstate = st["tickers"].setdefault(ticker, state_mod.default_ticker_state())
        try:
            tstate, events = engine.process_ticker(
                ticker, tstate, earnings_map.get(ticker), seed_mode=seed_mode
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
    return report


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
