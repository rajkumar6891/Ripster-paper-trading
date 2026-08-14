# TradingView 1-hour EMA cross alerts as a trend filter (2026-08-14)

Motivation: the user has real TradingView alert emails firing whenever a
ticker's 1-hour EMA34/EMA50 ("slow cloud") crosses, and asked whether
gating the deployed 10-minute entry signal on that real higher-timeframe
trend state -- "1 hour crossovers give an idea of trend in the underlying
stock, 10-min filters show current movement" -- improves results. This
mirrors the SPY/sector-ETF regime filter already tested and rejected in
`regime_vix_sector_research.md` sections 3 and 8-9, except using a real
per-stock curated signal instead of a generic index proxy.

## Data pulled

Parsed 106 alert emails across the 41-ticker backtest universe directly
from Gmail (`mcp__claude_ai_Gmail__search_threads`, one query per ticker:
`from:tradingview.com "on 60 close" "-- TICKER @" after:2026/07/29`,
subject line alone has ticker/direction/price/timestamp, no need to open
message bodies). Saved to `backtest/tradingview_1h_cross_alerts.json` via
`backtest/build_tradingview_alerts.py`.

**Critical constraint: this alert stream only goes back to 2026-07-29.**
Confirmed via Gmail date-range bisection (checked `before:2026/07/15`,
`before:2026/07/25`, `before:2026/07/28`, `before:2026/07/31`
progressively -- nothing exists before 2026-07-29/30). That is roughly
**15 calendar days**, dramatically shorter than the 60-day window used for
every other backtest in this project. This is the single most important
caveat on everything below.

**38 of the 41 tickers had at least one alert** in-window; CRM, NOW, and
WMT had zero (confirmed genuinely zero via a second, broadened non-phrase
Gmail query, not a search artifact -- these names just did not cross on
the 1h EMA34/50 in this window).

## Method

- Gate: at a given 10-min bar, the ticker's "current 1h state" is whichever
  direction (bullish/bearish) the most recent alert at-or-before that
  timestamp reported. No alert yet for that ticker -> state unknown ->
  entry blocked (fail-closed, same convention used elsewhere in this
  project for missing indicator data). Both bullish AND bearish alerts are
  used for this state-tracking -- bearish alerts are never traded directly,
  they only tell the gate when the bullish state has ended.
- Backtested on the exact overlap window between the alert stream and the
  available price cache: **2026-07-29 08:00 UTC to 2026-08-13 14:30 UTC
  (~15.3 calendar days)** -- both the gated and ungated variant are run on
  this identical restricted window, not compared against the older 60-day
  baseline numbers, so this is apples-to-apples.
- All other parameters are the exact currently-deployed live config:
  stop-3%, chandelier-8x ATR(14) trailing exit, no take-profit cap,
  RVOL>=1.5 / RSI in (50,70) / ADX>=25 / cloud-sep>=0.4%.

## Result

| Variant | Trades | Win rate | Total P&L | Profit factor |
|---|---|---|---|---|
| Ungated (deployed filter, same 15-day window) | 34 | 44.1% | $6,764 | 3.79 |
| + 1h TradingView bullish-state gate | 23 | 39.1% | $3,217 | 3.05 |

The gate cut trade count by a third (34 -> 23) and reduced win rate, total
P&L, and profit factor on every measure. This is directionally consistent
with the SPY/sector-ETF regime filter finding from the prior research pass
-- gating on a higher-timeframe trend signal, even a real curated one
instead of a self-computed proxy, removed more good trades than bad ones
in this sample.

## Sample-size honesty -- read before drawing conclusions

**Both trade counts (34 and 23) are small.** Per-ticker, almost every row
is 1-2 trades -- a single trade going the other way would meaningfully
move the aggregate numbers. This is NOT the same standard of evidence as
the 60-day/140-trade studies elsewhere in this project. Per the task's own
threshold, anything under ~15-20 trades should not be treated as
conclusive, and 23 trades is right at that edge. **Do not present this as
a confirmed rejection with the same confidence as the VIX-gate or
regime-gate findings** -- it is best read as "one more data point
consistent with the existing pattern (external trend gates hurt this
particular filter/exit combination in this dataset), not as independent
strong evidence on its own.

No in-sample/out-of-sample split was attempted on top of this (per the
task instructions) -- 15 days does not have enough trades to split further
and have either half mean anything.

## Recommendation

**Inconclusive-leaning-reject.** Directionally the same result as the
already-rejected SPY/sector regime gate, using an independent (real,
curated) data source instead of a self-computed proxy -- that consistency
across two different implementations of "gate on higher-timeframe trend"
is worth noting for the paper as a repeated pattern, not a coincidence of
one flawed study. But the sample here is too small to add much confidence
beyond what was already established. Do not deploy this gate. If the user
wants a more decisive answer, the alert stream needs several more weeks to
accumulate before a gated-vs-ungated comparison would have enough trades
to trust on its own.

## Files produced

- `backtest/build_tradingview_alerts.py` -- transcribes the Gmail-sourced
  alert data into `tradingview_1h_cross_alerts.json` (data snapshot, not a
  live fetcher -- re-run requires manually re-pulling from Gmail)
- `backtest/tradingview_1h_cross_alerts.json` -- 106 alerts, 41 tickers
- `backtest/run_tradingview_1h_filter_study.py` -- the gated/ungated
  backtest (`tradingview_1h_filter_study_results.json`)

