#!/usr/bin/env python3
"""Re-grade the 돌파신호 v1 against a baseline, and against a universe we did not pick.

verify_breakout_findings.py reports the LEVEL of a breakout's SPY-relative excess return
(20d +2.13%, 60d +5.62%) with a ticker-cluster bootstrap CI around that level. A CI around
a level answers "is this number reliably above zero", which is not the question -- the
question is "is it above what you would have got by buying the same universe on the same
day for no reason at all". In the 54-card universe those are very different numbers,
because the universe was hand-picked in 2025-2026 with the 2023-2026 outcomes already
known (see compute_valuation_ic_v4.py for the full argument and the numbers).

This script adds the missing denominators:

  baseline_uncond   every (ticker, day) in the same universe over the same index range.
                    Measures the universe's own drift against SPY.
  baseline_datematched
                    for each event, the mean forward excess of EVERY universe member on
                    that SAME date. This is the strict control: it removes market timing
                    entirely, so whatever survives is the signal picking a stock rather
                    than the signal picking a good week to be long. Breakouts cluster in
                    상승장 by construction, which is exactly the confound it removes.

The headline statistic is therefore the DIFFERENCE (event minus date-matched baseline),
not the level, and the ticker-cluster bootstrap runs on that difference. Clustering is by
ticker because one name can contribute dozens of events that are not independent draws.

Run it on both universes; the comparison is the point.

    python3 verify_breakout_vs_baseline.py --price-dir ../data/raw_5y      --label cards
    python3 verify_breakout_vs_baseline.py --price-dir ../data/sp500_5y    --label sp500
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

from breakout_signal import detect_simple_breakouts

HORIZONS = (20, 60)


def load_bars(path):
    return sorted(json.load(open(path))["daily"], key=lambda b: b["date"])


def forward_metrics(bars, closes, idx, spy_closes, si):
    """Forward SPY-excess return and the two hit-rate definitions the shipped backtest
    uses, for an entry at index idx."""
    out = {}
    n = len(closes)
    for h in HORIZONS:
        if idx + h < n and si is not None and si + h < len(spy_closes):
            out["ex%d" % h] = (closes[idx + h] / closes[idx] - 1) - (spy_closes[si + h] / spy_closes[si] - 1)
    if idx + 20 < n:
        out["hit20"] = float(max(b["h"] for b in bars[idx + 1:idx + 21]) / closes[idx] - 1 >= 0.05)
    if idx + 60 < n:
        out["hit60"] = float(max(b["h"] for b in bars[idx + 1:idx + 61]) / closes[idx] - 1 >= 0.10)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-dir", required=True)
    ap.add_argument("--spy", default=None, help="defaults to <price-dir>/SPY.json")
    ap.add_argument("--label", default="universe")
    ap.add_argument("--min-bars", type=int, default=300)
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    pdir = Path(args.price_dir)
    spy_path = Path(args.spy) if args.spy else pdir / "SPY.json"
    spy_bars = load_bars(spy_path)
    spy_closes = [b["c"] for b in spy_bars]
    spy_index = {b["date"]: i for i, b in enumerate(spy_bars)}

    tickers = sorted(p.stem for p in pdir.glob("*.json") if p.stem != "SPY")
    events = []                       # rows: {ticker, date, ex20, ex60, hit20, hit60}
    universe_day = defaultdict(list)  # date -> [metrics for every ticker that day]
    uncond = []

    used = 0
    for t in tickers:
        bars = load_bars(pdir / f"{t}.json")
        if len(bars) < args.min_bars or "h" not in bars[0]:
            continue
        used += 1
        closes = [b["c"] for b in bars]
        for i in range(60, len(bars)):
            m = forward_metrics(bars, closes, i, spy_closes, spy_index.get(bars[i]["date"]))
            if not m:
                continue
            m["ticker"] = t
            universe_day[bars[i]["date"]].append(m)
            uncond.append(m)
        for ev in detect_simple_breakouts(bars):
            i = ev["idx"]
            m = forward_metrics(bars, closes, i, spy_closes, spy_index.get(bars[i]["date"]))
            if not m:
                continue
            m.update(ticker=t, date=bars[i]["date"])
            events.append(m)

    day_mean = {d: {k: float(np.mean([x[k] for x in rows if k in x]))
                    for k in ("ex20", "ex60", "hit20", "hit60")
                    if any(k in x for x in rows)}
                for d, rows in universe_day.items()}

    def mean_of(rows, key):
        v = [r[key] for r in rows if key in r]
        return float(np.mean(v)) if v else None

    def diff_rows(key):
        """(event value - same-day universe mean) for every event that has both."""
        out = []
        for e in events:
            if key in e and key in day_mean.get(e["date"], {}):
                out.append((e["ticker"], e[key] - day_mean[e["date"]][key]))
        return out

    rng = random.Random(args.seed)
    by_ticker_all = defaultdict(list)
    for e in events:
        by_ticker_all[e["ticker"]].append(e)
    names = sorted(by_ticker_all)

    def cluster_ci(key):
        """Ticker-cluster bootstrap on the event-minus-same-day-universe difference."""
        pool = defaultdict(list)
        for tkr, d in diff_rows(key):
            pool[tkr].append(d)
        keys = [k for k in names if pool.get(k)]
        if len(keys) < 5:
            return None
        means = []
        for _ in range(args.boot):
            draw = []
            for _ in range(len(keys)):
                draw.extend(pool[keys[rng.randrange(len(keys))]])
            if draw:
                means.append(sum(draw) / len(draw))
        if not means:
            return None
        lo, hi = np.percentile(means, [2.5, 97.5])
        return float(lo), float(hi)

    report = {"label": args.label, "tickers": used, "events": len(events),
              "unconditional_observations": len(uncond), "metrics": {}}
    print(f"=== {args.label}: {used} tickers, {len(events)} breakout events, "
          f"{len(uncond)} unconditional (ticker,day) observations ===")
    print(f"{'metric':8} {'event':>9} {'uncond':>9} {'same-day':>9} {'event-sameday':>15} {'95% CI (cluster)':>26}")
    for key, pct in (("ex20", True), ("ex60", True), ("hit20", False), ("hit60", False)):
        ev = mean_of(events, key)
        un = mean_of(uncond, key)
        dr = diff_rows(key)
        dm = float(np.mean([d for _, d in dr])) if dr else None
        ci = cluster_ci(key)
        if ev is None:
            continue
        f = (lambda x: f"{x*100:+7.2f}%") if pct else (lambda x: f"{x*100:7.1f}%")
        sameday = ev - dm if dm is not None else None
        print(f"{key:8} {f(ev)} {f(un)} {f(sameday) if sameday is not None else '      n/a':>9} "
              f"{f(dm) if dm is not None else 'n/a':>15} "
              f"{('[%s, %s]' % (f(ci[0]).strip(), f(ci[1]).strip())):>26}")
        report["metrics"][key] = {
            "event_mean": round(ev, 5), "unconditional_mean": round(un, 5) if un is not None else None,
            "same_day_universe_mean": round(sameday, 5) if sameday is not None else None,
            "event_minus_same_day": round(dm, 5) if dm is not None else None,
            "cluster_bootstrap_95ci": [round(ci[0], 5), round(ci[1], 5)] if ci else None,
            "n_events": sum(1 for e in events if key in e),
        }
    if args.out:
        json.dump(report, open(args.out, "w"), indent=2, ensure_ascii=False)
        print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
