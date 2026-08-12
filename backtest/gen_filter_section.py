import json

d = json.load(open("filter_study_results.json"))
baseline = d["baseline"]
results = [r for r in d["results"] if r["trades"] >= 15]

top_total = sorted(results, key=lambda r: r["total_pnl"], reverse=True)[:8]
top_quality = sorted(results, key=lambda r: r["avg_pnl"], reverse=True)[:8]

better_fewer = [r for r in results if r["total_pnl"] > baseline["total_pnl"] and r["trades"] < baseline["trades"]]
better_fewer.sort(key=lambda r: r["total_pnl"], reverse=True)


def fmt_money(v):
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


def fmt_pct(v):
    return f"{v*100:.1f}%" if v is not None else "n/a"


def fmt_pf(v):
    if v is None:
        return "n/a"
    return "inf" if v == float("inf") else f"{v:.2f}"


def row_html(r, max_pnl, highlight=""):
    cls = "pos" if r["total_pnl"] >= 0 else "neg"
    hl = f' class="filter-row {highlight}"' if highlight else ' class="filter-row"'
    bar_pct = round(abs(r["total_pnl"]) / max_pnl * 100, 1) if max_pnl else 0
    return f"""
        <tr{hl}>
          <td class="filter-label">{r['label']}</td>
          <td class="num">{r['trades']}</td>
          <td class="num">{fmt_pct(r['win_rate'])}</td>
          <td class="num {cls}">{fmt_money(r['total_pnl'])}</td>
          <td class="num">{fmt_money(r['avg_pnl'])}</td>
          <td class="num">{fmt_pf(r['profit_factor'])}</td>
        </tr>"""


max_pnl_total = max(abs(r["total_pnl"]) for r in top_total)
max_pnl_quality = max(abs(r["total_pnl"]) for r in top_quality)

rows_total_html = "".join(row_html(r, max_pnl_total, "winner" if r == top_total[0] else "") for r in top_total)
rows_quality_html = "".join(row_html(r, max_pnl_quality, "winner" if r == top_quality[0] else "") for r in top_quality)

best_q = top_quality[0]
trade_cut_pct = round((1 - best_q["trades"] / baseline["trades"]) * 100)
avg_uplift_x = round(best_q["avg_pnl"] / baseline["avg_pnl"], 1)

section_html = f"""
  <section>
    <h2>4. Entry-filter optimization (10-minute, exit fixed at stop-3% / +15% TP)</h2>
    <p class="section-sub">Layering RSI(14), ADX(14), relative volume, EMA-cloud separation, and a
      first-20-minutes-of-session filter on top of the same cloud-crossover entry &mdash; 162 combinations
      tested, each requiring at least 15 trades across the 10 tickers to count. Unfiltered reference:
      <strong>{baseline['trades']} trades</strong>, {fmt_pct(baseline['win_rate'])} win rate,
      {fmt_money(baseline['total_pnl'])} total, {fmt_money(baseline['avg_pnl'])} avg/trade.</p>

    <div class="filter-tiles">
      <div class="tile">
        <p class="tile-label">Best for raw total P&amp;L</p>
        <p class="tile-value pos">{fmt_money(top_total[0]['total_pnl'])}</p>
        <p class="tile-detail">{top_total[0]['trades']} trades &middot; {top_total[0]['label']}</p>
      </div>
      <div class="tile">
        <p class="tile-label">Best for trade quality</p>
        <p class="tile-value pos">{fmt_money(best_q['avg_pnl'])}<span style="font-size:13px;color:var(--text-muted)">/trade</span></p>
        <p class="tile-detail">{trade_cut_pct}% fewer trades, {avg_uplift_x}&times; the avg profit/trade, {fmt_pct(best_q['win_rate'])} win rate</p>
      </div>
    </div>

    <h3 class="subhead">Ranked by total P&amp;L</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Filter combination</th><th class="num">Trades</th><th class="num">Win %</th><th class="num">Total P&amp;L</th><th class="num">Avg/trade</th><th class="num">Profit factor</th></tr></thead>
        <tbody>{rows_total_html}</tbody>
      </table>
    </div>

    <h3 class="subhead">Ranked by avg P&amp;L per trade &mdash; &ldquo;fewer, more legit trades&rdquo;</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Filter combination</th><th class="num">Trades</th><th class="num">Win %</th><th class="num">Total P&amp;L</th><th class="num">Avg/trade</th><th class="num">Profit factor</th></tr></thead>
        <tbody>{rows_quality_html}</tbody>
      </table>
    </div>

    <p class="section-sub" style="margin-top:16px;">
      <strong>Reading this:</strong> the quality-ranked winner
      (<code>{best_q['label']}</code>) cuts trade count from {baseline['trades']} to {best_q['trades']}
      ({trade_cut_pct}% fewer) while lifting win rate from {fmt_pct(baseline['win_rate'])} to
      {fmt_pct(best_q['win_rate'])} and profit factor from {fmt_pf(baseline['profit_factor'])} to
      {fmt_pf(best_q['profit_factor'])} &mdash; genuinely higher-conviction setups. Its <em>total</em> P&amp;L
      is lower only because far less capital-time is deployed at the same fixed $10,000/trade size; sizing
      each of these higher-conviction trades larger is the natural next lever if the goal is total dollars,
      not just hit rate.
    </p>
  </section>
"""

with open("report.html", "r", encoding="utf-8") as f:
    html = f.read()

marker = "  <footer>"
if "4. Entry-filter optimization" not in html:
    html = html.replace(marker, section_html + "\n" + marker)

extra_css = """
  .filter-tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 24px; }
  .subhead { font-size: 14px; font-weight: 700; margin: 20px 0 10px; color: var(--text-secondary); }
  tr.filter-row.winner td { background: color-mix(in srgb, var(--good-soft) 55%, transparent); }
  .filter-label { font-size: 12.5px; max-width: 360px; }
  code { font-family: ui-monospace, "SF Mono", monospace; font-size: 12px; background: var(--surface); padding: 1px 5px; border-radius: 4px; border: 1px solid var(--border); }
  @media (max-width: 640px) { .filter-tiles { grid-template-columns: 1fr; } }
"""
if ".filter-tiles" not in html:
    html = html.replace("</style>", extra_css + "</style>")

with open("report.html", "w", encoding="utf-8") as f:
    f.write(html)
print("updated report.html")
