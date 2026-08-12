import json

data = json.load(open("report_data.json"))

TF_ORDER = ["10m", "30m", "60m"]
TF_META = {
    "10m": {"label": "10-minute", "accent": "var(--accent-10m)", "accent-soft": "var(--accent-10m-soft)"},
    "30m": {"label": "30-minute", "accent": "var(--accent-30m)", "accent-soft": "var(--accent-30m-soft)"},
    "60m": {"label": "1-hour", "accent": "var(--accent-60m)", "accent-soft": "var(--accent-60m-soft)"},
}


def bar_row(label, trades, win_rate, pnl, pnl_raw, pf, bar_pct, positive, accent, extra_class=""):
    sign_class = "pos" if positive else "neg"
    return f"""
      <div class="bar-row {extra_class}">
        <div class="bar-row-label">{label}</div>
        <div class="bar-track">
          <div class="bar-fill {sign_class}" style="width:{bar_pct}%; --bar-accent:{accent};"></div>
        </div>
        <div class="bar-stats">
          <span class="stat-pnl {sign_class}">{pnl}</span>
          <span class="stat-sub">{trades} trades &middot; {win_rate} win &middot; PF {pf}</span>
        </div>
      </div>"""


# ---- Timeframe comparison bars ----
tf_bars = ""
for row in data["timeframe_rows"]:
    meta = TF_META[row["tf"]]
    tf_bars += bar_row(meta["label"], row["trades"], row["win_rate"], row["pnl"], row["pnl_raw"],
                        row["pf"], row["bar_pct"], row["positive"], meta["accent"])

# ---- Exit variant tables (top 6 + baseline marker, rest in <details>) ----
variant_sections = ""
for tf in TF_ORDER:
    meta = TF_META[tf]
    rows = data["variant_tables"][tf]
    top6 = rows[:6]
    rest = rows[6:]

    top_html = ""
    for r in top6:
        cls = "winner" if r == rows[0] else ("baseline-marker" if r["is_baseline"] else "")
        badge = '<span class="pill pill-win">best</span>' if r == rows[0] else (
            '<span class="pill pill-base">baseline</span>' if r["is_baseline"] else "")
        top_html += bar_row(f'{r["label"]} {badge}', r["trades"], r["win_rate"], r["pnl"], r["pnl_raw"],
                             r["pf"], r["bar_pct"], r["positive"], meta["accent"], extra_class=cls)

    rest_rows = ""
    for r in rest:
        cls = "baseline-marker" if r["is_baseline"] else ""
        badge = '<span class="pill pill-base">baseline</span>' if r["is_baseline"] else ""
        rest_rows += f"""
          <tr class="{cls}">
            <td>{r['label']} {badge}</td>
            <td class="num">{r['trades']}</td>
            <td class="num">{r['win_rate']}</td>
            <td class="num {'pos' if r['positive'] else 'neg'}">{r['pnl']}</td>
            <td class="num">{r['pf']}</td>
          </tr>"""

    details_html = ""
    if rest_rows:
        details_html = f"""
        <details class="more-variants">
          <summary>Show all {len(rows)} variants</summary>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Variant</th><th class="num">Trades</th><th class="num">Win %</th><th class="num">Total P&amp;L</th><th class="num">Profit factor</th></tr></thead>
              <tbody>{rest_rows}</tbody>
            </table>
          </div>
        </details>"""

    hl = data["headline"]["best_variants"][tf]
    variant_sections += f"""
      <div class="tf-panel">
        <div class="tf-panel-head">
          <h3><span class="dot" style="background:{meta['accent']}"></span>{meta['label']}</h3>
          <p class="tf-panel-sub">Best: <strong>{hl['label']}</strong> &mdash; {hl['pnl']} total
            (<span class="pos">+{hl['uplift']}</span> vs. baseline)</p>
        </div>
        <div class="bars">{top_html}</div>
        {details_html}
      </div>"""

# ---- Per-ticker table ----
ticker_rows_html = ""
for r in data["ticker_rows"]:
    cells = ""
    for tf in TF_ORDER:
        c = r[tf]
        cls = "pos" if c["positive"] else "neg"
        cells += f'<td class="num {cls}">{c["pnl"]}<span class="cell-sub">{c["trades"]}tr &middot; {c["win_rate"]}</span></td>'
    ticker_rows_html += f'<tr><td class="ticker-cell">{r["ticker"]}</td>{cells}</tr>'

headline = data["headline"]

html = f"""<!doctype html>
<title>Ripster EMA Cloud &mdash; Timeframe &amp; Exit Study</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  .viz-root {{
    color-scheme: light;
    --bg:              #f9f9f7;
    --surface:         #fcfcfb;
    --surface-raised:  #ffffff;
    --text-primary:    #0b0b0b;
    --text-secondary:  #52514e;
    --text-muted:      #898781;
    --border:          rgba(11,11,11,0.10);
    --grid:            #e1e0d9;
    --accent-10m:      #2a78d6;
    --accent-10m-soft: #cde2fb;
    --accent-30m:      #eb6834;
    --accent-30m-soft: #fbdccb;
    --accent-60m:      #1baf7a;
    --accent-60m-soft: #c7ecdd;
    --good:            #0ca30c;
    --critical:        #d03b3b;
    --good-soft:       #d9f2d9;
    --critical-soft:   #f7d9d9;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --bg:              #0d0d0d;
      --surface:         #1a1a19;
      --surface-raised:  #212120;
      --text-primary:    #ffffff;
      --text-secondary:  #c3c2b7;
      --text-muted:      #898781;
      --border:          rgba(255,255,255,0.10);
      --grid:            #2c2c2a;
      --accent-10m:      #3987e5;
      --accent-10m-soft: #163156;
      --accent-30m:      #d95926;
      --accent-30m-soft: #4a2313;
      --accent-60m:      #199e70;
      --accent-60m-soft: #103c2b;
      --good:            #0ca30c;
      --critical:        #e66767;
      --good-soft:       #0f2e10;
      --critical-soft:   #3a1414;
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --bg:              #0d0d0d;
    --surface:         #1a1a19;
    --surface-raised:  #212120;
    --text-primary:    #ffffff;
    --text-secondary:  #c3c2b7;
    --text-muted:      #898781;
    --border:          rgba(255,255,255,0.10);
    --grid:            #2c2c2a;
    --accent-10m:      #3987e5;
    --accent-10m-soft: #163156;
    --accent-30m:      #d95926;
    --accent-30m-soft: #4a2313;
    --accent-60m:      #199e70;
    --accent-60m-soft: #103c2b;
    --good:            #0ca30c;
    --critical:        #e66767;
    --good-soft:       #0f2e10;
    --critical-soft:   #3a1414;
  }}

  .viz-root {{
    background: var(--bg);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", ui-sans-serif, sans-serif;
    line-height: 1.5;
    padding: 0 20px 80px;
  }}
  .viz-root * {{ box-sizing: border-box; }}
  .num, .stat-pnl, .cell-sub, table td, table th, .bar-stats {{
    font-family: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", monospace;
    font-variant-numeric: tabular-nums;
  }}

  .page {{ max-width: 900px; margin: 0 auto; }}

  header.hero {{
    padding: 56px 0 32px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
  }}
  .eyebrow {{
    font-family: ui-monospace, "SF Mono", monospace;
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin: 0 0 12px;
  }}
  h1 {{
    font-size: 32px;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 0 0 12px;
    text-wrap: balance;
  }}
  .hero-sub {{
    font-size: 15px;
    color: var(--text-secondary);
    max-width: 62ch;
    margin: 0;
  }}

  h2 {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.005em;
    margin: 0 0 4px;
  }}
  .section-sub {{
    color: var(--text-secondary);
    font-size: 14px;
    margin: 0 0 20px;
  }}
  section {{ margin-bottom: 48px; }}

  /* Stat tiles */
  .tiles {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-bottom: 48px;
  }}
  .tile {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 18px 16px;
  }}
  .tile-label {{
    font-size: 12px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 0 0 8px;
  }}
  .tile-value {{
    font-size: 24px;
    font-weight: 700;
    font-family: ui-monospace, "SF Mono", monospace;
    margin: 0 0 4px;
  }}
  .tile-detail {{
    font-size: 13px;
    color: var(--text-secondary);
    margin: 0;
  }}

  /* Bar rows */
  .bars {{ display: flex; flex-direction: column; gap: 10px; }}
  .bar-row {{
    display: grid;
    grid-template-columns: 200px 1fr 220px;
    align-items: center;
    gap: 14px;
    padding: 10px 12px;
    border-radius: 8px;
  }}
  .bar-row.winner {{ background: var(--surface); border: 1px solid var(--border); }}
  .bar-row.baseline-marker:not(.winner) {{ background: color-mix(in srgb, var(--surface) 60%, transparent); }}
  .bar-row-label {{
    font-size: 13px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .bar-track {{
    height: 10px;
    background: var(--grid);
    border-radius: 5px;
    overflow: hidden;
  }}
  .bar-fill {{
    height: 100%;
    border-radius: 5px;
    background: var(--bar-accent);
  }}
  .bar-fill.neg {{ background: var(--critical); }}
  .bar-stats {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    font-size: 13px;
  }}
  .stat-pnl {{ font-weight: 700; font-size: 14px; }}
  .stat-pnl.pos, .pos {{ color: var(--good); }}
  .stat-pnl.neg, .neg {{ color: var(--critical); }}
  .stat-sub {{
    color: var(--text-muted);
    font-size: 11.5px;
  }}

  .pill {{
    display: inline-block;
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 1px 7px;
    border-radius: 100px;
    margin-left: 6px;
    vertical-align: middle;
  }}
  .pill-win {{ background: var(--good-soft); color: var(--good); }}
  .pill-base {{ background: var(--grid); color: var(--text-secondary); }}

  /* Timeframe panels for exit optimization */
  .tf-panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 20px 16px;
    margin-bottom: 16px;
  }}
  .tf-panel-head {{ margin-bottom: 16px; }}
  .tf-panel h3 {{
    font-size: 15px;
    font-weight: 700;
    margin: 0 0 4px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
  .tf-panel-sub {{ font-size: 13px; color: var(--text-secondary); margin: 0; }}
  .tf-panel .bar-row {{ grid-template-columns: 240px 1fr 200px; }}

  .more-variants {{ margin-top: 12px; }}
  .more-variants summary {{
    cursor: pointer;
    font-size: 13px;
    color: var(--text-secondary);
    padding: 8px 4px;
  }}
  .more-variants summary:hover {{ color: var(--text-primary); }}

  /* Tables */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    font-weight: 600;
  }}
  td.num, th.num {{ text-align: right; }}
  tr.baseline-marker td {{ background: color-mix(in srgb, var(--grid) 40%, transparent); }}

  .ticker-table td, .ticker-table th {{ text-align: right; }}
  .ticker-table td:first-child, .ticker-table th:first-child {{ text-align: left; }}
  .ticker-cell {{ font-weight: 700; font-family: ui-monospace, "SF Mono", monospace; }}
  .cell-sub {{
    display: block;
    font-size: 10.5px;
    color: var(--text-muted);
    font-weight: 400;
  }}

  footer {{
    border-top: 1px solid var(--border);
    padding-top: 24px;
    color: var(--text-muted);
    font-size: 12.5px;
    line-height: 1.7;
  }}
  footer h4 {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin: 0 0 8px; }}
  footer ul {{ margin: 0 0 16px; padding-left: 18px; }}

  @media (max-width: 640px) {{
    .tiles {{ grid-template-columns: 1fr; }}
    .bar-row {{ grid-template-columns: 1fr; row-gap: 6px; }}
    .bar-stats {{ align-items: flex-start; flex-direction: row; gap: 10px; }}
    .tf-panel .bar-row {{ grid-template-columns: 1fr; }}
  }}
</style>

<div class="viz-root">
<div class="page">

  <header class="hero">
    <p class="eyebrow">Ripster EMA Cloud &middot; Strategy Research</p>
    <h1>Which candle timeframe wins &mdash; and how to exit it</h1>
    <p class="hero-sub">Backtest of the same 5/12 vs 34/50 EMA cloud strategy across 10-minute, 30-minute,
      and 1-hour candles, on the 10 largest S&amp;P&nbsp;500 names by market cap, over the trailing 60 trading
      days (Yahoo Finance's max intraday history window). 18 exit variants tested per timeframe to find the
      best risk-exit / take-profit combination.</p>
  </header>

  <div class="tiles">
    <div class="tile">
      <p class="tile-label">Best timeframe (baseline exit)</p>
      <p class="tile-value" style="color:var(--accent-10m)">{headline['best_tf_label']}</p>
      <p class="tile-detail">{headline['best_tf_pnl']} total P&amp;L across 10 tickers</p>
    </div>
    <div class="tile">
      <p class="tile-label">Weakest timeframe</p>
      <p class="tile-value neg">{headline['worst_tf_label']}</p>
      <p class="tile-detail">{headline['worst_tf_pnl']} &mdash; baseline exit loses money here</p>
    </div>
    <div class="tile">
      <p class="tile-label">Best exit upgrade found</p>
      <p class="tile-value pos">+{headline['best_variants']['60m']['uplift']}</p>
      <p class="tile-detail">on 1-hour, swapping in {headline['best_variants']['60m']['label']}</p>
    </div>
  </div>

  <section>
    <h2>1. Timeframe comparison</h2>
    <p class="section-sub">Same strategy, same exit rule (cloud-cross OR 5% stop &mdash; what the live monitor
      uses), same 10 tickers, same 60-day window. Only the candle size changes.</p>
    <div class="bars">{tf_bars}</div>
  </section>

  <section>
    <h2>2. Exit-strategy optimization</h2>
    <p class="section-sub">For each timeframe: is there a better exit than the live monitor's baseline
      (cloud-cross OR 5% stop, no take-profit)? Testing 6 risk-exit variants (no stop, fixed stop at 3/5/8%,
      trailing stop at 5/8%) &times; 3 take-profit caps (none, +10%, +15%) &mdash; 18 combinations per timeframe,
      ranked by total P&amp;L. Top 6 shown; baseline always marked.</p>
    {variant_sections}
  </section>

  <section>
    <h2>3. Per-ticker breakdown</h2>
    <p class="section-sub">Baseline exit, by ticker and timeframe. Sorted by 10-minute P&amp;L. Small samples
      per cell (5&ndash;30 trades) &mdash; read this as directional, not conclusive.</p>
    <div class="table-wrap">
      <table class="ticker-table">
        <thead>
          <tr><th>Ticker</th><th>10-minute</th><th>30-minute</th><th>1-hour</th></tr>
        </thead>
        <tbody>{ticker_rows_html}</tbody>
      </table>
    </div>
  </section>

  <footer>
    <h4>Methodology &amp; caveats</h4>
    <ul>
      <li><strong>Universe:</strong> AAPL, MSFT, NVDA, GOOGL, AMZN, META, AVGO, TSLA, BRK.B, JPM &mdash; the
        10 largest S&amp;P&nbsp;500 constituents by market cap in the live monitor's universe.</li>
      <li><strong>Data:</strong> Yahoo Finance. 10-minute bars are built by merging pairs of 5-minute bars
        (Yahoo has no native 10m interval). 5m/30m cap out at 60 days of history; 1h bars were pulled over
        the same 60-day window so the three timeframes are compared on identical dates, not different sample
        depths.</li>
      <li><strong>Entry rule:</strong> identical to the live monitor &mdash; price and the entire fast cloud
        (EMA5/12) fully above the entire slow cloud (EMA34/50), one position at a time, sized at $10,000
        notional per entry.</li>
      <li><strong>Not applied here:</strong> the live monitor's 2-day earnings blackout is skipped in this
        backtest (no free historical earnings-date source was available), so trade counts here run slightly
        higher than the live monitor would produce around earnings dates.</li>
      <li><strong>Intrabar assumption:</strong> when a bar's low would trigger a stop and its high would
        trigger a take-profit in the same bar, the stop is assumed to hit first (the conservative case).</li>
      <li><strong>Read the sample sizes:</strong> 1-hour produces as few as 5 trades for some tickers over
        this window &mdash; directionally useful, not statistically strong on its own.</li>
    </ul>
  </footer>

</div>
</div>
"""

with open("report.html", "w", encoding="utf-8") as f:
    f.write(html)
print("wrote report.html", len(html), "bytes")
