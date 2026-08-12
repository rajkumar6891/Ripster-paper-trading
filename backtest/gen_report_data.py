import json

d = json.load(open("study_results.json"))
tf_order = ["10m", "30m", "60m"]
tf_label = {"10m": "10-minute", "30m": "30-minute", "60m": "1-hour"}


def fmt_money(v):
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


def fmt_pct(v):
    return f"{v*100:.1f}%" if v is not None else "n/a"


def fmt_pf(v):
    if v is None:
        return "n/a"
    if v == float("inf"):
        return "inf"
    return f"{v:.2f}"


base = d["timeframe_baseline"]
max_abs_pnl = max(abs(base[tf]["total_pnl"]) for tf in tf_order)

rows_tf = []
for tf in tf_order:
    s = base[tf]
    rows_tf.append({
        "tf": tf, "label": tf_label[tf], "trades": s["trades"],
        "win_rate": fmt_pct(s["win_rate"]), "pnl": fmt_money(s["total_pnl"]),
        "pnl_raw": s["total_pnl"], "pf": fmt_pf(s["profit_factor"]),
        "bar_pct": round(abs(s["total_pnl"]) / max_abs_pnl * 100, 1),
        "positive": s["total_pnl"] >= 0,
    })

out = {"timeframe_rows": rows_tf}

# exit variant tables (top 6 by total_pnl, plus baseline row flagged)
variant_tables = {}
for tf in tf_order:
    rows = d["variant_results"][tf]
    max_variant_pnl = max(abs(r["total_pnl"]) for r in rows)
    formatted = []
    for r in rows:
        formatted.append({
            "label": r["label"], "trades": r["trades"], "win_rate": fmt_pct(r["win_rate"]),
            "pnl": fmt_money(r["total_pnl"]), "pnl_raw": r["total_pnl"],
            "pf": fmt_pf(r["profit_factor"]),
            "bar_pct": round(abs(r["total_pnl"]) / max_variant_pnl * 100, 1),
            "positive": r["total_pnl"] >= 0,
            "is_baseline": "baseline" in r["label"],
        })
    variant_tables[tf] = formatted
out["variant_tables"] = variant_tables

# per-ticker breakdown
per_ticker = d["timeframe_baseline_per_ticker"]
tickers = list(per_ticker["10m"].keys())
ticker_rows = []
for t in tickers:
    row = {"ticker": t}
    for tf in tf_order:
        s = per_ticker[tf][t]
        row[tf] = {"trades": s["trades"], "win_rate": fmt_pct(s["win_rate"]), "pnl": fmt_money(s["total_pnl"]),
                    "positive": s["total_pnl"] >= 0}
    ticker_rows.append(row)
# sort by 10m pnl desc
ticker_rows.sort(key=lambda r: per_ticker["10m"][r["ticker"]]["total_pnl"], reverse=True)
out["ticker_rows"] = ticker_rows

# headline stats
best_tf = max(rows_tf, key=lambda r: r["pnl_raw"])
worst_tf = min(rows_tf, key=lambda r: r["pnl_raw"])
best_variant_per_tf = {tf: max(d["variant_results"][tf], key=lambda r: r["total_pnl"]) for tf in tf_order}
out["headline"] = {
    "best_tf_label": best_tf["label"], "best_tf_pnl": best_tf["pnl"],
    "worst_tf_label": worst_tf["label"], "worst_tf_pnl": worst_tf["pnl"],
    "best_variants": {tf: {"label": best_variant_per_tf[tf]["label"], "pnl": fmt_money(best_variant_per_tf[tf]["total_pnl"]),
                            "uplift": fmt_money(best_variant_per_tf[tf]["total_pnl"] - base[tf]["total_pnl"])}
                       for tf in tf_order},
}

with open("report_data.json", "w") as f:
    json.dump(out, f, indent=2)
print("wrote report_data.json")
print(json.dumps(out["headline"], indent=2))
