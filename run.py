#!/usr/bin/env python3
"""
Main entry point for the Ripster EMA Cloud paper-trading monitor.

Market data comes from Robinhood MCP tool calls (get_equity_historicals,
get_earnings_calendar) made by the *calling agent* -- this script cannot
call MCP tools itself, it only parses already-fetched JSON. The agent is
expected to:
  1. Call get_equity_historicals in batches (<=10 symbols/call) covering
     the tickers in universe.py, and dump the merged `data.results` array
     to a JSON file (default: market_data.json).
  2. Call get_earnings_calendar once for a forward window and dump its
     `data.results` array to a JSON file (default: earnings.json).
  3. Run this script pointed at those two files.

Each invocation:
  1. Loads persisted state (or starts fresh/"seed" on the very first run).
  2. Parses the two input files.
  3. Evaluates the strategy against any newly-closed 1h candles per ticker,
     updates positions/trade log/P&L.
  4. Saves state and prints a chat-ready report.

Paper trading only -- no brokerage integration, no live orders.
"""

import argparse
import datetime
import json
import sys

import data_source
import engine
import state as state_mod
import universe


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def run(market_data_path, earnings_path):
    st = state_mod.load_state()
    seed_mode = not st.get("seeded", False)

    bars_by_symbol = data_source.parse_historicals(load_json(market_data_path))
    earnings_map = data_source.parse_earnings_map(load_json(earnings_path))
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

    all_events = []
    errors = []
    tickers = universe.UNIVERSE

    for ticker in tickers:
        raw_bars = bars_by_symbol.get(ticker)
        if raw_bars is None:
            errors.append(f"{ticker}: missing from {market_data_path}")
            continue
        tstate = st["tickers"].setdefault(ticker, state_mod.default_ticker_state())
        try:
            tstate, events = engine.process_ticker(
                ticker, tstate, raw_bars, earnings_map.get(ticker), seed_mode=seed_mode, now_ts=now_ts
            )
            all_events.extend(events)
        except Exception as e:  # noqa: BLE001 - one bad ticker shouldn't kill the run
            errors.append(f"{ticker}: {e}")

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-data-file", default="market_data.json")
    parser.add_argument("--earnings-file", default="earnings.json")
    args = parser.parse_args()
    try:
        run(args.market_data_file, args.earnings_file)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL ERROR: {exc}", file=sys.stderr)
        raise
