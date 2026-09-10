#!/usr/bin/env python3
"""Fetch quarterly diluted EPS history from SEC EDGAR and compute TTM EPS per quarter,
with each entry tagged by the date it was ACTUALLY first disclosed -- suitable as a
point-in-time anchor for a real (no-look-ahead) backtest.

Forked from stock-widgets-customer/scripts/fetch_quarterly_eps.py with one correctness
fix, found and verified during this build:

  That script's dedup kept the LATEST-filed XBRL entry per (start,end) period, to solve
  split-restatement (get the correctly-scaled value). This has a side effect that breaks
  point-in-time correctness: EDGAR shows the same historical quarter's number again in
  each subsequent filing's comparative column, so "latest filed" can be a YEAR OR MORE
  after the number was actually first disclosed. Verified on real NVDA data:
    - 2022-05-01 (Q1 FY23): original filing accn ...-22-000079, filed 2022-05-27, val 0.64
                            later comparative accn ...-23-000093, filed 2023-05-26, val 0.64
    (latest-filed dedup would tag this quarter "available" a full year late)

  Fix: apply per-entry split-correction FIRST (using apply_split_correction, unchanged
  logic, keyed off each entry's OWN filed date), THEN dedup by (start,end) keeping the
  EARLIEST-filed entry. This resolves the split-restatement duplicates specifically
  (0.64/10=0.064 either way for the case above) -- but a 2026-09-02 Codex review
  correctly flagged that "switching which one wins only fixes the date, not the value"
  is NOT a general guarantee: if EDGAR later restates a filing for a reason OTHER than
  a known stock split (a genuine accounting correction/restatement), the earliest-filed
  value can legitimately differ from a later-corrected one, and this function has no way
  to detect that case -- it would silently keep the (possibly since-corrected) earliest
  value forever. Checked directly against NVDA's full raw EDGAR history for this risk:
  15 (start,end) groups have split-corrected values that disagree by >0 across
  duplicates; only 1 has a relative spread >1% (2017-01-30~2017-07-30, where a single
  outlier 2018-02-28 filing shows roughly half the other two filings' value -- earliest
  and latest both agree at 0.0427, so "earliest wins" happens to land on the correct
  side here), the rest are sub-cent 2016-era quarters where the "mismatch" is source
  data's own 2-decimal rounding, not a real restatement. So: no material impact found
  for NVDA specifically, but this is a real residual limitation of the method, not a
  solved problem -- re-check this for any other ticker before trusting its output blindly.

Usage:
    python3 fetch_eps_history.py NVDA --cik 0001045810 --out data/eps_quarterly/NVDA.json
"""
import argparse
import json
import subprocess
import sys
from datetime import date


def curl_json(url):
    result = subprocess.run(
        ["curl", "-s", "-A", "Mozilla/5.0 (research; contact gptjhss@gmail.com)", url],
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


def split_ratio(filed, split_dates):
    ratio = 1
    for eff_date, r in split_dates:
        if filed < eff_date:
            ratio *= r
    return ratio


def apply_split_correction(entries, split_dates):
    for e in entries:
        r = split_ratio(e["filed"], split_dates)
        if r != 1:
            e["val"] = round(e["val"] / r, 6)
    return entries


def dedup_earliest_filed(entries):
    """Dedup by (start, end), keep the EARLIEST `filed` date -- the true first-disclosure
    date, i.e. the honest point-in-time anchor. Magnitude is unaffected since
    apply_split_correction() has already normalized every entry's `val` to today's share
    count using its OWN filed date, before this function runs."""
    best = {}
    for e in entries:
        key = (e["start"], e["end"])
        if key not in best or e["filed"] < best[key]["filed"]:
            best[key] = e
    return list(best.values())


def days_between(e):
    # Guard: a few filers have a malformed XBRL entry with no "start" (confirmed on GS,
    # one 2008 entry). Returning -1 makes it fail both the quarterly (80<=d<=100) and
    # annual (d>350) filters in main(), so it is dropped before dedup_earliest_filed()
    # -- which would otherwise KeyError on e["start"] too.
    if "start" not in e:
        return -1
    return (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days


KNOWN_SPLITS = {
    "NVDA": [("2021-07-20", 4), ("2024-06-07", 10)],
    # Verified 2026-09-02 against real EDGAR duplicate-filing detection (not just public
    # knowledge) for the cross-ticker valuation-IC backtest -- see
    # scripts/compute_valuation_ic.py. Detected ratios matched known split facts for all.
    "AAPL": [("2014-06-09", 7), ("2020-08-31", 4)],
    "AMZN": [("2022-06-06", 20)],
    "AVGO": [("2024-07-15", 10)],
    "GOOGL": [("2022-07-18", 20)],
    "TSLA": [("2020-08-31", 5), ("2022-08-25", 3)],
    "META": [],   # no splits ever -- confirmed empirically (no ratio>1.3 duplicate found)
    "MSFT": [],   # last split 2003, outside this data's reporting window -- confirmed empirically
    "MU": [],     # last split 2000-05-02, outside this data's reporting window -- WebSearch confirmed
    "JPM": [],    # last split 2000-06-12 (3-for-2), outside this data's reporting window -- WebSearch confirmed 2026-09-04
    "LLY": [],    # last split 1997-10-16 (2-for-1), outside this data's reporting window -- WebSearch confirmed 2026-09-04
    "WMT": [("2024-02-26", 3)],  # 3-for-1 split, effective 2024-02-26 -- WebSearch confirmed 2026-09-05 (corporate.walmart.com release), within this data's 5y window
    "AMD": [],    # last split 2000-08-22 (2-for-1), outside this data's reporting window -- WebSearch confirmed 2026-09-05
    "JNJ": [],    # last split 2001-06-13 (2-for-1), outside this data's reporting window -- WebSearch confirmed 2026-09-05
    "MA": [],     # last split 10-for-1 effective 2014-01, outside this data's reporting window -- WebSearch confirmed 2026-09-06
    "XOM": [],    # last split 2001-07-19 (2-for-1), outside this data's reporting window -- WebSearch confirmed 2026-09-06
    "ORCL": [],   # last split 2000-10-13 (2-for-1), outside this data's reporting window -- WebSearch confirmed 2026-09-06
    "ABBV": [],   # no splits ever since 2013 Abbott spinoff -- WebSearch confirmed 2026-09-06
    "COST": [],   # last split 2000-01-03 (2-for-1), outside this data's reporting window -- confirmed empirically (no ratio>1.3 duplicate found in the full XBRL EPS history back to 2012)
    "LRCX": [("2024-10-02", 10)],  # 10-for-1 split, effective 2024-10-02 -- confirmed via LRCX FY2025 10-K text ("On October 2, 2024, the Company effected a 10-for-one stock split")
    "CAT": [],    # last split 2005-06-13 (2-for-1), outside this data's reporting window -- confirmed empirically (no ratio>1.3 duplicate found in fetched XBRL EPS history)
    "MRK": [],    # no stock split found -- the only >1.3x duplicate-value groups in the full XBRL history are 4 quarters from 2009 (Schering-Plough merger restatement, not a split), all outside this data's 5y window -- confirmed empirically 2026-09-07
    "CSCO": [],   # no split within the fetched XBRL history -- confirmed empirically 2026-09-07 (0 duplicate-value groups found at all)
    "KO": [],     # last split 2012-08 (2-for-1), outside this data's 5y reporting window -- confirmed empirically 2026-09-07 (7 duplicate-value groups found, all from 2010-2013 restatements pre-dating the window)
    "MS": [],     # last split 2000-01-27 (2-for-1), outside this data's 5y reporting window -- WebSearch confirmed 2026-09-09
    "DELL": [],   # no proportional stock split -- the 2021-11-02 "1973-for-1000"/"903-for-500" ratios some aggregators list are the VMware spinoff's Class V tracking-stock exchange into Class C, a fixed-ratio security conversion, not a market-wide split of existing Class C shares (no price discontinuity around 2021-11-02 in Yahoo daily data) -- confirmed empirically 2026-09-09 (0 duplicate-value groups with ratio>1.3 found in full XBRL EarningsPerShareDiluted history)
    "PG": [],     # last split 2004-06-21 (2-for-1), outside this data's 5y reporting window -- WebSearch confirmed 2026-09-09
    "PANW": [("2024-12-12", 2)],  # 2-for-1 split, effected 2024-12-12 -- confirmed via PANW FY2025 10-K text ("On December 12, 2024, we effected a two-for-one stock split of our outstanding shares of common stock"); all share/per-share amounts retroactively adjusted by the company
    "HD": [],     # last split 1999-12-30 (3-for-2), far outside this data's XBRL window (HD's EarningsPerShareDiluted history starts at FY2007, earliest end 2008-02-03) -- WebSearch confirmed 2026-09-09 (13 splits between 1982 and 1999, none since) and confirmed empirically (0 of 121 (start,end) groups in the full XBRL EPS history have a duplicate-value ratio >1.3)
    "GS": [],     # GS has never split since its 1999 IPO -- confirmed empirically (no duplicate (start,end) group with ratio>1.3 in the full XBRL EarningsPerShareDiluted history)
    "NFLX": [("2025-11-14", 10)],  # 10-for-1 forward split -- confirmed via NFLX FY2025 10-K Item 5 / Q2 2026 10-Q Note 1 text ("On November 14, 2025, the Company completed a ten-for-one forward stock split of the Company's issued common stock"), record date 2025-11-10, split-adjusted trading from 2025-11-17. Boundary is the 11-14 completion date, not the 11-17 trading date, because split_ratio() compares each XBRL entry's FILED date: last pre-split filing 2025-10-22 (Q3'25 10-Q, EPS 5.87 -> 0.587), first post-split filing 2026-01-23 (FY25 10-K, EPS 2.53 as-filed)
    "PM": [],     # PM has never split since it began trading in 2008 -- the spin-off from Altria was a 1-for-1 distribution of PM shares to Altria holders (a separation, not a split of PM stock) -- WebSearch confirmed 2026-09-09 and confirmed empirically (0 of 123 (start,end) groups in the full XBRL EarningsPerShareDiluted history have a duplicate-value ratio >1.3)
    "WFC": [],    # last split 2-for-1 in August 2006 (announced 2006-06-27 as a 100% stock dividend, record date 2006-08-04, distributed 2006-08-11, split-adjusted from 2006-08-14 -- SEC 8-K exhibit 99.2, accession 0001193125-06-140458), far outside both this data's 5y price window and WFC's XBRL EarningsPerShareDiluted history (earliest end 2007-12-31) -- confirmed empirically 2026-09-10 (only 3 of 111 (start,end) groups have a duplicate-value ratio >1.3; all three are 2020 COVID-era loss quarters restated between the 2020 and 2021 filings at ratios 1.45/1.53/1.67, none a clean 1.5x or 2x split signature, and all pre-date the 5y window)
    "GEV": [],    # GE Vernova has never split. It began trading on the NYSE on 2024-04-02 as a spin-off from General Electric (now GE Aerospace): GE holders of record on 2024-03-19 received one GEV share for every four GE shares held (WebSearch confirmed 2026-09-10 against GE's own 2024-04-02 spin-off FAQ, and the FY2025 10-K's "On April 2, 2024 ... GE distributed all of the shares of our common stock to its stockholders"). That 1-for-4 distribution ratio is the rate at which a NEW security was handed to the PARENT's holders -- not a proportional split of GEV's own outstanding shares -- so nothing in GEV's per-share history is retroactively restated by it, and the price-adjustment factor vendors book for the event lands on the parent ticker (GE), not on GEV. Same distinction already documented for DELL's VMware Class V exchange and RTX's 2020-04-03 Carrier/Otis spin-off factor below. GEV's XBRL EarningsPerShareDiluted history begins at end 2022-12-31 (Form 10 carve-out combined financials); confirmed empirically 2026-09-10 that 0 of 21 (start,end) groups have a duplicate-value ratio >1.3.
    "RTX": [],    # no proportional stock split inside this data's window. Last true split was United Technologies' 2-for-1 on 2005-06-13 (earlier UTC 2-for-1s: 1999-05-18 -- board declared 1999-04-30, stock dividend issued 1999-05-17 per UTC's own 8-K/press release -- plus 1996-12-11, 1984-06-11, 1976-05-19); WebSearch confirmed 2026-09-10. That is outside RTX's XBRL EarningsPerShareDiluted history, which starts at end 2007-12-31, and far outside this data's 5y price window (from 2021-09-10). The "1589-for-1000 on 2020-04-03" that Investing.com/Seeking Alpha list in RTX's split column is NOT a split: on 2020-04-03 UTC completed the Carrier (0.5 sh/UTX sh) and Otis (0.25 sh/UTX sh) spin-offs and then merged with Raytheon Company (2.3348 RTX sh per RTC sh); price vendors book the ~1.589 spinoff price-adjustment factor as a split row -- the same aggregator artifact already documented for DELL's VMware Class V exchange above, and it too pre-dates the 5y window. Confirmed empirically 2026-09-10: 0 of 123 (start,end) groups in the full XBRL EPS history have a duplicate-value ratio >1.3, so no retroactive per-share restatement exists anywhere in the series.
    "ANET": [("2021-11-18", 4), ("2024-12-04", 4)],  # TWO 4-for-1 forward splits, both inside this data's 5y price window (which starts 2021-09-10) -- confirmed 2026-09-10 from ANET's OWN filings, not from an aggregator. (1) FY2021 10-K Note 1: "On November 1, 2021, we announced a four-for-one split ... effected in the form of a stock dividend. Each stockholder of record on November 11, 2021 received three additional shares ... distributed after close of trading on November 17, 2021", so split-adjusted trading begins 2021-11-18. (2) FY2025 10-K Note 1 + the 2024-12-03 8-K Item 5.03: "On November 7, 2024, the Company announced a four-for-one forward stock split ... effected through the filing of an amendment ... which became effective at 4:30 p.m. Eastern Time on December 3, 2024", so split-adjusted trading begins 2024-12-04. Each boundary is the split-adjusted TRADING date because split_ratio() compares each XBRL entry's FILED date, and both dates sit cleanly between the last pre-split filing and the first post-split one (2021: last pre 2021-11-02 Q3'21 10-Q EPS 2.81 -> 0.70; first post 2022-02-15 FY21 10-K. 2024: last pre 2024-11-08 Q3'24 10-Q EPS 2.33 -> 0.58; first post 2025-02-19 FY24 10-K EPS 2.23 as-filed). Confirmed empirically the same day: 14 of 88 (start,end) groups in the full XBRL EarningsPerShareDiluted history have a duplicate-value ratio >1.3, and every one is a clean ~4.00x step at exactly one of these two boundaries (e.g. FY2019 10.63 filed 2021-02-19 -> 2.66 filed 2022-02-15 = 3.996x; FY2022 4.27 filed 2024-02-13 -> 1.07 filed 2025-02-19 = 3.99x) -- no non-split restatement anywhere in the series. Yahoo's 5y daily series is already adjusted for BOTH (max single-day moves in the whole window are +20.4% on 2021-11-02, the Q3'21 earnings pop, and -22.4% on 2025-01-27, the DeepSeek AI-capex selloff; no >50% discontinuity at either split date).
    "SNDK": [],   # SanDisk has never split -- it only began trading 2025-02-13 (when-issued) / 2025-02-24 (regular-way, Nasdaq) after Western Digital distributed 80.1% of SanDisk on 2025-02-21 at one-third of a SNDK share per WDC share. That distribution ratio is the SPINOFF's exchange ratio applied to WDC holders, not a split of SNDK's own outstanding shares -- the same aggregator artifact already documented for DELL's VMware Class V exchange and RTX's 2020 Carrier/Otis spin-merge above, except here it belongs to the PARENT's price series, so it must never be applied to SNDK's own EPS history. Confirmed empirically 2026-09-10: SNDK's full XBRL EarningsPerShareDiluted history (20 entries, earliest end 2023-06-30, carve-out periods included) has 0 (start,end) groups with any duplicate-value disagreement at all, let alone a ratio >1.3.
}

CIKS = {
    "NVDA": "0001045810", "AAPL": "0000320193", "AMZN": "0001018724",
    "AVGO": "0001730168", "GOOGL": "0001652044", "META": "0001326801",
    "MSFT": "0000789019", "TSLA": "0001318605", "WMT": "0000104169",
    "AMD": "0000002488",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--cik", required=True)
    ap.add_argument("--tag", default="EarningsPerShareDiluted")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{args.cik}/us-gaap/{args.tag}.json"
    data = curl_json(url)
    entries = data["units"]["USD/shares"]
    if not entries:
        # companyconcept has a known intermittent indexing-lag bug (returns
        # units:{"USD/shares":{}} for a filer that has real data) -- confirmed
        # on KO twice (2026-09-06, 2026-09-07, >24h apart, still empty both
        # times, so not a transient blip). companyfacts serves the same
        # underlying data and has not shown this bug -- fall back to it.
        print(f"NOTE: companyconcept returned 0 entries for {args.ticker}, "
              f"falling back to companyfacts", file=sys.stderr)
        facts = curl_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{args.cik}.json")
        entries = facts["facts"]["us-gaap"][args.tag]["units"]["USD/shares"]

    ticker_key = args.ticker.upper()
    if ticker_key not in KNOWN_SPLITS:
        print(f"WARNING: no known-split table for {args.ticker} -- add an entry "
              f"(even an empty list, if verified split-free) before trusting this output.",
              file=sys.stderr)
    split_dates = KNOWN_SPLITS.get(ticker_key, [])
    if split_dates:
        entries = apply_split_correction(entries, split_dates)

    discrete = dedup_earliest_filed([e for e in entries if e["form"] == "10-Q" and 80 <= days_between(e) <= 100])
    annual = dedup_earliest_filed([e for e in entries if e["form"] == "10-K" and days_between(e) > 350])

    discrete.sort(key=lambda e: e["end"])
    annual.sort(key=lambda e: e["end"])

    quarters = list(discrete)
    for fy in annual:
        fy_end = fy["end"]
        fy_end_d = date.fromisoformat(fy_end)
        members = [
            q for q in discrete
            if date.fromisoformat(q["end"]) <= fy_end_d
            and (fy_end_d - date.fromisoformat(q["start"])).days <= 380
            and (fy_end_d - date.fromisoformat(q["end"])).days <= 280
        ]
        if len(members) == 3 and not any(q["end"] == fy_end for q in discrete):
            q4_val = round(fy["val"] - sum(m["val"] for m in members), 4)
            last_q = max(members, key=lambda m: m["end"])
            quarters.append({
                "start": last_q["end"], "end": fy_end, "val": q4_val,
                "accn": fy["accn"], "fy": fy.get("fy"), "fp": "Q4-derived",
                "form": "10-K-derived", "filed": fy["filed"],
            })

    quarters.sort(key=lambda e: e["end"])

    out = []
    for i, q in enumerate(quarters):
        if i < 3:
            continue
        ttm = round(sum(x["val"] for x in quarters[i - 3:i + 1]), 4)
        out.append({
            "quarter_end": q["end"], "quarter_eps": q["val"], "ttm_eps": ttm,
            "fp": q.get("fp"), "form": q["form"],
            "available_date": q["filed"],  # true first-disclosure date -- the point-in-time anchor
            "accn": q["accn"],
        })

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)

    print(f"{args.ticker}: {len(discrete)} discrete quarters, {len(annual)} annual filings, "
          f"{len(out)} TTM-EPS points written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
