"""
Stateful per-ticker evaluation loop: merges freshly-fetched bars into
persisted history, evaluates the Ripster EMA Cloud strategy on any newly
closed bars, and updates positions / trade log / realized P&L.

Exit priority per bar (see strategy.py for the backtest history behind
these): flat 3% stop first (worst case for the trader), then the ATR
chandelier trailing exit (peak-since-entry minus 8xATR(14), ratcheted up
only), then the cloud-bearish-cross exit. No hard take-profit cap.
"""

import datetime
from zoneinfo import ZoneInfo

import data_source
import indicators
import strategy

ET = ZoneInfo("America/New_York")

MAX_BARS_KEPT = 400          # per-ticker rolling history cap
NOTIONAL_PER_POSITION = 10_000.0


def bar_et_date(ts):
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).astimezone(ET).date()


def bar_et_iso(ts):
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).astimezone(ET).isoformat()


def _merge_bars(existing, fresh_closed):
    by_ts = {b["ts"]: b for b in existing}
    for b in fresh_closed:
        by_ts[b["ts"]] = b
    merged = sorted(by_ts.values(), key=lambda b: b["ts"])
    if len(merged) > MAX_BARS_KEPT:
        merged = merged[-MAX_BARS_KEPT:]
    return merged


def _parse_earnings_date(date_str):
    if not date_str:
        return None
    return datetime.date.fromisoformat(date_str)


def process_ticker(ticker, tstate, raw_bars, next_earnings_date_str, seed_mode, now_ts=None):
    """Mutates and returns tstate; returns (tstate, events).

    raw_bars: already-fetched 10-minute bars for this ticker (list of
    {ts, open, high, low, close, volume} dicts). May include a
    still-forming trailing bar -- this function filters to fully-closed
    bars itself.
    """
    fresh_closed = data_source.closed_bars(raw_bars, now_ts=now_ts)

    existing_bars = tstate.get("bars", [])
    merged_bars = _merge_bars(existing_bars, fresh_closed)
    tstate["bars"] = merged_bars
    tstate["regular_market_price"] = raw_bars[-1]["close"] if raw_bars else tstate.get("regular_market_price")

    last_processed_ts = tstate.get("last_processed_ts")
    new_bars = [b for b in merged_bars if last_processed_ts is None or b["ts"] > last_processed_ts]

    events = []

    if seed_mode:
        if merged_bars:
            tstate["last_processed_ts"] = merged_bars[-1]["ts"]
        return tstate, events

    if not new_bars:
        return tstate, events

    closes_full = [b["close"] for b in merged_bars]
    clouds = strategy.compute_clouds(closes_full)
    rsi_full = indicators.compute_rsi(closes_full)
    adx_full = indicators.compute_adx(merged_bars)
    rvol_full = indicators.compute_rvol(merged_bars)
    cloud_sep_full = indicators.compute_cloud_sep_pct(closes_full, clouds)
    atr_full = indicators.compute_atr(merged_bars, period=strategy.ATR_PERIOD)
    ts_to_index = {b["ts"]: i for i, b in enumerate(merged_bars)}
    next_earnings_date = _parse_earnings_date(next_earnings_date_str)

    # Positions opened before the chandelier-exit change won't have "peak"
    # in their dict yet -- backfill it from real stored history (the true
    # high-water mark since entry) rather than starting cold from whatever
    # bar happens to be processed first after the upgrade.
    position = tstate.get("position")
    if position is not None and "peak" not in position:
        highs_since_entry = [b["high"] for b in merged_bars if b["ts"] >= position["entry_ts"]]
        position["peak"] = max(highs_since_entry, default=position["entry_price"])
        position["chand_stop"] = None

    for bar in new_bars:
        idx = ts_to_index[bar["ts"]]
        ema5 = clouds[5][idx]
        ema12 = clouds[12][idx]
        ema34 = clouds[34][idx]
        ema50 = clouds[50][idx]
        close = bar["close"]
        low = bar["low"]
        high = bar["high"]
        atr_here = atr_full[idx]
        position = tstate.get("position")

        if position is not None:
            entry_price = position["entry_price"]
            exit_price, reason = None, None

            if strategy.stop_triggered(low, entry_price):
                exit_price, reason = strategy.stop_price(entry_price), "stop-loss"
            else:
                position["peak"] = max(position.get("peak", entry_price), high)
                if atr_here is not None:
                    candidate = strategy.chandelier_candidate(position["peak"], atr_here)
                    position["chand_stop"] = candidate if position.get("chand_stop") is None \
                        else max(position["chand_stop"], candidate)
                chand_stop = position.get("chand_stop")
                if chand_stop is not None and low <= chand_stop:
                    exit_price, reason = chand_stop, "chandelier-exit"
                elif (ema5 is not None and ema12 is not None and ema34 is not None and ema50 is not None
                      and strategy.bearish_exit_signal(close, ema5, ema12, ema34, ema50)):
                    exit_price, reason = close, "signal"

            if exit_price is not None:
                pnl = (exit_price - entry_price) * position["shares"]
                events.append({
                    "ticker": ticker, "type": "exit", "reason": reason,
                    "price": exit_price, "ts": bar["ts"], "time_et": bar_et_iso(bar["ts"]),
                    "pnl": pnl, "entry_price": entry_price, "entry_time_et": position["entry_time_et"],
                })
                tstate["cumulative_realized_pnl"] = tstate.get("cumulative_realized_pnl", 0.0) + pnl
                tstate["trade_log"].append(events[-1])
                tstate["position"] = None

        if tstate.get("position") is None:
            rsi, adx, rvol, cloud_sep = rsi_full[idx], adx_full[idx], rvol_full[idx], cloud_sep_full[idx]
            if (atr_here is not None and ema5 is not None and ema12 is not None and ema34 is not None and ema50 is not None
                    and strategy.bullish_entry_signal(close, ema5, ema12, ema34, ema50)
                    and strategy.entry_filter_ok(rvol, rsi, adx, cloud_sep)):
                bar_date = bar_et_date(bar["ts"])
                if not strategy.within_earnings_blackout(bar_date, next_earnings_date):
                    shares = NOTIONAL_PER_POSITION / close
                    tstate["position"] = {
                        "entry_price": close,
                        "entry_ts": bar["ts"],
                        "entry_time_et": bar_et_iso(bar["ts"]),
                        "shares": shares,
                        "peak": close,
                        "chand_stop": strategy.chandelier_candidate(close, atr_here),
                    }
                    events.append({
                        "ticker": ticker, "type": "entry", "reason": "signal",
                        "price": close, "ts": bar["ts"], "time_et": bar_et_iso(bar["ts"]),
                        "shares": shares,
                        "rvol": rvol, "rsi": rsi, "adx": adx, "cloud_sep_pct": cloud_sep, "atr": atr_here,
                    })
                    tstate["trade_log"].append(events[-1])

        tstate["last_processed_ts"] = bar["ts"]

    return tstate, events
