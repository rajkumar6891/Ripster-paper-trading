"""Local JSON persistence for positions/trade log/P&L and the earnings-date cache."""

import datetime
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "state.json")
EARNINGS_CACHE_PATH = os.path.join(BASE_DIR, "earnings_cache.json")
EARNINGS_CACHE_MAX_AGE_HOURS = 20


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


def load_earnings_cache():
    if not os.path.exists(EARNINGS_CACHE_PATH):
        return None
    with open(EARNINGS_CACHE_PATH, "r") as f:
        cache = json.load(f)
    fetched_at = datetime.datetime.fromisoformat(cache["fetched_at_utc"])
    age_hours = (datetime.datetime.now(datetime.timezone.utc) - fetched_at).total_seconds() / 3600
    if age_hours > EARNINGS_CACHE_MAX_AGE_HOURS:
        return None
    return cache["earnings"]


def save_earnings_cache(earnings_map):
    cache = {
        "fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "earnings": earnings_map,
    }
    tmp_path = EARNINGS_CACHE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp_path, EARNINGS_CACHE_PATH)
