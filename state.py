"""Local JSON persistence for positions/trade log/P&L."""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "state.json")


def default_ticker_state():
    return {
        "bars": [],
        "last_processed_ts": None,
        "position": None,
        "trade_log": [],
        "cumulative_realized_pnl": 0.0,
        "regular_market_price": None,
    }


def default_state():
    return {
        "seeded": False,
        "last_run_utc": None,
        "tickers": {},
    }


def load_state():
    if not os.path.exists(STATE_PATH):
        return default_state()
    with open(STATE_PATH, "r") as f:
        return json.load(f)


def save_state(state):
    tmp_path = STATE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_path, STATE_PATH)
