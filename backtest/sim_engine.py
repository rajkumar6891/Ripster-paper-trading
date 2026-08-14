"""
Pure backtest simulator for the Ripster EMA Cloud strategy, reusing the
same EMA/signal math as the live monitor (strategy.py) but running over a
full historical bar series in one pass instead of incrementally.

Entry rule is fixed (bullish cloud signal, one position at a time, no
earnings filter -- see run_study.py for why). Exit is configurable so we
can compare variants: the always-on cloud bearish-cross exit, plus an
optional risk exit (fixed stop or trailing stop) and an optional take-
profit target.

Intrabar ambiguity: when a bar's low would trigger a stop/trailing/chandelier
exit AND its high would trigger a take-profit in the same bar, we
conservatively assume the downside exit hit first (worse case for the
trader), then take-profit, then the close-based cloud exit last.
"""

import strategy

NOTIONAL_PER_POSITION = 10_000.0


def simulate(bars, risk_exit=None, risk_pct=None, take_profit_pct=None, entry_filter=None,
             atr=None, atr_mult=None, chandelier_mult=None):
    """
    bars: chronological list of {ts, open, high, low, close, volume}.
    risk_exit: None | "stop" | "trailing" | "atr_stop".
    risk_pct: stop/trailing distance as a fraction (e.g. 0.05 for 5%), used
    for risk_exit in ("stop", "trailing").
    atr / atr_mult: for risk_exit == "atr_stop", atr is a list of ATR values
    aligned 1:1 with bars (see indicators.compute_atr) and atr_mult is the
    multiple of ATR-at-entry used as stop distance (stop = entry_price -
    atr_mult * atr[entry_index]), fixed for the life of the trade -- not
    trailing, matching the classic Turtle-style "entry - 2xATR" stop. A bar
    can't open a position under this mode if ATR isn't available yet.
    chandelier_mult: independent of risk_exit -- when set, adds an ATR
    trailing exit on top of whatever risk_exit is doing: stop = (highest
    high since entry) - chandelier_mult * ATR[i], recomputed every bar off
    the *current* bar's ATR (so it reacts to changing volatility, unlike
    the fixed-at-entry atr_stop) and ratcheted so it only ever moves up,
    never down. Meant to replace a hard take_profit_pct cap -- pass
    take_profit_pct=None when using this so winners aren't capped early.
    Requires `atr` to be provided; a bar can't open a position if ATR isn't
    available there yet.
    take_profit_pct: fraction above entry to take profit, or None.
    entry_filter: optional list of booleans aligned 1:1 with bars -- when
    given, a bar can only open a new position if entry_filter[i] is True in
    addition to the usual bullish cloud signal (see run_filter_study.py for
    how these are built from RSI/ADX/RVOL/etc).

    Returns a list of closed trades: {entry_ts, entry_price, exit_ts,
    exit_price, reason, pnl, return_pct}. Any position still open at the
    end of the series is force-closed at the last bar's close (marked
    "reason": "end-of-data") so every entry is accounted for.
    """
    closes = [b["close"] for b in bars]
    clouds = strategy.compute_clouds(closes)

    trades = []
    position = None  # {"entry_ts","entry_price","peak"}

    for i, bar in enumerate(bars):
        ema5, ema12, ema34, ema50 = clouds[5][i], clouds[12][i], clouds[34][i], clouds[50][i]
        close, low, high = bar["close"], bar["low"], bar["high"]

        if position is not None:
            entry_price = position["entry_price"]
            exit_price = None
            reason = None

            if risk_exit == "stop":
                stop_price = entry_price * (1 - risk_pct)
                if low <= stop_price:
                    exit_price, reason = stop_price, "stop"
            elif risk_exit == "trailing":
                position["peak"] = max(position["peak"], high)
                trail_price = position["peak"] * (1 - risk_pct)
                if low <= trail_price:
                    exit_price, reason = trail_price, "trailing"
            elif risk_exit == "atr_stop":
                stop_price = position["stop_price"]
                if low <= stop_price:
                    exit_price, reason = stop_price, "atr-stop"

            if exit_price is None and chandelier_mult is not None:
                position["peak"] = max(position["peak"], high)
                if atr[i] is not None:
                    candidate = position["peak"] - chandelier_mult * atr[i]
                    position["chand_stop"] = candidate if position["chand_stop"] is None \
                        else max(position["chand_stop"], candidate)
                if position["chand_stop"] is not None and low <= position["chand_stop"]:
                    exit_price, reason = position["chand_stop"], "chandelier"

            if exit_price is None and take_profit_pct is not None:
                tp_price = entry_price * (1 + take_profit_pct)
                if high >= tp_price:
                    exit_price, reason = tp_price, "take-profit"

            if (exit_price is None and ema5 is not None and ema12 is not None
                    and ema34 is not None and ema50 is not None
                    and strategy.bearish_exit_signal(close, ema5, ema12, ema34, ema50)):
                exit_price, reason = close, "cloud-exit"

            if exit_price is not None:
                shares = NOTIONAL_PER_POSITION / entry_price
                pnl = (exit_price - entry_price) * shares
                trade = {
                    "entry_ts": position["entry_ts"], "entry_price": entry_price,
                    "exit_ts": bar["ts"], "exit_price": exit_price, "reason": reason,
                    "pnl": pnl, "return_pct": (exit_price / entry_price - 1),
                }
                if "entry_atr" in position:
                    trade["entry_atr"] = position["entry_atr"]
                    trade["stop_pct"] = 1 - position["stop_price"] / entry_price
                trades.append(trade)
                position = None

        if position is None and i < len(bars) - 1:  # don't open brand-new positions on the last bar
            filter_ok = entry_filter is None or bool(entry_filter[i])
            atr_needed = risk_exit == "atr_stop" or chandelier_mult is not None
            atr_ok = not atr_needed or (atr is not None and atr[i] is not None)
            if (filter_ok and atr_ok and ema5 is not None and ema12 is not None and ema34 is not None and ema50 is not None
                    and strategy.bullish_entry_signal(close, ema5, ema12, ema34, ema50)):
                position = {"entry_ts": bar["ts"], "entry_price": close, "peak": close}
                if risk_exit == "atr_stop":
                    position["stop_price"] = close - atr_mult * atr[i]
                    position["entry_atr"] = atr[i]
                if chandelier_mult is not None:
                    position["chand_stop"] = close - chandelier_mult * atr[i]

    if position is not None:
        last = bars[-1]
        entry_price = position["entry_price"]
        shares = NOTIONAL_PER_POSITION / entry_price
        pnl = (last["close"] - entry_price) * shares
        trades.append({
            "entry_ts": position["entry_ts"], "entry_price": entry_price,
            "exit_ts": last["ts"], "exit_price": last["close"], "reason": "end-of-data",
            "pnl": pnl, "return_pct": (last["close"] / entry_price - 1),
        })

    return trades


def summarize(trades):
    n = len(trades)
    if n == 0:
        return {"trades": 0, "win_rate": None, "total_pnl": 0.0, "avg_pnl": None, "profit_factor": None}
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    return {
        "trades": n,
        "win_rate": len(wins) / n,
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / n,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else None),
    }
