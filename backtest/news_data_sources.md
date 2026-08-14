# Real-time news / analyst-action data sources — research (2026-08-13)

Scoped to: free or <$50/mo, real-time-enough for a Windows Task Scheduler
script hitting up to 173 tickers every 10-60 minutes, and ToS-clean enough
for an unattended bot. This is a **sourcing + design document only** --
nothing here is implemented in code, and (see Limitations below) none of
it can be backtested with what's available.

## Comparison table

| Source | Analyst upgrades/downgrades | Stock news | Free tier limit | Auth | ToS/reliability |
|---|---|---|---|---|---|
| **Finnhub** | Premium only (`/stock/upgrade-downgrade` requires paid plan) | **Free** (`/company-news`) | 60 calls/min | API key, free signup | Personal/non-commercial only per ToS -- fine for a personal paper-trading project, not for redistribution |
| **Yahoo Finance quoteSummary** (`upgradeDowngradeHistory`, `recommendationTrend` modules) | Undocumented, free if reachable | Undocumented | Unofficial, unclear | None historically, but now increasingly requires a cookie+crumb handshake | **Not recommended** -- as of 2025 this endpoint family returns 401/"Invalid Crumb" errors without a browser-session cookie+crumb; confirmed broken intermittently even for maintained libraries (yfinance issues #2495, #2533, #2404). Different from the `v8/finance/chart` endpoint this project already uses successfully, which remains open. Adding crumb-handling is real added fragility for an unattended script. |
| **Financial Modeling Prep (FMP)** | Ambiguous -- `/stable/upgrades-downgrades-consensus-bulk` and `/stable/grade-latest-news` exist, but FMP's pattern is to gate ratings/analyst datasets behind paid tiers; could not confirm free-tier access (their docs/pricing pages block automated fetches, 403/429) | Same ambiguity | 250 calls/day (free) | API key, free signup | **Needs manual verification** -- sign up for a free key and test `grade-latest-news` directly before relying on it. If gated, their Starter paid tier is ~$19-30/mo range, within budget. |
| **Alpha Vantage `NEWS_SENTIMENT`** | No | Yes, with actual NLP sentiment scores (bullish/neutral/bearish + relevance) | **25 requests/day total** | API key, free signup | Free tier is far too small for a 173-ticker universe -- would take ~a week to cycle through once. Only viable for a small hand-picked watchlist (~20 tickers), not the full universe. |
| **StockTwits public API** | No | No formal news, but message-stream + user-tagged sentiment as a crowd-sentiment/attention proxy | No official published limit; unauthenticated, historically lenient for read-only symbol streams | None | Free, no key needed, matches this project's existing "no paid API" pattern. Sentiment quality is noisy (only ~30-50% of messages are tagged bullish/bearish) -- useful as a supplementary attention/volume signal, not a primary catalyst source. |
| **MarketBeat ratings page** | Yes (web page, not an API) | No | N/A -- scraping | None | Scraping a ratings *page* (not an offered API/feed) for automated bot use sits in a ToS gray zone most sites don't welcome -- **not recommending** this route. |
| **Benzinga** | Yes, real-time, well-regarded | Yes | None -- paid only | N/A | Priced well above the ~$50/mo budget for this use case; skip. |

## Recommendation

**Primary: Finnhub `/company-news`** (free, confirmed, 60 calls/min).
173 tickers at 1 call/sec ≈ 3 minutes per run -- comfortably fits inside a
10-60 minute cadence with room to spare, same request-pacing pattern this
project already uses in `data_source.py` (just needs a longer pause than
the existing 0.05s, e.g. ~1.1s between calls to respect the free limit).

**Secondary/supplementary: StockTwits public symbol stream** (free, no
key) as a crowd-attention/sentiment proxy, cheap to add alongside Finnhub.

**Analyst upgrades/downgrades: no clean free option found.** Finnhub gates
it to paid; FMP is unconfirmed and needs a manual signup-and-test before
committing to it (recommend doing that test before building anything on
it); Yahoo's undocumented module is real but increasingly unreliable
without cookie/crumb handling. If real upgrade/downgrade data turns out to
matter, FMP's Starter tier (~$19-30/mo, confirm current price at signup)
is the most likely path within budget -- but verify free-tier access to
`grade-latest-news` first since it may already be sufficient.

## Design sketch (not implemented)

The user's framing was "as soon as these stocks hit our filters *and* the
market also behaves in our favor, enter" -- i.e. news/catalyst data as a
**confirming signal layered on top of the existing technical filter**, not
a replacement for it. Suggested design, for when/if built:

1. On each run, after the existing RVOL/RSI/ADX/cloud-sep filter + cloud-
   bullish signal already pass for a ticker (i.e. right before the entry
   would fire today), make one `Finnhub /company-news` call for that
   ticker only (not all 173 -- only the handful that already cleared the
   technical filter each run, which keeps request volume trivial).
2. Check headlines from the last ~24h for the ticker. Two reasonable
   designs, in order of recommended caution:
   - **Recommended first: log-only / observe mode.** Record whether fresh
     news existed at entry time and what it was, but don't gate the entry
     on it yet. Run this for several weeks of live paper trading to
     accumulate a real sample of "entries with fresh news" vs "entries
     without" and compare their actual win rates -- *then* decide whether
     to promote it to a gate, based on real forward data, not assumption.
   - **Only after observe-mode shows a real effect: promote to a soft
     boost or hard gate.** E.g. require at least one non-trivial headline
     in the last 24h (filters out totally catalyst-free technical
     breakouts, which the live-loser analysis suggests may be lower
     quality anyway), or simply log a "confidence" tier without blocking
     entries at all.
3. StockTwits message volume/sentiment for the same ticker could be added
   as a second, independent observe-mode signal in parallel.

Do **not** skip the observe-mode step and gate on this immediately --
see Limitations below for why.

## Limitations for the paper -- read before citing this

**This entire news/analyst-catalyst layer cannot be backtested with what's
available.** There is no affordable historical database of point-in-time
analyst upgrades/downgrades or news headlines that could be joined against
the existing 10-minute-bar historical price data the way RVOL/RSI/ADX/
ATR/cloud-separation were backtested earlier in this project. Providers
that do offer historical point-in-time news/ratings archives (e.g. Benzinga,
RavenPack, FMP's higher tiers) are priced well above this project's budget
and were out of scope for this research pass.

Practical consequence: **any result from adding this layer can only be
observed going forward in live paper trading**, starting from whenever
it's implemented -- it is not, and cannot be, part of the historical
backtest comparisons (chandelier exit, cloud-sep threshold, etc.) already
validated earlier in this project on ~60 days of historical bars. For the
paper, this should be described as a *live, forward-only, observational
extension* to the strategy, methodologically distinct from the backtested
technical-filter work -- not as something validated with the same rigor.
It would also need a meaningfully longer live observation window than the
technical filters did (those had ~60 days x 41 tickers of history to draw
on; a forward-only signal starts from zero and needs real trade volume
before its win-rate effect means anything statistically).
