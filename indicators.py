"""
Entry-quality indicators used to filter the Ripster EMA Cloud signal:
RSI(14), ADX(14) (Wilder's method for both), rolling relative volume, and
EMA-cloud separation (as % of price). Same math as the backtest study that
validated these thresholds (see backtest/indicators.py) -- kept as a
separate copy here so the live monitor has no dependency on the backtest
tooling.

All return lists aligned 1:1 with the input bars; entries without enough
history are None.
"""


def compute_rsi(closes, period=14):
    n = len(closes)
    rsi = [None] * n
    if n <= period:
        return rsi
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains[i] = max(delta, 0.0)
        losses[i] = max(-delta, 0.0)

    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    rsi[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1 + avg_gain / avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1 + avg_gain / avg_loss)

    return rsi


def compute_adx(bars, period=14):
    n = len(bars)
    adx = [None] * n
    if n <= period * 2:
        return adx

    tr, plus_dm, minus_dm = [0.0] * n, [0.0] * n, [0.0] * n
    for i in range(1, n):
        high, low, prev_close = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        prev_high, prev_low = bars[i - 1]["high"], bars[i - 1]["low"]
        tr[i] = max(high - low, abs(high - prev_close), abs(low - prev_close))
        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    atr = sum(tr[1:period + 1]) / period
    smooth_plus = sum(plus_dm[1:period + 1]) / period
    smooth_minus = sum(minus_dm[1:period + 1]) / period

    def dx_at(atr_v, sp, sm):
        if atr_v == 0:
            return 0.0
        plus_di = 100 * sp / atr_v
        minus_di = 100 * sm / atr_v
        denom = plus_di + minus_di
        return 0.0 if denom == 0 else 100 * abs(plus_di - minus_di) / denom

    dx_list = [None] * n
    dx_list[period] = dx_at(atr, smooth_plus, smooth_minus)

    for i in range(period + 1, n):
        atr = (atr * (period - 1) + tr[i]) / period
        smooth_plus = (smooth_plus * (period - 1) + plus_dm[i]) / period
        smooth_minus = (smooth_minus * (period - 1) + minus_dm[i]) / period
        dx_list[i] = dx_at(atr, smooth_plus, smooth_minus)

    first_adx_idx = period * 2
    valid_dx = [d for d in dx_list[period:first_adx_idx + 1] if d is not None]
    if not valid_dx:
        return adx
    adx[first_adx_idx] = sum(valid_dx) / len(valid_dx)
    for i in range(first_adx_idx + 1, n):
        if dx_list[i] is None:
            continue
        adx[i] = (adx[i - 1] * (period - 1) + dx_list[i]) / period

    return adx


def compute_rvol(bars, period=20):
    n = len(bars)
    rvol = [None] * n
    vols = [b["volume"] or 0 for b in bars]
    for i in range(period, n):
        avg = sum(vols[i - period:i]) / period
        rvol[i] = (vols[i] / avg) if avg > 0 else None
    return rvol


def compute_cloud_sep_pct(closes, clouds):
    n = len(closes)
    sep = [None] * n
    for i in range(n):
        e5, e12, e34, e50 = clouds[5][i], clouds[12][i], clouds[34][i], clouds[50][i]
        if None in (e5, e12, e34, e50) or closes[i] == 0:
            continue
        fast_low, slow_high = min(e5, e12), max(e34, e50)
        sep[i] = (fast_low - slow_high) / closes[i]
    return sep
