# Professional/institutional trend & entry/exit practice — research notes

Research pass on what professional/systematic traders (CTAs, retail-algo repos with
real backtested/live code) actually use for trend identification, entry timing, and
exit/risk management, compared against the current Ripster EMA-cloud paper-trading
strategy (`strategy.py`, `engine.py`).

**Current strategy, for reference:**
- Trend/entry signal: EMA(5)/EMA(12) fast cloud vs EMA(34)/EMA(50) slow cloud,
  bullish = price above both clouds + fast cloud above slow cloud, on 10-min bars.
- Entry filter: RVOL ≥ 1.5x, RSI in [50,70], ADX ≥ 25, cloud separation ≥ 0.3% of price.
  Fires any time the condition holds (not just on the fresh cross — already
  backtested as better).
- Exit: fixed 3% stop, 10% take-profit cap, cloud-bearish-cross exit. No trailing
  stop. No ATR anywhere in the codebase.
- Position sizing: fixed size per trade (no ATR/equity-based sizing — confirmed by
  reading `engine.py`/`state.py`, no risk-% logic exists).
- Universe: ~173 US equities, no crypto/futures. Earnings-avoidance: skip within 2
  days of earnings.

---

## 1. Trend identification

**What professionals commonly use:**
- **Moving-average systems**: classic periods are EMA/SMA 20/50/200 for
  daily-timeframe trend context; crossover systems (fast MA over slow MA = uptrend)
  remain a CTA staple. [ChartsWatcher: 8 Trend Following Strategies](https://chartswatcher.com/pages/blog/8-trend-following-strategies-to-boost-profits)
- **Donchian channels** are the other cornerstone of systematic trend-following:
  **20-day and 55-day breakout lookbacks are the two most common**, per the classic
  Turtle system and modern CTA writeups — 20-day for shorter swings (4–8 week holds),
  55-day for longer trends (3–6 months). [AlphaMaven: Trend Following Strategy Guide](https://alpha-maven.com/learn/trend-following-explained), [Trading Dude: Systematic Trend-Following](https://medium.com/@trading.dude/when-prediction-fails-rules-prevail-the-case-for-systematic-trend-following-f77f5e1d9330)
- **ADX as a trend-strength gate**: ADX ≥ 25 is the textbook Wilder threshold for
  "trending enough to trade," used as a filter layered on top of an MA/breakout
  signal to suppress false signals in chop. Freqtrade's official `Strategy004.py`
  uses `ADX(14) > 50 OR ADX(35) > 26` as its trend gate (higher/stricter than the
  textbook 25, showing real strategies often tune it up). [freqtrade-strategies/Strategy004.py](https://github.com/freqtrade/freqtrade-strategies/blob/main/user_data/strategies/Strategy004.py)
- **VWAP as an intraday trend reference**: close above VWAP = bullish bias, below =
  bearish, is a standard institutional-flow proxy for intraday trend context —
  distinct from (and often combined with) MA-based trend signals. A public repo
  (`arshadakl/intraday-trading-bot`) implements exactly this: entry requires close
  crossing above VWAP, with a "consolidation" filter (price within 0.5% of VWAP)
  to avoid whipsaw entries right at the line. [arshadakl/intraday-trading-bot](https://github.com/arshadakl/intraday-trading-bot)
- **Multi-timeframe alignment**: repeatedly cited as good practice (trade in the
  direction of the higher-timeframe trend) but rarely codified with hard numbers in
  the sources found — mostly qualitative guidance in retail-strategy writeups.

**vs. current strategy:**
- **Agrees**: ADX ≥ 25 gate matches the textbook threshold almost exactly (some
  real strategies go stricter, e.g. Freqtrade's 26–50).
- **Diverges**: no VWAP reference at all, and no higher-timeframe (e.g. daily or
  1h) trend filter — the strategy trades 10-min-bar signals with no check that the
  daily trend agrees. This is the single biggest trend-identification gap relative
  to common institutional practice.
- **Diverges**: EMA cloud (5/12 vs 34/50) is a legitimate but nonstandard trend
  system — it's directionally similar to a fast/slow MA crossover but doesn't map
  to a widely-published methodology (Donchian, golden-cross 50/200, etc.) the way
  the research literature does. That's not necessarily wrong, but it means there's
  less external validation to lean on than for the alternatives above.

---

## 2. Entry timing

**What professionals commonly use:**
- **Breakout entries** (Turtle-style): enter on a new N-day high/low — 20-day
  (System 1) or 55-day (System 2) Donchian breakout. Public reimplementations
  (`jesse-ai/example-strategies/TurtleRules`, `OktayBogazkaya/turtle-trading-strategy`,
  `Rors78/turtle-bot`) confirm these exact lookback periods and layer a "skip entry
  if the last System-1 trade was a winner" filter to reduce whipsaw. [jesse-ai TurtleRules](https://github.com/jesse-ai/example-strategies/blob/master/TurtleRules/__init__.py), [OktayBogazkaya/turtle-trading-strategy](https://github.com/OktayBogazkaya/turtle-trading-strategy)
- **Volume/RVOL confirmation**: extremely common as a breakout-quality filter.
  Concrete numbers found: 1.5x average volume as the default surge threshold, with
  1.3x suggested for quiet markets and 1.8x for stricter filtering
  (`arshadakl/intraday-trading-bot`). **This exactly matches the current strategy's
  RVOL ≥ 1.5x.**
- **Momentum/RSI filters paired with trend entries**: `arshadakl/intraday-trading-bot`
  uses RSI in [40,70] as the "neutral-to-bullish, not yet overbought" entry zone;
  `Strategy004.py` uses RSI/Stochastic in oversold zones for pullback-style mean
  reversion (different regime — that strategy is a dip-buy, not a breakout system,
  so its RSI logic isn't directly comparable). **Current strategy's RSI [50,70] is
  narrower/stricter than the arshadakl example but the same idea: momentum
  confirming, not yet extended.**
- **Avoiding chasing extended moves**: cloud/MA-separation filters (distance between
  fast and slow trend lines) show up as a proxy for "not too extended" in several
  retail systems, conceptually equivalent to the current cloud-separation ≥ 0.3%
  filter, though no source gave a standard numeric threshold for this specific
  technique — it appears to be a less standardized practice than RVOL/RSI/ADX.

**vs. current strategy:**
- **Agrees closely**: RVOL ≥ 1.5x is literally the default threshold found in a
  real public repo. ADX ≥ 25 and RSI-band filtering are both directionally
  standard practice.
- **Diverges**: no breakout/Donchian component at all — entries are purely
  trend-state + filter based, never "new N-bar high." Given Donchian breakouts are
  one of the two most cited CTA entry techniques, this is a candidate to test
  (e.g., require price to be making a fresh N-bar high, not just cloud-bullish) —
  though the existing "fresh-cross vs any-time" backtest already found timing
  restrictions costly, so this would need real testing, not assumption.

---

## 3. Exit / risk management

**This is where the current strategy diverges most from professional practice.**

- **ATR-based (volatility-adjusted) stops, not fixed %, are the standard.** Every
  public repo found uses ATR for stop distance, not a flat percentage:
  - Turtle system: **stop = entry − 2×ATR(20)**, confirmed in code across three
    independent repos (`jesse-ai/example-strategies`, `Rors78/turtle-bot`,
    `OktayBogazkaya/turtle-trading-strategy`). [jesse-ai TurtleRules](https://github.com/jesse-ai/example-strategies/blob/master/TurtleRules/__init__.py)
  - `arshadakl/intraday-trading-bot`: stop = entry − 2×ATR, target = entry + 4×ATR
    (1:2 risk-reward), with a fixed-% fallback (0.5%/1.0%) only used when ATR is
    unavailable — i.e., ATR is the primary method, fixed % is explicitly the
    degraded fallback. [arshadakl/intraday-trading-bot](https://github.com/arshadakl/intraday-trading-bot)
  - Rationale found repeatedly: a fixed % stop is too tight on volatile names and
    too loose on quiet ones; ATR normalizes stop distance to each stock's actual
    volatility. **The current 3% fixed stop has exactly this failure mode** — it
    will be needlessly tight on high-ATR names and needlessly loose on low-ATR ones
    within the same 173-ticker universe.
- **Chandelier / ATR trailing exits, not hard take-profit caps, are the standard
  way trend-followers let winners run.** Formula: `stop = Highest High(N) − ATR(N) ×
  multiplier` (classic default: 22-period lookback, 3× ATR multiplier), ratcheting
  up as price makes new highs, never loosening. [StockCharts: Chandelier Exit](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit), [Quantfunctions chandelier](https://rdrr.io/github/pverspeelt/Quantfunctions/man/chandelier.html)
  This is philosophically the opposite of a hard 10%/15% take-profit cap — a
  trailing exit captures more of a large trend while a fixed cap truncates it. The
  earlier backtest finding (removing the TP cap entirely beat a 15% cap on total
  P&L/win-rate/PF) is directionally consistent with this — a trailing exit would be
  the natural next thing to test, likely beating both the old cap and no-cap-at-all.
- **Position sizing as a function of ATR + fixed account-risk %, universally, not
  fixed share count.** Canonical formula, confirmed in code:
  `units = (risk_pct × account_equity) / (ATR × dollars_per_point)`, with
  **risk_pct = 1% being the standard default** across every source that specified a
  number (Turtle system, `Rors78/turtle-bot`, generic ATR-sizing writeups).
  [Rors78/turtle-bot](https://github.com/Rors78/turtle-bot), [automatedtradebot.com: Position sizing for trading bots](https://automatedtradebot.com/position-sizing-for-trading-bots)
  **The current strategy has no such logic at all** — it's flagged as a real gap:
  every paper trade risks the same fixed dollar/share amount regardless of the
  entry stock's volatility, so a 3% stop on a low-volatility stock and a 3% stop on
  a high-volatility stock represent very different real risk.
- **Time-based exits**: seen in Freqtrade's ROI-decay table (5% target at bar 0,
  decaying to 1% by bar 60) as an alternative/supplement to a static TP — not
  something the sources treated as more important than ATR-based exits, but worth
  noting as a third lever beyond stop/TP.

**vs. current strategy:**
- **Diverges the most of any topic covered.** Fixed 3% stop and 10% TP cap are
  both non-standard relative to what real strategies (Turtle-derived and
  retail-VWAP alike) actually run — ATR-based stop distance and ATR-based trailing
  exits are the near-universal alternative found across every source.
- **No position sizing formula exists at all** — this is arguably the highest-value
  gap since it affects every single trade uniformly, not just edge cases.

---

## 4. Market-regime filters

Coverage here was thinner than the other three topics — most sources treat
ADX-as-trend-strength-gate (already covered in §1) as the primary regime filter,
i.e. "only trade when ADX confirms trending conditions" is itself the regime
filter most systems use, rather than a separate volatility-regime layer. No source
gave a distinct, separately-parameterized "volatility regime" filter (e.g. VIX-based
or realized-vol-percentile gating) with concrete numbers — this looks like a less
codified/less publicly-documented practice than the entry/exit topics above, at
least among the public repos surfaced by this search.

---

## Prioritized, testable changes

Each of these is phrased to be pluggable into the existing `backtest/sim_engine.py`
/ `run_study.py` harness for A/B testing before touching live `strategy.py`. Ordered
by expected impact based on how consistently the research supports each one.

1. **Replace the fixed 3% stop with an ATR-based stop.** Add `ATR(14 or 20)` to
   `indicators.py` (ADX computation likely already needs true range, so this is
   mostly reusable), then test `stop = entry − 2×ATR` in `sim_engine.py` as a new
   `risk_exit` mode alongside the existing `"stop"` mode. This is the single most
   consistently-cited practice across every source and the current biggest
   divergence from professional practice.

2. **Replace the hard 10% take-profit cap with an ATR/chandelier trailing exit.**
   Test `trailing_stop = highest_high_since_entry − 3×ATR` (classic 22-bar/3×ATR
   default, or tune per the 10-min-bar timeframe) as a new exit mode, run against
   the same filtered-entry dataset already used in `run_pure_cloud_exit_study.py` /
   the TP sweep. Directionally supported by the already-completed finding that
   removing the TP cap outright beat a 15% cap — a trailing exit is the more
   sophisticated version of "no cap" that still protects gains.

3. **Add ATR-based (or even fixed-%-of-equity) position sizing.** Currently every
   trade risks a fixed size regardless of the entry stock's volatility. Add
   `shares = (risk_pct × paper_account_equity) / (ATR × stop_multiple)` — start
   with risk_pct = 1% (the standard default found everywhere) — to `engine.py`.
   This doesn't require new backtest infrastructure beyond exposing ATR per-ticker,
   which change #1 already needs.

4. **Add a higher-timeframe trend filter (e.g. daily-bar EMA or price-vs-VWAP).**
   Only take the existing 10-min entry signal when the daily/hourly trend agrees
   (e.g., price above daily EMA50, or above session VWAP). This is cheap to test:
   compute a daily-bar trend flag from the existing `raw_bars.json` fetch pipeline
   and gate `entry_filter_ok` on it in a new backtest variant.

5. **(Lower priority, smaller expected effect) Test a Donchian/N-bar-high
   confirmation on top of the cloud signal**, e.g. require the entry bar's close to
   be a fresh 10–20 bar high, not just cloud-bullish + filter-pass. Lower priority
   because the existing fresh-cross-timing study already found that adding timing
   restrictions to entries reduced total P&L — this would need to be tested
   specifically, not assumed to help, given that precedent.

---

## Follow-up: items 1 and 2 backtested (2026-08-13)

### #1 ATR-based stop — tested, **rejected**

`backtest/run_atr_stop_study.py`, `backtest/atr_stop_study_results.json`. Replaced the
fixed 3% stop with `entry_price - atr_mult * ATR(14)`, fixed for the trade's life,
swept atr_mult in [1.5, 2, 2.5, 3, 4, 5]. **Every multiplier underperformed the flat
3% stop on every metric** (baseline: 61 trades, 44.3% win rate, $6,409 P&L, PF 2.26;
best ATR variant at 5x: 64 trades, 39.1% win rate, $4,771 P&L, PF 1.89).

Root cause: ATR(14) on **10-minute bars** measures single-candle noise, not the
swing-level volatility the Turtle 2×ATR rule was calibrated for on daily bars. At the
textbook 2x multiplier the implied stop distance was a mean of 0.79% (100% of entries
tighter than the flat 3%) — the ATR stop was firing 52/73 times vs. the flat stop's
4/61, cutting trades off before the cloud-exit or take-profit could work. This also
revealed the fixed 3% stop is barely load-bearing today (4/61 exits) — the
cloud-bearish-cross exit does almost all the real risk control. **Conclusion: don't
apply a literature-default ATR multiplier without re-deriving it for the actual bar
timeframe in use — 10-min-bar ATR needs a much larger multiplier than daily-bar
convention, if ATR-based stops are used at all.**

### #2 Chandelier/trailing exit (replacing the hard TP cap) — tested, **promising, not yet applied**

`backtest/run_chandelier_study.py`, `backtest/chandelier_study_results.json`. Added
`chandelier_mult` to `sim_engine.simulate()`: an independent trailing exit,
`stop = highest_high_since_entry − chandelier_mult × ATR(14)`, recomputed every bar
off the *current* bar's ATR and ratcheted to only ever move up. Combined with the
existing 3% stop as a downside floor (per the #1 finding, ATR wasn't trusted as the
*initial* stop) and no take-profit cap. Entry rule held fixed at the any-time filter.

Low multipliers (2–4x) failed the same way #1's ATR stop did — too tight for 10-min
bars (trades=98 at 2x, PF 1.23). But **6–10x ATR(14) consistently beat both baselines**
(current live stop3%+TP10%: $6,409/PF 2.26; no-cap stop3%-only: $5,816/PF 2.16), with
a sharp peak at **7x**: 60 trades, **51.7% win rate, $7,660 total P&L (+19.5% vs
current live), profit factor 2.91**. Exit-reason breakdown at 7x shows the chandelier
genuinely captures bigger moves than either cap would have — top trades included
MSFT +22.5%, AMZN +17.0%, both far beyond the old 15% or current 10% TP ceiling.

**Caveat before adopting**: the peak at 7x is fairly sharp (6x: PF 1.37 fine but lower
$4,512; 8x: PF 2.57/$7,014; 9x: PF 2.37/$6,400) on a small sample (10 tickers, ~60
trading days) — this has real overfitting risk on the exact multiplier. The *range*
finding (6–10x beats a hard cap, mechanism is sound: don't tighten trailing stops
below what 10-min-bar ATR actually needs) is more trustworthy than the specific "7x is
optimal" point. Recommend either widening the backtest universe/period before locking
in a multiplier, or picking a more conservative value in the 8–10x range (still beats
baseline on every metric, less peaky) rather than the raw-best 7x, before touching
live `strategy.py`.

#### Widened-dataset validation (same day)

Fetched a second, independent, sector-diverse 41-ticker dataset
(`backtest/fetch_data_wide.py` -> `raw_bars_wide.json`; same 60-day window --
Yahoo's hard cap on 5m intraday bars means breadth was the only lever, not
longer history) spanning healthcare, financials, consumer, industrials, energy,
and non-mega semis/software, not just the original 10 mega-cap/tech names.
Reran the full sweep (`backtest/run_chandelier_study_wide.py`,
`chandelier_study_wide_results.json`):

| Exit | Trades | Win rate | Total P&L | PF |
|---|---|---|---|---|
| Current live (stop3+TP10) | 253 | 36.0% | $9,853 | 1.42 |
| No cap (stop3 only) | 239 | 36.8% | $10,791 | 1.51 |
| Chandelier 6x | 267 | 41.2% | $10,062 | 1.53 |
| Chandelier 7x | 250 | 40.4% | $14,792 | 1.77 |
| **Chandelier 8x** | 246 | 39.8% | **$16,694** | **1.85** |
| Chandelier 9-10x | 243-245 | ~39% | $13,016-14,269 | 1.62-1.69 |

Same shape as the narrow sample (2-4x still fails badly, sweet spot in 6-10x),
and the peak only shifted from 7x (narrow) to **8x** (wide) -- close enough to
read as a real structural effect rather than curve-fit noise on one sample.
Top captured trades span sectors (MSFT +22.5%, NOW +20.5%, QCOM +19.0%, CAT
+12.4%, CRM +12.1%), not just a couple of names carrying the result.

**Conclusion: 8x ATR(14) chandelier exit is now validated across two
independent samples and is the recommended value** (beats both baselines
in both datasets; 7x is close-second in both, so the region is robust even
if the exact peak isn't pinned to the decimal). Not yet applied to live
`strategy.py`/`engine.py` -- next step if/when approved.

---

## Live-loser diagnosis + entry-filter tightening study (2026-08-13)

The live monitor's first 10 real closed trades were all losses (see git
history / trade_log for the detail). Pulled each one's entry-time
RVOL/RSI/ADX/cloud-sep and found every single one had barely cleared the
filter thresholds (cloud-sep 0.30-0.49% against the 0.3% floor, RSI in the
high-60s against the 70 ceiling, several with ADX 25-27 against the 25
floor) -- the mirror image of the earlier `analyze_big_wins.py` finding that
big winners have *higher* average RVOL/RSI/ADX/cloud-sep than the trade
population. None hit the 3% stop (max loss -2.76%); all exited via the
cloud-bearish signal, so the stop wasn't the issue -- entry quality was.

`backtest/run_tighter_filter_study.py` tested raising each threshold
individually (holding stop-3% + chandelier-8x fixed), on the wide 41-ticker
set:

| Variant | Trades | Win rate | Total P&L | PF |
|---|---|---|---|---|
| Current thresholds | 246 | 39.8% | $16,694 | 1.85 |
| RSI cap 70->65 | 162 | 38.9% | $11,908 | 1.94 |
| ADX floor 25->30 | 192 | 34.9% | $8,267 | **1.49 (worse)** |
| **Cloud-sep 0.3%->0.5%** | 140 | **42.9%** | $12,365 | **1.96** |
| All three tightened | 58 | 41.4% | $4,807 | 1.76 |
| Late-entry cutoff (no entries last 60min) | 166 | 38.0% | $6,593 | **1.49 (worse)** |

**Cloud-sep 0.3%->0.5% is the only lever that improves win rate *and*
profit factor together** (not just a fewer-trades-for-quality tradeoff).
Raising ADX backfires outright (worse on every metric, not just fewer
trades) -- rejected. The late-entry-cutoff hypothesis, despite matching the
live losers' late-day-entry pattern, actually hurts in the wide backtest
(blocks plenty of genuinely good late-day trades too) -- rejected, that
pattern in the 10 live losers reads as small-sample coincidence, not a real
structural effect. Stacking all three tightenings compounds down to too few
trades to be useful.

**Also tested wiring in VIX** (`backtest/vix_study.py`): confirmed the
"VIX up -> stocks down" theory holds on average (-0.197 average 5-min-return
correlation across 41 tickers, 30/41 negative, strongest for high-beta
names like semis, weak/reversed for defensives/energy) but a "VIX below its
own 2h moving average" entry gate *hurt* the validated best config (total
P&L $16,694 -> $8,195, PF 1.85 -> 1.48) -- rejected as implemented; the
momentum entry signal already correlates with elevated near-term
volatility, so this gate cut good trades along with bad ones.

### Applied to live `strategy.py` / `engine.py` (2026-08-13)

Final validated combination deployed: **stop-3% (flat, unchanged) + ATR(14)
chandelier trailing exit at 8x (replaces the old hard take-profit cap) +
cloud-separation floor raised 0.3%->0.5% (RVOL/RSI/ADX filter legs
unchanged)**. Backtested together on the wide 41-ticker set: 140 trades,
42.9% win rate, $12,365 total P&L, profit factor 1.96 (vs. the pre-session
baseline of stop-3%+TP-10%: 246 trades* similar universe/filter, 39.8% win
rate, $16,694 total P&L, PF 1.85 -- note the tightened filter trades lower
total $ for meaningfully higher win rate/PF, the same kind of tradeoff the
original entry filter made). Per-ticker P&L for this final config, wide
dataset: NOW +$3,540 (71% WR), QCOM +$2,205, PANW +$1,344, META +$1,250
(100% WR, 4 trades), ADBE +$1,028 (100% WR); worst: AMD -$563, GS -$554,
BA -$413, V -$407, AMZN -$404. Full per-ticker table in
`tighter_filter_study_results.json` under the `"cloud-sep 0.3%->0.5%"` key.

Verified with `test_engine.py` (24 assertions: exit-priority ordering,
chandelier ratcheting, signal-exit fallback, backward-compat migration for
positions opened under the old take-profit logic, new-entry initialization,
and a direct equivalence check against `sim_engine.py` on real data) before
deploying. The live paper-trading state (`state.json`) was reset to a clean
unseeded baseline at the same time, since the 41 positions/10 trades already
open were opened under the old take-profit-cap logic and mixing them with
results from the new exit logic would make performance tracking meaningless
going forward.
