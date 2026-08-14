"""
Extend the VIX correlation check to real REIT and defense tickers, to test
the user's theory: "VIX moves proportionally for semiconductors, reverse
for defense and REITs." Same methodology as vix_study.py part 1 (5-min
return correlation, aligned by exact 5m timestamp).
"""
import json
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def correlation(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5


def ticker_corr(bars5m, vix_by_ts):
    pairs = []
    for i in range(1, len(bars5m)):
        t_prev, t_cur = bars5m[i - 1]["ts"], bars5m[i]["ts"]
        if t_cur - t_prev != 300:
            continue
        if t_prev not in vix_by_ts or t_cur not in vix_by_ts:
            continue
        stock_ret = bars5m[i]["close"] / bars5m[i - 1]["close"] - 1
        vix_ret = vix_by_ts[t_cur] / vix_by_ts[t_prev] - 1
        pairs.append((stock_ret, vix_ret))
    if len(pairs) < 30:
        return None, 0
    return correlation([p[0] for p in pairs], [p[1] for p in pairs]), len(pairs)


def main():
    with open(os.path.join(DATA_DIR, "vix_bars.json")) as f:
        vix = json.load(f)
    vix_by_ts = {b["ts"]: b["close"] for b in vix["5m"]}

    with open(os.path.join(DATA_DIR, "raw_bars_extra.json")) as f:
        extra = json.load(f)
    reits, defense, data = extra["reits"], extra["defense"], extra["data"]

    with open(os.path.join(DATA_DIR, "raw_bars_wide.json")) as f:
        wide = json.load(f)
    semis = ["AMD", "NVDA", "QCOM", "MU", "ADI", "AVGO"]

    results = {}
    print(f"{'Ticker':6s} {'sector':10s} {'corr':>7s} {'n_pairs':>8s}")
    for sector_name, tickers, source in [
        ("REIT", reits, data), ("Defense", defense, data), ("Semis(ref)", semis, wide)
    ]:
        for t in tickers:
            bars5m = source[t]["5m"]
            c, n = ticker_corr(bars5m, vix_by_ts)
            results[t] = {"sector": sector_name, "corr": c, "n_pairs": n}
            cs = f"{c:7.3f}" if c is not None else "   n/a"
            print(f"{t:6s} {sector_name:10s} {cs} {n:8d}")

    def sector_avg(name):
        vals = [r["corr"] for r in results.values() if r["sector"] == name and r["corr"] is not None]
        return sum(vals) / len(vals) if vals else None

    print()
    for name in ["REIT", "Defense", "Semis(ref)"]:
        avg = sector_avg(name)
        print(f"{name} average correlation: {avg:.3f}" if avg is not None else f"{name}: n/a")

    with open(os.path.join(DATA_DIR, "vix_sector_correlation_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {os.path.join(DATA_DIR, 'vix_sector_correlation_results.json')}")


if __name__ == "__main__":
    main()
