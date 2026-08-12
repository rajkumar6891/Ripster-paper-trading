"""
Ripster EMA Cloud strategy (5/12 fast cloud vs 34/50 slow cloud), 10-minute
candles.

Pure signal/EMA math -- no I/O, no state persistence. See engine.py for the
stateful per-ticker evaluation that drives entries/exits off of these
signals, and data_source.py for how closed bars are fetched.

Exit rule and entry-quality filter are the winners from the timeframe/exit
/filter backtest study (paper_trading/backtest/): stop-3% + take-profit-15%
beat the original cloud-exit/5%-stop on 10-minute candles, and layering an
RVOL + RSI + ADX + cloud-separation filter on top cut trade count ~74%
while lifting win rate 36%->42% and profit factor 1.57->2.00 (at the cost
of lower *total* P&L per unit time, since far fewer trades are taken at
the same fixed position size -- see the study report for the full tradeoff).
"""

STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.15
EARNINGS_AVOID_DAYS = 2

FAST_PERIODS = (5, 12)
SLOW_PERIODS = (34, 50)

# Entry-quality filter thresholds (backtest-validated best "fewer, higher-
# conviction trades" combination: RVOL>=1.5x | RSI 50-70 | ADX>=25 | cloud
# separation >=0.3% of price).
RVOL_MIN = 1.5
RSI_MIN = 50
RSI_MAX = 70
ADX_MIN = 25
CLOUD_SEP_MIN = 0.003


def compute_ema(closes, period):
    """Standard EMA, seeded with the first close (pandas ewm adjust=False
    convention). Returns a list the same length as `closes`; entries are
    always defined once there is at least one close, they simply take a
    few dozen bars to converge for the slower periods."""
    if not closes:
        return []
    alpha = 2.0 / (period + 1)
    emas = [None] * len(closes)
    emas[0] = closes[0]
    for i in range(1, len(closes)):
        emas[i] = alpha * closes[i] + (1 - alpha) * emas[i - 1]
    return emas


def compute_clouds(closes):
    """Return {period: [ema values]} for all four EMA periods used."""
    return {p: compute_ema(closes, p) for p in (*FAST_PERIODS, *SLOW_PERIODS)}


def bullish_entry_signal(close, ema5, ema12, ema34, ema50):
    """Price and the entire fast cloud fully above the entire slow cloud."""
    fast_low = min(ema5, ema12)
    slow_high = max(ema34, ema50)
    return close > ema5 and close > ema12 and fast_low > slow_high


def bearish_exit_signal(close, ema5, ema12, ema34, ema50):
    """Mirror image: price and the entire fast cloud fully below the slow cloud."""
    fast_high = max(ema5, ema12)
    slow_low = min(ema34, ema50)
    return close < ema5 and close < ema12 and fast_high < slow_low


def stop_price(entry_price):
    """Resting-stop level: 5% below entry."""
    return entry_price * (1 - STOP_LOSS_PCT)


def stop_triggered(bar_low, entry_price):
    """Intrabar stop check -- uses the bar's low, not just its close, to
    behave like a resting stop order rather than a close-only check."""
    return bar_low <= stop_price(entry_price)


def take_profit_price(entry_price):
    """Resting take-profit level: 15% above entry."""
    return entry_price * (1 + TAKE_PROFIT_PCT)


def take_profit_triggered(bar_high, entry_price):
    """Intrabar take-profit check, using the bar's high like a resting
    limit order."""
    return bar_high >= take_profit_price(entry_price)


def entry_filter_ok(rvol, rsi, adx, cloud_sep_pct):
    """Entry-quality gate on top of the base cloud-crossover signal. Any
    missing (None) indicator -- e.g. not enough history yet -- fails the
    filter closed rather than open."""
    if None in (rvol, rsi, adx, cloud_sep_pct):
        return False
    return (rvol >= RVOL_MIN and RSI_MIN < rsi < RSI_MAX and adx >= ADX_MIN
            and cloud_sep_pct >= CLOUD_SEP_MIN)


def within_earnings_blackout(bar_date, next_earnings_date):
    """bar_date / next_earnings_date are datetime.date or None. True if
    opening a new position on bar_date would fall within EARNINGS_AVOID_DAYS
    calendar days of the ticker's next known earnings date."""
    if next_earnings_date is None:
        return False
    delta = (next_earnings_date - bar_date).days
    return 0 <= delta <= EARNINGS_AVOID_DAYS
