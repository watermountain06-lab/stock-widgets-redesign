#!/usr/bin/env python3
"""Fetch a control universe that was NOT hand-picked for this site, so a signal can be
graded against something other than the 54 cards.

Why this exists: the cards were chosen in 2025-2026 as stocks worth covering, i.e. chosen
with the 2023-2026 outcomes already known. Over the 5-year window the median card returned
+107% against SPY's +75%, and the panel's mean 12-month forward excess return is +23%. Any
backtest run only on that universe is conditioning on the future, which does not merely
shift the level -- it manufactures a "cheap now -> outperforms later" correlation out of
nothing (a name that looked cheap and then rocketed got a card; one that looked cheap and
stayed flat never entered the sample). See compute_valuation_ic_v4.py for the case where
that artifact produced a 12-month IC of -0.218 with a confidence interval excluding zero,
which collapsed to -0.023 the moment the same test was run here instead.

Universe: the 503 current S&P 500 names already listed in scripts/sp500.json (ticker + CIK
both present, so nothing is typed by hand). Current membership carries its own mild
survivorship -- names that dropped out of the index are absent -- which is much less than
hand-picking but is not zero, and should be stated wherever results from it are quoted.

Splits: taken from Yahoo's own events=split payload for the same request as the bars,
rather than the hand-verified KNOWN_SPLITS table in fetch_eps_history.py. That table is
the right approach for a card ticker (it documents WHY each entry is what it is, and
catches the spin-off ratios that aggregators mislabel as splits), but 500 tickers cannot
be verified that way. Taking both from one request means the price series and the split
list agree by construction, and only splits inside the price window can matter here
because PER is computed only on dates that have a price bar. Verify the output with a
single-day-move scan before trusting it: at the 2026-09-12 run, 4 of 467 tickers had a
move above 45% (MRNA, ECHO, GL, APP), which compute_valuation_ic_v4.py excludes by name.

EPS: same point-in-time construction as fetch_eps_history.py -- us-gaap
EarningsPerShareDiluted from EDGAR, split-corrected per entry using that entry's OWN filed
date, then deduped by (start, end) keeping the EARLIEST filed row so each TTM figure is
tagged with the date it was actually first disclosed. Q4 is derived from the 10-K minus
the three quarters where the filer does not tag it directly.

Resumable: a ticker whose price and EPS files both already exist is skipped, so an
interrupted run can just be re-run. Tickers are dropped (and named in the error list, not
silently) when they have under 900 price bars or under 20 TTM EPS points -- recent IPOs,
spin-offs, and filers whose XBRL history is too short for a 2-year trailing anchor.

Usage:
    python3 fetch_control_universe.py           # -> data/sp500_5y/, data/sp500_eps/
"""
import argparse
import json
import os
import subprocess
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YAHOO_UA = {"User-Agent": "Mozilla/5.0"}
SEC_CURL = ["curl", "-s", "-A", "Mozilla/5.0 (research; contact gptjhss@gmail.com)"]
MIN_BARS, MIN_EPS_POINTS = 900, 20


def yahoo_ticker(t):
    return t.replace(".", "-")


def fetch_prices_and_splits(ticker):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker(ticker)}"
           f"?range=5y&interval=1d&events=split")
    req = urllib.request.Request(url, headers=YAHOO_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    result = payload["chart"]["result"]
    if not result:
        raise ValueError(f"no chart data: {payload['chart'].get('error')}")
    chart = result[0]
    quote = chart["indicators"]["quote"][0]
    bars = []
    for i, ts in enumerate(chart["timestamp"]):
        close = quote["close"][i]
        if close is None:
            continue
        bars.append({"date": datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d"),
                     "c": round(close, 4)})
    splits = [
        {"date": datetime.fromtimestamp(s["date"], tz=timezone.utc).astimezone().strftime("%Y-%m-%d"),
         "ratio": s["numerator"] / s["denominator"]}
        for s in ((chart.get("events") or {}).get("splits") or {}).values()
    ]
    return {"daily": bars, "splits": sorted(splits, key=lambda s: s["date"])}


def sec_json(url):
    out = subprocess.run(SEC_CURL + [url], capture_output=True, text=True, timeout=45)
    return json.loads(out.stdout)


def period_days(entry):
    # Same guard as fetch_eps_history.py: a few filers have a malformed XBRL entry with no
    # "start", which must fail both the quarterly and annual filters rather than KeyError.
    if "start" not in entry:
        return -1
    return (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days


def dedup_earliest_filed(entries):
    best = {}
    for e in entries:
        key = (e["start"], e["end"])
        if key not in best or e["filed"] < best[key]["filed"]:
            best[key] = e
    return sorted(best.values(), key=lambda e: e["end"])


def fetch_eps(ticker, cik, splits):
    data = sec_json(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/"
                    f"EarningsPerShareDiluted.json")
    entries = data.get("units", {}).get("USD/shares", [])
    if not entries:
        # companyconcept has a known intermittent indexing-lag bug that returns an empty
        # units list for a filer that has real data; companyfacts serves the same data.
        facts = sec_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        entries = facts["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"]

    entries = [dict(e) for e in entries]
    for e in entries:
        ratio = 1.0
        for s in splits:
            if e["filed"] < s["date"]:
                ratio *= s["ratio"]
        if ratio != 1.0:
            e["val"] = e["val"] / ratio

    quarterly = dedup_earliest_filed([e for e in entries
                                      if e["form"] == "10-Q" and 80 <= period_days(e) <= 100])
    annual = dedup_earliest_filed([e for e in entries
                                   if e["form"] == "10-K" and period_days(e) > 350])

    quarters = list(quarterly)
    for fy in annual:
        fy_end = date.fromisoformat(fy["end"])
        members = [q for q in quarterly
                   if date.fromisoformat(q["end"]) <= fy_end
                   and (fy_end - date.fromisoformat(q["start"])).days <= 380
                   and (fy_end - date.fromisoformat(q["end"])).days <= 280]
        if len(members) == 3 and not any(q["end"] == fy["end"] for q in quarterly):
            quarters.append({
                "start": max(members, key=lambda m: m["end"])["end"], "end": fy["end"],
                "val": round(fy["val"] - sum(m["val"] for m in members), 4),
                "filed": fy["filed"], "form": "10-K-derived", "accn": fy["accn"],
            })
    quarters.sort(key=lambda e: e["end"])

    out = []
    for i, q in enumerate(quarters):
        if i < 3:
            continue
        out.append({"quarter_end": q["end"], "quarter_eps": q["val"],
                    "ttm_eps": round(sum(x["val"] for x in quarters[i - 3:i + 1]), 4),
                    "form": q["form"],
                    "available_date": q["filed"],  # true first-disclosure date
                    "accn": q["accn"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default=str(ROOT / "scripts/sp500.json"))
    ap.add_argument("--price-out", default=str(ROOT / "data/sp500_5y"))
    ap.add_argument("--eps-out", default=str(ROOT / "data/sp500_eps"))
    args = ap.parse_args()

    os.makedirs(args.price_out, exist_ok=True)
    os.makedirs(args.eps_out, exist_ok=True)
    members = json.load(open(args.list))

    done = ok = skipped = 0
    errors = []
    for rec in members:
        ticker, cik = rec["ticker"], rec["cik"]
        price_path = os.path.join(args.price_out, f"{ticker}.json")
        eps_path = os.path.join(args.eps_out, f"{ticker}.json")
        if os.path.exists(price_path) and os.path.exists(eps_path):
            skipped += 1
            continue
        try:
            if os.path.exists(price_path):
                prices = json.load(open(price_path))
            else:
                prices = fetch_prices_and_splits(ticker)
                if len(prices["daily"]) < MIN_BARS:
                    raise ValueError(f"only {len(prices['daily'])} bars")
                json.dump(prices, open(price_path, "w"))
                time.sleep(0.35)
            if not os.path.exists(eps_path):
                eps = fetch_eps(ticker, cik, prices["splits"])
                if len(eps) < MIN_EPS_POINTS:
                    raise ValueError(f"only {len(eps)} eps points")
                json.dump(eps, open(eps_path, "w"))
                time.sleep(0.2)
            ok += 1
        except Exception as exc:
            errors.append((ticker, str(exc)[:90]))
            if os.path.exists(eps_path):
                os.remove(eps_path)
        done += 1
        if done % 50 == 0:
            print(f"...{done}/{len(members)} ok={ok} err={len(errors)}", flush=True)

    print(f"DONE total={len(members)} ok={ok} skipped={skipped} errors={len(errors)}")
    for ticker, msg in errors:
        print(f"  ERR {ticker} {msg}")


if __name__ == "__main__":
    main()
