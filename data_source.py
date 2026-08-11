"""
Free, unauthenticated public market-data access.

- 1h OHLC candles: Yahoo Finance's public chart endpoint (no login, no key).
- Upcoming earnings dates: Nasdaq's public earnings-calendar endpoint (no
  login, no key). Yahoo's quoteSummary/calendarEvents endpoint now requires
  an authenticated crumb/cookie, so it's deliberately not used here.
"""

import json
import time
import urllib.request
import urllib.error
import datetime

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PaperTradingMonitor/1.0"

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"

# A bar's start-timestamp-to-next-bar gap must fall in this window (seconds)
# for the bar to count as a genuine 1-hour candle. This naturally drops the
# exchange's trailing sub-hour "stub" bar (e.g. the 15:30-16:00 ET leftover
# before the 4pm close) and the still-forming last bar of a fetch.
_HOUR_GAP_MIN = 3300  # 55 min
_HOUR_GAP_MAX = 3900  # 65 min


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


def fetch_chart(ticker, range_="5d", interval="60m"):
    """Fetch raw hourly bars (including any still-forming/stub trailing bar)
    plus the current regular-market price, in a single request."""
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
    meta = res.get("meta") or {}
    return {
        "bars": bars,
        "regular_market_price": meta.get("regularMarketPrice"),
        "meta": meta,
    }


def fetch_raw_bars(ticker, range_="5d", interval="60m"):
    return fetch_chart(ticker, range_=range_, interval=interval)["bars"]


def closed_hourly_bars(raw_bars):
    """Filter raw bars down to genuine, fully-closed 1-hour candles.

    A bar counts as closed and genuine only if a subsequent bar exists in
    the series roughly one hour later -- this simultaneously excludes the
    still-forming last bar and any sub-hour trailing stub bar.
    """
    closed = []
    for i in range(len(raw_bars) - 1):
        gap = raw_bars[i + 1]["ts"] - raw_bars[i]["ts"]
        if _HOUR_GAP_MIN <= gap <= _HOUR_GAP_MAX:
            closed.append(raw_bars[i])
    return closed


def fetch_closed_hourly_bars(ticker, range_="5d"):
    return closed_hourly_bars(fetch_raw_bars(ticker, range_=range_))


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
