# Regime, sector-VIX, and win-rate research (2026-08-13, follow-up session)

Motivation: current deployed config wins 42.9% of trades. Goal for this pass was
specifically to raise win rate (not just total P&L) by testing (1) the user's
theorized VIX-sector relationship (proportional for semis, reversed for defense
and REITs) and (2) a top-down market-sentiment -> sector-sentiment -> stock
regime filter, and to do so with real overfitting discipline since this is
being written up for an academic paper.

**Headline result: none of the filters tested here beat the currently deployed
config's win rate, and the ones that looked promising in aggregate collapsed
under an in-sample/out-of-sample split. Recommendation is to NOT adopt any of
these — the current deployed config (stop-3% + chandelier-8x + RVOL/RSI/ADX/
cloud-sep filter, no regime/VIX gate) remains the best validated option.
IMPORTANT, added after the initial pass (see §7): the deployed baseline
itself shows the same first-half/second-half instability as the rejected
variants (55% WR / PF 3.14 first half vs. 31% WR / PF 1.21 second half) —
so "42.9% win rate" should be read as a blended average over a regime shift,
not a stable rate, for the paper.**

---

## 1. VIX-sector theory: partially confirmed for semis, refuted for defense/REITs

Fetched real REIT tickers (PLD, AMT, EQIX, O, SPG, PSA, WELL, DLR, VTR) and
pure-play defense tickers (LMT, NOC, GD, LHX, TDY) — neither was in the
existing 41-ticker wide dataset — and computed the same 5-minute-return VIX
correlation used in `vix_study.py` (`backtest/fetch_extra.py`,
`backtest/vix_sector_correlation.py`, results in
`vix_sector_correlation_results.json`):

| Sector | Tickers | Avg. VIX correlation | Range |
|---|---|---|---|
| Semis | AMD, NVDA, QCOM, MU, ADI, AVGO | **-0.502** | -0.43 to -0.53 |
| Defense | LMT, NOC, GD, LHX, TDY | -0.113 | -0.02 to -0.28 |
| REIT | PLD, AMT, EQIX, O, SPG, PSA, WELL, DLR, VTR | **-0.048** | -0.20 to +0.09 |

**Semis: confirmed, strongly.** Every semis ticker shows correlation between
-0.43 and -0.53 — VIX up reliably means semis down at the 5-minute level, the
strongest sector relationship found in either session's research.

**Defense: refuted as stated.** All 5 defense tickers are still *negative*
(same direction as semis, just weaker) — not reversed. TDY is the outlier at
-0.284; the other four cluster near zero (-0.02 to -0.11). There is no
sector where VIX-up predicts price-up for defense in this data.

**REITs: not confirmed as "reversed," best described as noise.** The 9 REIT
correlations split 5 negative / 4 positive, ranging -0.20 to +0.09, averaging
essentially zero (-0.048). This reads as "REITs have no reliable VIX
relationship at 5-minute granularity," not "REITs move opposite to VIX." The
theory that motivated this — REITs are rate-sensitive rather than
risk-sentiment-sensitive, so they shouldn't track the fear index the way
growth stocks do — is directionally sensible and *is* supported (REITs are
clearly decoupled from VIX vs. semis), but "decoupled" and "reversed" are
different claims, and the data only supports the former.

## 2. Sector-differentiated VIX gate: hurt, not helped

Built a gate that blocks entries in semis (the only sector with confirmed
strong correlation) when VIX is above its own 2-hour moving average
("spiking"), leaving all other sectors ungated (`run_regime_vix_study.py`).
Tested against the deployed baseline on the same 41-ticker set:

| Variant | Trades | Win rate | Total P&L | PF |
|---|---|---|---|---|
| **Baseline (no gate)** | 140 | **42.9%** | **$12,365** | **1.96** |
| VIX gate, semis only | 134 | 41.8% | $9,312 | 1.71 |
| VIX gate, all tickers | 107 | 42.1% | $4,447 | 1.38 |

Both VIX-gated variants come in *below* baseline on win rate, P&L, and profit
factor. The full-universe VIX gate replicates the prior session's finding
(gating on VIX hurts) even with the current tightened filter; restricting the
gate to just the confirmed-correlated sector (semis) softens the damage but
still doesn't help. Rejected.

## 3. Top-down regime filter (SPY -> sector ETF -> stock): also hurt, and unstable

Built SPY and 8 sector-ETF (XLK/XLY/XLF/XLV/XLP/XLI/XLE/XLRE) regime flags —
"in an uptrend" defined as close above its own EMA(50) on 10-minute bars,
mapped each of the 41 tickers to its sector ETF (best-effort; GOOGL/META
mapped to XLK as a proxy since Communication Services (XLC) wasn't fetched —
a known simplification). Gated the existing entry signal on SPY bullish,
sector bullish, or both:

| Variant | Trades | Win rate | Total P&L | PF |
|---|---|---|---|---|
| **Baseline (no gate)** | 140 | **42.9%** | **$12,365** | **1.96** |
| SPY regime required | 108 | 40.7% | $8,763 | 1.77 |
| Sector-ETF regime required | 119 | 41.2% | $9,042 | 1.78 |
| SPY + sector regime required | 98 | 40.8% | $7,926 | 1.77 |
| VIX(semis) + SPY + sector regime | 93 | 39.8% | $5,464 | 1.54 |

Every regime-gated variant reduces win rate, total P&L, and profit factor
versus the ungated baseline. Stacking more gates monotonically makes it
worse. The "top-down alignment should improve quality" intuition does not
hold in this dataset at this timeframe.

## 4. In-sample/out-of-sample check: the apparent quality is not stable over time

This is the more important finding methodologically. Splitting each ticker's
~60-day window at the midpoint (first ~30 trading days vs. last ~30) for the
three best-looking variants:

| Variant | First half | Second half |
|---|---|---|
| VIX gate, all tickers | 54 trades, **53.7%** WR, $5,932, PF 2.29 | 53 trades, **30.2%** WR, **-$1,485**, PF 0.79 |
| VIX gate, semis only | 67 trades, **52.2%** WR, $7,814, PF 2.41 | 67 trades, **31.3%** WR, $1,498, PF 1.20 |
| Sector-ETF regime required | 63 trades, **50.8%** WR, $9,616, PF 2.81 | 56 trades, **30.4%** WR, **-$575**, PF 0.91 |

Every one of these looked like a genuine win-rate improvement (50-54%) in the
first half of the window — and then **collapsed to 30-31% and flipped to
roughly breakeven-or-negative P&L in the second half**. This is a textbook
regime-dependency/overfitting signature: a filter that happens to align with
whatever the market was doing in the first ~30 days, not a structural edge.
None of these numbers would have looked like red flags from the aggregate
statistic alone — the aggregate "VIX gate, all tickers: 42.1% WR" looks
almost identical to baseline, but that average is hiding a first-half win and
a second-half loss netting out to a wash, plus regime-collapse in exactly the
scenario (raising win rate) this session was optimizing for. **This is the
main reason none of these filters are recommended**, independent of the
aggregate-level win rate not improving.

The baseline (undated) config wasn't itself re-verified IS/OOS in this pass
(it was validated in the prior session on the whole window, not split) — that
would be a reasonable next check before treating even the current deployed
config as fully temporally stable, given how unstable the sample turned out
to be for every variant tested here.

## 5. Best combined configuration

**None beat the baseline.** Per the task's own instruction not to manufacture
a positive result: the highest win rate of any tested variant was the
baseline itself (42.9%, no gate). Every additional filter — VIX-based,
regime-based, or combined — reduced win rate, P&L, and profit factor, and the
best-looking ones were shown by the IS/OOS split to be unstable rather than
genuinely predictive.

## 6. One observation for future work (not validated, flagged as such)

Sector breakdown of the baseline's 140 trades (`regime_vix_study_results.json`,
"baseline" variant):

| Sector | Trades | Win rate | Total P&L | PF |
|---|---|---|---|---|
| Tech/Semis/Software | 68 | 48.5% | $10,606 | 2.68 |
| Industrials | 24 | 45.8% | $1,486 | 1.74 |
| Healthcare | 15 | 46.7% | $1,200 | 2.13 |
| Consumer Disc. | 13 | 38.5% | $128 | 1.11 |
| Financials | 10 | 30.0% | -$321 | 0.75 |
| Energy | 7 | 14.3% | -$274 | 0.49 |
| Staples | 3 | 0.0% | -$461 | 0.00 |

Tech/Semis/Software alone carries 48.5% win rate and essentially all the
profit (68 of 140 trades, $10,606 of $12,365 total P&L). Energy, Financials,
and Staples all lose money. A "trade tech/healthcare/industrials only, skip
energy/financials/staples" sector filter is tempting given this table — but
Energy (n=7) and Staples (n=3) are far too small a sample to trust, and given
how badly the VIX/regime gates degraded out-of-sample in this exact dataset,
this table should be treated as a hypothesis to test with an IS/OOS split and
a larger sample, not a filter to deploy. Flagged for a future session, not
implemented here.

## 7. Follow-up: the deployed baseline itself is NOT temporally stable either

Section 4 flagged that the baseline had never been checked IS/OOS — only the
candidate filters had. Closed that gap (`run_baseline_is_oos.py`,
`baseline_is_oos_results.json`), splitting each ticker's window at the
midpoint and running the exact deployed config (stop-3% + chandelier-8x +
RVOL/RSI/ADX/cloud-sep>=0.5%, no regime/VIX gate) on each half:

| Window | Trades | Win rate | Total P&L | PF |
|---|---|---|---|---|
| Full 60 days (the number quoted as "deployed performance") | 140 | 42.9% | $12,365 | 1.96 |
| First ~30 trading days | 71 | **54.9%** | $11,253 | **3.14** |
| Second ~30 trading days | 67 | **31.3%** | $1,519 | **1.21** |

**This is the same collapse pattern as every rejected filter variant in
Section 4 — and it's larger.** The deployed config's headline 42.9% win rate
is not a stable number; it's an average of a strong first-half regime
(54.9% WR, PF 3.14) and a much weaker second-half regime (31.3% WR, PF
1.21, barely above breakeven). Practically all of the strategy's edge in
this sample came from the first 30 days.

**Implication for the paper and for the live deployment**: the 42.9%/1.96
figures already reported as "the deployed config's backtest performance"
should not be presented as a stable expectation without this caveat. The
honest range to report is "42.9% blended over this sample, with a 55%/31%
split across the two halves" — and the live paper-trading run that just
started should be read with the explicit possibility that it's entering in
a "second-half-like" regime, where a 31% win rate and near-breakeven PF is
just as plausible as the aggregate 42.9%. This isn't a reason to distrust
the chandelier-exit/cloud-sep findings specifically (those improvements
were relative, and nothing in this pass suggests the *old* config would
have been more stable) — but it is a reason to caveat any absolute win-rate
number from this dataset heavily, and to treat the live paper-trading data
now accumulating as the real test, not the backtest number.

## 8. Follow-up: is the instability parameter-overfitting, or regime-dependence?

Prompted directly by the user asking whether the deployed filters (chandelier
mult=8x, cloud-sep=0.5%) are themselves overfit, given §7's IS/OOS collapse.
These are different claims and worth separating (`run_parameter_stability_check.py`,
`parameter_stability_results.json`): re-swept both parameters *independently*
on the first half and second half of the window, to see whether 8x/0.5% are
only "best" on the full sample (overfitting) or remain best/near-best even
when a genuinely different sub-sample is used to pick them (not overfitting
in the classic sense -- more likely a real, if regime-conditional, effect).

**Chandelier multiplier: stable, not overfit.** 8x is independently the best
choice on the first half alone (54.9% WR, PF 3.14) -- not just on the full
window it was originally chosen on. In the second half, 6x edges out 8x
only marginally (33.3% vs 31.3% WR), and **every multiplier from 6x-12x is
stuck in the 30-33% win-rate range** in the second half regardless of choice.
No chandelier value rescues second-half performance, which is the signature
of a market-conditions effect, not a mistuned parameter.

**Cloud-sep threshold: mildly sensitive, and a gap in the original sweep.**
0.5% is best on the first half (matches what was deployed). On the second
half, 0.4% would have done modestly better (36.3% WR / $6,232 vs 0.5%'s
31.3% WR / $1,519) -- a real but modest difference. More importantly: **on
the full window, 0.4% actually beats the deployed 0.5% on both total P&L
($17,012 vs $12,365) and profit factor (2.05 vs 1.96)**, only losing on raw
win rate (41.3% vs 42.9%). The original filter-tightening study
(`run_tighter_filter_study.py`) only tested 0.3% vs 0.5%, skipping 0.4% --
a real gap in that sweep's grid, not fatal, but worth correcting.

**Conclusion**: the deployed parameters are not classically overfit -- the
chandelier multiplier in particular remains the right choice when selected
from an independent sub-sample, and the second-half weakness persists
across every parameter value tested, pointing to the market itself being
less favorable for a trend-following system in that window (likely
choppier/less-trending) rather than to curve-fitting. The cloud-sep
threshold is the one place with a legitimate, if modest, overfitting-
adjacent concern, and 0.4% deserves a look as a possible improvement on
0.5% independent of the regime question.

## 9. Follow-up: proper 0.4% cloud-sep backtest (chandelier re-swept, IS/OOS checked)

§8 only checked cloud-sep=0.4% with chandelier held fixed at the value tuned
for 0.5%. Redid this properly (`run_cloud_sep_04_study.py`,
`cloud_sep_04_study_results.json`): re-swept the chandelier multiplier AT
cloud-sep=0.4% first (8x remained best there too, no change needed there),
then ran the same full/first-half/second-half IS/OOS check applied to the
deployed config, for a fair side-by-side:

| Config | Window | Trades | Win rate | Total P&L | PF |
|---|---|---|---|---|---|
| **Deployed (8x, 0.5%)** | Full | 140 | **42.9%** | $12,365 | 1.96 |
| | First half | 71 | 54.9% | $11,253 | 3.14 |
| | Second half | 67 | 31.3% | $1,519 | 1.21 |
| **Candidate (8x, 0.4%)** | Full | 189 | 41.3% | **$17,012** | **2.05** |
| | First half | 95 | 46.3% | $10,526 | 2.37 |
| | Second half | 91 | 36.3% | **$6,232** | **1.77** |

**This is a genuine tradeoff, not a strict win either direction.** 0.4%
trades more (189 vs 140), makes meaningfully more money ($17,012 vs
$12,365, +38%), and is *more stable* across the two halves — its
win-rate swing is 46.3%->36.3% (10pts) versus the deployed config's much
sharper 54.9%->31.3% (23.6pts), and its second-half P&L is 4x higher
($6,232 vs $1,519) with a meaningfully better profit factor (1.77 vs 1.21,
i.e. still solidly profitable in the weak regime vs. barely breakeven).
But its **blended win rate is lower** (41.3% vs 42.9%) — because the wider
filter takes more marginal trades that slightly dilute the average, even
though the extra trades are net profitable in aggregate.

**Framing for the paper**: if the objective is strictly "maximize the
single win-rate number," 0.5% remains ahead by 1.6pts. If the objective is
"maximize risk-adjusted profitability and behave more consistently across
regimes" — arguably the more defensible objective for a live strategy —
0.4% is the better choice on every other metric, including being
demonstrably less regime-fragile, which is exactly the property §7/§8
found lacking in the deployed config. This is presented as a decision
point, not resolved here — the user should choose which objective the
paper (and the live deployment) optimizes for.

## Methodology notes / limitations for the paper

- Universe: 41 tickers (mega-cap-tech-heavy but sector-diversified), ~60
  trading days (2026-05-15 to 2026-08-11), 10-minute bars — small by
  quantitative-finance standards; every finding here should be read as
  "on this sample," not as a general market law.
- VIX correlation computed at 5-minute-return granularity, aligned by exact
  timestamp match on Yahoo's raw feed; VIX's extended trading session
  required a nearest-bar-at-or-before lookup for gating, not exact-grid
  alignment, elsewhere in this study.
- Sector-ETF mapping is best-effort (GOOGL/META approximated as XLK).
- Regime signal (close > EMA50) is a simple, standard trend definition, not
  tuned/swept — a swept version would carry even more overfitting risk on
  a sample already this small, so it was deliberately not attempted.
- The IS/OOS split is a single 50/50 chronological split, not k-fold or
  walk-forward — a real academic treatment would want a more rigorous
  cross-validation scheme; this was a first-pass sanity check and it was
  enough to reject every candidate, which is itself the useful result.

## Files produced

- `backtest/fetch_extra.py` — fetches REIT/defense tickers + sector ETFs
  (`raw_bars_extra.json`, `sector_etfs.json`, both gitignored, regenerate
  with internet access)
- `backtest/vix_sector_correlation.py` — REIT/defense/semis correlation
  check (`vix_sector_correlation_results.json`)
- `backtest/run_regime_vix_study.py` — the gate backtests + IS/OOS split
  (`regime_vix_study_results.json`)
- `backtest/run_baseline_is_oos.py` — the same IS/OOS split applied to the
  deployed baseline itself (`baseline_is_oos_results.json`), added as a
  follow-up (§7) once the candidate-filter collapse pattern made it clear
  the baseline needed the same check
