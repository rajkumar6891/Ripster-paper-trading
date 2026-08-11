"""
Free, unauthenticated public market-data access -- Yahoo Finance's public
chart endpoint for 1h OHLC candles, Nasdaq's public earnings-calendar
endpoint for upcoming earnings dates. No login, no API key.

This module fetches directly over HTTP, which only works where outbound
internet access is unrestricted (i.e. run locally, not from a sandboxed
cloud routine with a locked-down network egress policy).
"""

import datetime
import json
import time
import urllib.error
import urllib.request

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PaperTradingMonitor/1.0"

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"

CLOSED_BAR_SECONDS = 3600  # a bar counts as closed once a full hour has
                            # elapsed since it opened (matches the spec's
                            # "a bar isn't finalized until a full hour has
                            # passed since it opened").


def _get_json(url, timeout=15, retries=3, backoff=1.5):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - broad by design, we retry+raise
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff ** attempt)
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last_err}")


def yahoo_symbol(ticker):
    """Yahoo uses a hyphen for share classes, e.g. BRK.B -> BRK-B."""
    return ticker.replace(".", "-")


def fetch_raw_bars(ticker, range_="5d", interval="60m"):
    """Fetch raw hourly bars (including any still-forming trailing bar) as
    a list of {ts, open, high, low, close, volume} dicts."""
    symbol = yahoo_symbol(ticker)
    url = CHART_URL.format(symbol=symbol) + f"?interval={interval}&range={range_}"
    data = _get_json(url)
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        err = (data.get("chart") or {}).get("error")
        raise RuntimeError(f"No chart result for {ticker}: {err}")
    res = result[0]
    timestamps = res.get("timestamp") or []
    quote = (res.get("indicators") or {}).get("quote", [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []

    bars = []
    for i, ts in enumerate(timestamps):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        if None in (o, h, l, c):
            continue
        bars.append({
            "ts": int(ts),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": int(vols[i]) if i < len(vols) and vols[i] is not None else None,
        })
    bars.sort(key=lambda b: b["ts"])
    return bars


def closed_hourly_bars(bars, now_ts=None):
    """Filter to bars whose full hour has elapsed as of now_ts (defaults to
    the current wall-clock time)."""
    if now_ts is None:
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    return [b for b in bars if now_ts >= b["ts"] + CLOSED_BAR_SECONDS]


def fetch_upcoming_earnings_map(lookahead_days=21):
    """Build {ticker: 'YYYY-MM-DD'} for the earliest upcoming known earnings
    date within the lookahead window, scanning Nasdaq's public per-day
    earnings calendar. Tickers with no confirmed date in the window are
    simply absent (treated as 'no known upcoming earnings')."""
    earnings = {}
    today = datetime.date.today()
    for i in range(lookahead_days):
        d = today + datetime.timedelta(days=i)
        url = f"{EARNINGS_URL}?date={d.isoformat()}"
        try:
            data = _get_json(url, retries=2)
        except Exception:
            continue
        rows = ((data or {}).get("data") or {}).get("rows") or []
        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if sym and sym not in earnings:
                earnings[sym] = d.isoformat()
    return earnings
