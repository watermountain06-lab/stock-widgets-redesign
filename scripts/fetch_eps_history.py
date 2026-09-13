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
    "TXN": [],    # last split 2000-05-23 (2-for-1) -- WebSearch confirmed 2026-09-12 (6 splits between 1973 and 2000: 1973, 1987 3-for-1, 1995, 1997, 1999-08-17, 2000-05-23, none since), far outside both this data's 5y price window and TXN's XBRL EarningsPerShareDiluted history (earliest end 2007-12-31). Confirmed empirically the same day: of 119 (start,end) groups in the full XBRL EPS history only 5 carry a duplicate-value disagreement, all four quarters/cumulatives of FY2016 at ratios 1.039-1.062 (an ASU-era restatement, not a split signature), and 0 groups exceed 1.3x.
    "C": [("2011-05-09", 0.1)],  # Citigroup's 1-for-10 REVERSE split -- note the ratio is 0.1, not 10, because a reverse split moves per-share figures the OTHER way: split_ratio() multiplies the accumulated ratio for every entry filed BEFORE the effective date and apply_split_correction() then divides val by it, so a pre-split entry is scaled UP (val / 0.1 = val * 10), which is the correction a reverse split needs. Effective at 4:10 p.m. ET Friday 2011-05-06, split-adjusted trading on the NYSE from Monday 2011-05-09 (Citi 8-K accn 0001193125-11-131957 and the 2011 10-K); 2011-05-09 is used as the boundary to match the split-adjusted TRADING date convention already used for ANET/KLAC above. Unlike TXN/GS/PM, this split does NOT predate Citi's XBRL EarningsPerShareDiluted history (which starts at end 2007-12-31), so an empty list would be wrong: confirmed empirically 2026-09-12 that 10 of 119 (start,end) groups have a duplicate-value ratio >1.3, and 9 of them are a clean ~10x step landing exactly on this boundary (e.g. Q1 2011 filed 2011-05-05 val 0.10 -> filed 2012-02-24 val 0.99 = 9.9x; FY2010 filed 2011-02-25 val 0.35 -> filed 2012-02-24 val 3.54 = 10.11x; the residual from 10.00 is the source data's own 2-decimal rounding on sub-dollar pre-split values). The 10th group (2020-04-01~2020-06-30, ratio 1.32: 0.50 filed 2020-08-05 -> 0.38 filed 2021-02-26) is a genuine COVID-era restatement, not a split, and "earliest filed wins" keeps the as-first-disclosed 0.50 there, which is the point-in-time-correct choice. The split itself is far outside this data's 5y price window (from 2021-09-13), so it changes nothing in this card's own backtest -- it is recorded so the table is correct for any longer-history use.
    "KLAC": [("2026-06-12", 10)],  # 10-for-1 forward split -- confirmed 2026-09-12 from KLA's OWN filings, not from an aggregator. The FY2026 Q4 earnings release (8-K accn 0000319201-26-000024, 2026-07-28) states "On June 11, 2026, after the market close, the company effected a ten-for-one stock split ... Share and per share information throughout this press release have been retroactively adjusted", and the FY2026 10-K tags us-gaap:StockholdersEquityNoteStockSplitConversionRatio1 at 2026-06-11. Boundary is the split-adjusted TRADING date 2026-06-12 because split_ratio() compares each XBRL entry's FILED date, and it sits cleanly between the last pre-split filing (2026-04-30 Q3 FY26 10-Q, diluted EPS 9.12 -> 0.912) and the first post-split one (2026-08-06 FY26 10-K, diluted EPS 3.66 as-filed). Confirmed empirically the same day: EarningsPerShareDiluted carries BOTH bases for overlapping periods (FY2024 20.28 and 2.03; FY2025 30.37 and 3.04), every duplicate group a clean ~10x step at this one boundary. Share count corroborates: 130,627,521 (10-Q filed 2026-04-30) -> 1,306,546,783 (10-K filed 2026-08-06).
    "AMAT": [],   # last split 2002-04-17 (2-for-1) -- WebSearch confirmed 2026-09-12 (AMAT's own IR "Splits & Offerings" page lists nothing after it; the 2000-03-16 2-for-1 was the one before), which predates AMAT's XBRL EarningsPerShareDiluted history entirely (earliest end 2007-10-28) as well as this data's 5y price window. Confirmed empirically 2026-09-12: 0 of 121 (start,end) groups in the full XBRL EPS history carry a duplicate-value ratio >1.3 -- no retroactive per-share restatement of any kind.
    "INTC": [],   # last split 2000-07-30 (2-for-1, record date 2000-07-02; 13 forward splits between 1973 and 2000, none since) -- WebSearch confirmed 2026-09-12 against Intel's own investor "Stock Splits" page. Far outside INTC's XBRL EarningsPerShareDiluted history (earliest end 2007-12-29) and this data's 5y price window. Confirmed empirically 2026-09-12: 0 of 112 (start,end) groups carry a duplicate-value ratio >1.3.
    "GE": [("2021-08-02", 0.125)],  # 1-for-8 REVERSE split -- ratio is 0.125, not 8, for the same reason as C above: split_ratio() multiplies the accumulated ratio for entries filed BEFORE the boundary and apply_split_correction() divides by it, so a pre-split entry is scaled UP (val / 0.125 = val * 8), which is what a reverse split needs. GE completed the split on 2021-07-30 and the stock traded split-adjusted from 2021-08-02 (GE's own "GE COMPLETES ONE-FOR-EIGHT REVERSE STOCK SPLIT" release, 2021-07-30; ~8.8B shares -> ~1.1B); 2021-08-02 is used to match the split-adjusted TRADING date convention already used for ANET/KLAC/C. Confirmed empirically 2026-09-12: of 127 (start,end) groups, 15 have a duplicate-value ratio >1.3, and the 10 covering 2019-2021 periods are all clean ~8.0x steps landing exactly on this boundary (e.g. FY2020 0.58 filed 2021-02-12 -> 4.63 filed 2022-02-11 = 8.00x; Q2 2021 -0.14 filed 2021-07-27 -> -1.08 filed 2022-02-11 = 8.21x, the residual being 2-decimal rounding on sub-dollar pre-split values). The other 5 are NOT splits: four 2017 periods (Baker Hughes/Transportation discontinued-operations restatements, ratios 1.4-7.0 including a sign flip, all pre-dating the 5y window) and 2022 Q3 (-0.21 filed 2022-10-25 -> 0.08 filed 2023-04-25, the GE HealthCare spin-off's discontinued-ops restatement). "Earliest filed wins" keeps the as-first-disclosed value in each of those, which is the point-in-time-correct choice.
    #
    # CAUTION for anyone using GE in a PER backtest: the split table above makes GE's EPS
    # series internally consistent, but GE's PRICE series is not comparable across this
    # window for a different reason -- two major spin-offs INSIDE it (GE HealthCare
    # 2023-01-04, GE Vernova 2024-04-02) each removed a large block of earning power from
    # the share price while the point-in-time EPS series still carries those businesses
    # until the later restatement. See compute_valuation_ic.py for how that is handled.
    "IBM": [],    # last split 1999-05-26 (2-for-1) -- WebSearch confirmed 2026-09-12 -- far outside both this data's 5y price window and IBM's XBRL EarningsPerShareDiluted history (earliest end 2007-12-31). The 2021-11-03 Kyndryl separation inside the 5y window is NOT a split: IBM distributed 80.1% of Kyndryl (NYSE: KD) as a pro rata dividend, one KD share per five IBM shares held at the 2021-10-25 record date (IBM newsroom "IBM Completes the Separation of Kyndryl", 2021-11-03). That ratio is the rate at which a NEW security was handed to IBM's holders, not a proportional split of IBM's own outstanding shares, so nothing in IBM's per-share history is retroactively restated by it -- the same distinction already documented for DELL's VMware Class V exchange, RTX's 2020 Carrier/Otis spin-merge, GEV and SNDK above. (The vendor price-adjustment factor for a spin-off does land on the PARENT here, unlike GEV/SNDK, and Yahoo's series already carries it: there is no discontinuity around the event -- 2021-11-02 close 120.63, 11-03 close 121.54, 11-04 close 120.85.) Confirmed empirically 2026-09-12: of 113 (start,end) groups in the full XBRL EarningsPerShareDiluted history (2007-12-31 through 2026-06-30), ZERO carry any duplicate-value disagreement at all, let alone a ratio >1.3 -- so no retroactive per-share restatement of any kind exists anywhere in the series. Note that the Kyndryl separation DID restate the revenue and pre-tax-income series (FY2020 revenue 73,620 as filed 2021-02-23 -> 55,179 as restated 2022-02-22), which matters for multi-year growth comparisons but not for per-share splits.
    "AXP": [],    # American Express has never split within this data's XBRL window. Last true split was the 3-for-1 on 2000-05-10 (AXP's own investor-relations stock-split history lists 1977, 1987, 2000 and nothing since), far outside both this data's 5y price window and AXP's EarningsPerShareDiluted history. The 2005-10-01 Ameriprise Financial (AMP) spin-off that some aggregators book as a ~0.83 price-adjustment factor is NOT a split: AXP distributed all AMP shares to its own holders at one AMP share per five AXP shares, a distribution of a NEW security to the parent's holders rather than a proportional split of AXP's own outstanding shares, so nothing in AXP's per-share history is retroactively restated by it -- the same distinction already documented for DELL's VMware Class V exchange, RTX's 2020 Carrier/Otis spin-merge, GEV and SNDK above. Confirmed empirically 2026-09-12 against the full XBRL duplicate-ratio sweep: 252 entries across 114 (start,end) period groups, only 4 groups disagree at all and all four sit at ratios 1.0067-1.0075 (2017 quarters where a 2018/2019 comparative column re-rounded 1.34->1.35, 2.80->2.82, 4.30->4.33, 1.50->1.51) -- sub-cent source rounding, not a restatement. ZERO groups above 1.3x anywhere in the series.
    "LIN": [],    # Linde plc has never split. Linde AG's pre-2018 German history is irrelevant here because this CIK (0001707925) is the Irish holding company formed for the Praxair-Linde AG merger, and its per-share series is Praxair's (the accounting acquirer's) continued at 1:1; Praxair's last split was the 2-for-1 on 2002-07-01, far outside both this data's 5y price window and the XBRL EarningsPerShareDiluted history (earliest end 2016-12-31). Confirmed empirically 2026-09-12 against the full XBRL duplicate-ratio sweep: 115 entries across 60 (start,end) period groups, only 4 groups disagree at all and NONE at a split signature. All four sit at the 2018-10-31 merger boundary (2017Q3, 2017Q4, 2018 9M, 2018Q3) at ratios -0.1247, -0.0024, -0.0128 and -0.0087 -- negative, mutually inconsistent, and nothing like a common multiple. They are the pre-merger Linde plc SHELL entity's own EPS as filed in its fy2017/fy2018 10-Q/10-K (-11.63, -45.17, -375.88, -182.16: a holding company with no operations and a token share count) versus the successor-basis figures restated onto Praxair's share base from the FY2018 10-K on (1.45, 0.11, 4.82, 1.58). An entity-basis change, not a split, and it pre-dates this data's 5y price window (from 2021-09-13) entirely. ZERO groups above 1.3x anywhere in the series.
    "CRWD": [("2026-07-02", 4)],  # 4-for-1 forward stock split, effected as a stock dividend -- confirmed 2026-09-12 from CrowdStrike's OWN filings, not an aggregator: the 8-K filed 2026-06-03 (accn 0001535527-26-000022) announced that the Board approved a four-for-one split of the Class A common stock in the form of a stock dividend, record date 2026-06-25, three additional shares per held share distributed after the close of business on 2026-07-01, so split-adjusted trading begins 2026-07-02. Boundary is that split-adjusted TRADING date because split_ratio() compares each XBRL entry's FILED date, and 2026-07-02 sits cleanly between the last pre-split filing (2026-06-04, Q1 FY2027 10-Q, diluted EPS 0.11 as-filed) and the first post-split one (2026-08-27, Q2 FY2027 10-Q). Confirmed empirically the same day against the XBRL WeightedAverageNumberOfDilutedSharesOutstanding duplicates, which give an EXACT 4.0000x step on both overlapping periods (2025-02-01~2025-07-31: 249,182,000 filed 2025-08-28 -> 996,730,000 filed 2026-08-27; 2025-05-01~2025-07-31: 249,909,000 -> 999,634,000), and against the dei cover count (254,564,820 at 2026-05-28 -> 1,023,934,842 at 2026-08-20). CAUTION: the EarningsPerShareDiluted duplicate sweep alone gives ratios of ~4.4x, not 4.0x, for those same two periods -- that is NOT a different split ratio but a SEPARATE, overlapping revision: the FY2026 10-K (filed 2026-03-05) corrected an immaterial error in the timing of stock-based compensation recognition for FY2022/FY2023 awards (graded-vesting attribution instead of straight-line), which restated FY2024 net income 89,327->72,181, FY2025 -19,271->-15,241 and H1 FY2026 -187,882->-174,417. Split and restatement must not be conflated.
    "VZ": [],     # Verizon has never split within this data's XBRL window. Last true split was the 2-for-1 on 1998-06-30 (the Bell Atlantic-era split that carried into Verizon; the company has declared none since the 2000 Bell Atlantic/GTE merger created Verizon), far outside both this data's 5y price window and the XBRL EarningsPerShareDiluted history (earliest end 2007-12-31). The 2006 Idearc, 2008 FairPoint and 2010 Frontier line-exchange spin-offs inside the earlier history are NOT splits: each handed a NEW security (or another company's shares) to Verizon's own holders rather than proportionally splitting Verizon's outstanding shares, so nothing in the per-share series is retroactively restated by them -- the same distinction already documented for DELL's VMware Class V exchange, RTX's 2020 Carrier/Otis spin-merge, GEV, SNDK, IBM's Kyndryl separation and AXP's Ameriprise spin-off above. Confirmed empirically 2026-09-12 against the full XBRL duplicate-ratio sweep: 326 entries across 124 (start,end) period groups, of which only 10 disagree at all and every one of those sits in 2008-2010 at mutually inconsistent ratios (-2.935, 1.074, 1.333, 1.115, 1.051, 1.143, -0.269, -13.0, 0.167, 1.348 -- including sign flips, which no split can produce). Those are the spin-off discontinued-operations restatements plus the FASB noncontrolling-interest reclass, not a split signature. Restricting the sweep to end >= 2011-01-01 leaves 104 period groups with ZERO disagreement, so the entire 5y price window (from 2021-09-13) is on one consistent per-share basis.
    "AMGN": [],   # Amgen has never split within this data's XBRL window. Last true split was the 2-for-1 completed 1999-11-22 (the second of two 2-for-1 splits Amgen declared in 1999, the first declared 1999-01-26; earlier splits 1995, 1991 3-for-1, 1990) -- WebSearch confirmed 2026-09-12 against Amgen's own investor-relations stock-split filing. That predates Amgen's XBRL EarningsPerShareDiluted history entirely (earliest end 2007-12-31) and this data's 5y price window (from 2021-09-13). The 2023-10-06 Horizon Therapeutics acquisition inside the window is NOT a split and triggers no per-share restatement: it was an all-cash purchase at $116.50 per Horizon share funded with ~$23.8B of senior notes plus a $4B term loan, so no Amgen shares were issued and nothing in Amgen's own per-share history moves. Confirmed empirically 2026-09-12 against the full XBRL duplicate-ratio sweep: 324 entries across 123 (start,end) period groups, and ZERO groups carry any duplicate-value disagreement at all -- not one above 1.05x, let alone 1.3x. Cross-checked against WeightedAverageNumberOfDilutedSharesOutstanding as well (111 (start,end) groups, 0 disagreements above 1.05x; the diluted count drifts smoothly 581M -> 536M -> 544M across 2021-2026 with no discontinuity), which is the tag that settled CRWD's ambiguous ratio above.
    "CRM": [],    # Salesforce has never split within this data's XBRL window. Its ONLY split ever is the 4-for-1 announced 2013-03-21 (board approval), record date 2013-04-03, additional shares distributed 2013-04-17, split-adjusted trading from 2013-04-18 -- Salesforce's own press release "salesforce.com Announces Four-for-One Stock Split", WebSearch confirmed 2026-09-12. That is far outside this data's 5y price window (from 2021-09-13), though NOT outside the XBRL EarningsPerShareDiluted history (earliest end 2008-01-31), so the duplicate sweep does see it. Confirmed empirically 2026-09-12: of 122 (start,end) period groups, 15 disagree above 1.05x and they split into two distinct, separately-explained sets. (a) EIGHT groups covering FY2012-FY2013 periods are the 2013 split, and the large-magnitude pairs pin the ratio EXACTLY: FY2012 -1.92 filed 2013-03-08 -> -0.48 filed 2014-03-05 = 4.0000x, 9M-FY2013 -1.78 -> -0.45 = 3.956x, Q3-FY2013 -1.55 -> -0.39 = 3.974x. The noisier ratios in that same set (4.5, 4.2, 3.5) are all sub-$0.25 values where 2-decimal source rounding dominates (-0.09 -> -0.02 reads as 4.5x), the same rounding artifact already documented for NVDA's 2016-era quarters in this module's docstring -- not a different ratio. (b) SEVEN groups covering FY2017-FY2018 periods are NOT a split and must not be conflated with one: their values move UPWARD in the later filing (FY2018 0.17 filed 2018-03-09 -> 0.49 filed 2019-03-08; Q3-FY2018 0.07 -> 0.14; H1-FY2018 0.01 -> 0.06) at mutually inconsistent ratios of 1.77-6.0, and no split can raise a per-share figure. That is the ASC 606 full-retrospective revenue-recognition adoption in FY2019 restating the FY2017/FY2018 comparatives, the same split-versus-restatement distinction documented for CRWD above. Both sets end at 2018-01-31 at the latest: restricting the sweep to end >= 2018-02-01 leaves ZERO disagreements, so the entire 5y price window sits on one consistent per-share basis and the empty list is correct.
    "TMO": [],    # Thermo Fisher has never split within this data's XBRL window. Its full EarningsPerShareDiluted history (360 entries, earliest end 2007-12-31, 122 (start,end) groups) has only 2 groups whose values disagree at all, both from 2009 and both a units-tagging error in the original 2009-10-30 10-Q (accn 0000097745-09-000050 tagged 9M EPS as 1360000 and Q3 EPS as 530000, i.e. a literal 1,000,000x scale error, corrected to 1.36 / 0.53 in the 2010-11-05 refiling) -- a 1e6 ratio is not a split signature, and 2009 pre-dates this data's 5y price window either way. Last true split was the 2-for-1 effective 1996-11-15 under the old Thermo Electron; confirmed empirically 2026-09-13 that 0 groups show a split-shaped (1.3x-10x) duplicate ratio anywhere in the series.
    "MRVL": [],   # Marvell has never split. Confirmed empirically 2026-09-13, and this is the cleanest sweep result on this list: of the 40 (start,end) groups in the full XBRL EarningsPerShareDiluted history, ZERO disagree at all -- not zero above 1.3x, zero disagreements of any size -- and EarningsPerShareBasic is identical (40 groups, 0 disagreements). With no restatement anywhere in the series there is nothing for a split ratio to hide behind. The one discontinuity a reader might mistake for a split is the FY2021->FY2022 diluted share-count step, 668.8M (end 2021-01-30) -> 796.9M (end 2022-01-29), +19.2%: that is the April 2021 Inphi acquisition's stock consideration, and the same transaction is when Marvell Technology Group Ltd. (Bermuda) was reorganized under a new Delaware holding company, Marvell Technology, Inc. Both are a real share issuance / a legal-domicile change, NOT a proportional split -- a split retroactively restates every prior per-share figure and the sweep above proves none was restated, and +19.2% is not a split-shaped ratio in any case. Same split-versus-corporate-action distinction already documented for DELL's VMware Class V exchange, RTX's 2020 Carrier/Otis spin-merge and SNDK's Western Digital spin-off above, except the artifact here is an acquisition-plus-redomiciliation rather than a spin-off. Share counts thereafter run 851.4M -> 861.3M -> 865.5M -> 869.7M (FY2026), i.e. smooth low-single-digit drift, and the later step to 921.2M in Q2 FY2027 is the Celestial AI acquisition's ~27.2M-share consideration (closed 2026-02-02) -- again an issuance, not a split.
    "APH": [("2014-10-10", 2), ("2021-03-05", 2), ("2024-06-12", 2), ("2026-09-03", 2)],  # FOUR 2-for-1 forward splits, all effected as stock dividends -- confirmed 2026-09-13 from Amphenol's OWN filings, not an aggregator, and every boundary is the split-adjusted TRADING date because split_ratio() compares each XBRL entry's FILED date. (1) Q3 2014 10-Q (accn 0001104659-14-076813) Note 1: "a two-for-one stock split in the form of a stock dividend, payable to stockholders of record as of October 2, 2014, which was paid on October 9, 2014", so split-adjusted trading from 2014-10-10; the boundary sits cleanly between the last pre-split filing (2014-08-06 Q2 10-Q, Q2'14 EPS 1.09 -> 0.54) and the first post-split one (2014-11-05). (2) Q1 2021 10-Q (accn 0001558370-21-005338) Note 1: announced 2021-01-27, record 2021-02-16, "additional shares were distributed on March 4, 2021, and the Company's Common Stock began trading on a split-adjusted basis on March 5, 2021"; last pre-split filing 2021-02-10 (FY2020 10-K, EPS 3.91 -> 1.96), first post-split 2021-04-30. (3) Q2 2024 10-Q (accn 0001558370-24-010246) Note 1: announced 2024-05-20, record 2024-05-31, "additional shares were distributed on June 11, 2024, and the Common Stock began trading on a split-adjusted basis on June 12, 2024"; last pre-split filing 2024-04-26 (Q1'24 EPS 0.87 -> 0.44), first post-split 2024-07-26. (4) The 8-K filed 2026-09-04 (accn 0001104659-26-105485, Item 8.01) states the two-for-one split announced 2026-08-06, record 2026-08-17, distributed 2026-09-02, "has now been effected", so split-adjusted trading from 2026-09-03; the same filing restates the quarterly dividend $0.25 -> $0.125 per share. CAUTION: this fourth split is NOT yet visible in the EPS duplicate sweep, because no periodic filing has been made since it took effect (the latest is the 2026-07-31 Q2 10-Q) -- it is recorded here from the 8-K so the table is already right when the Q3 10-Q lands, and it is exactly why APH's SEC cover count (1,232,983,457 as of 2026-07-28) is PRE-split while the real tradeable count is 2,465,966,914. Using the raw cover count halves the market cap. Confirmed empirically 2026-09-13 for the first three: 313 entries across 123 (start,end) groups, 24 of which disagree above 1.05x, and every single one is a clean ~2.00x step landing on exactly one of those three boundaries (2014: FY2013 3.92 filed 2014-02-21 -> 1.96 filed 2015-02-20 = 2.000x; 2021: FY2019 3.75 filed 2021-02-10 -> 1.88 filed 2022-02-09 = 1.995x; 2024: FY2022 3.06 filed 2024-02-07 -> 1.53 filed 2025-02-07 = 2.000x). The residuals from 2.000 (the observed range is 1.975-2.024) are the source data's own 2-decimal rounding on sub-dollar quarterly values, the same artifact documented for NVDA's 2016-era quarters in this module's docstring -- ZERO groups anywhere in the series show a non-split restatement signature. Cover counts corroborate the two in-history splits independently: 299,576,711 (filed 2021-02-10) -> 597,615,720 (2021-04-30) and 600,603,947 (2024-04-26) -> 1,204,288,801 (2024-07-26), both exactly 2x. Yahoo's 5y daily series is already adjusted for every split in the window (which starts 2021-09-13, so only the 2024 and 2026 splits fall inside it): the largest single-day moves in the whole window are -12.6% on 2025-01-27 (the DeepSeek AI-capex selloff) and +10.2% on 2025-04-09, and there is no discontinuity at 2026-09-03 (09-02 close 80.04 -> 09-03 close 82.07).
    "TMUS": [],   # T-Mobile US has never split within this data's XBRL window. Its full XBRL EarningsPerShareDiluted history (2008-12-31 through 2026-06-30, 116 (start,end) groups) has 8 groups with a duplicate-value ratio >1.3, and every one of them falls in 2011-2013 and is a restatement artifact of the MetroPCS reverse-merger recapitalization (completed 2013-04-30), not a split: most involve a sign flip from a small positive to a large negative (e.g. FY2011 $0.82 filed 2012-02-29 -> -$8.81 filed 2014-02-25; Q3 2012 $0.52 -> -$14.45), which is the predecessor-entity restatement that followed TMUS becoming the accounting acquirer, and no group at all shows a clean 2x/4x/10x step. From 2014 onward the series has zero flagged groups. The 1-for-2 reverse split MetroPCS itself did on 2013-04-30 as part of that recapitalization pre-dates both this data's 5y price window (from 2021-09-10) and TMUS's own post-combination per-share series. Confirmed empirically 2026-09-13.
}

CIKS = {
    "NVDA": "0001045810", "AAPL": "0000320193", "AMZN": "0001018724",
    "AVGO": "0001730168", "GOOGL": "0001652044", "META": "0001326801",
    "MSFT": "0000789019", "TSLA": "0001318605", "WMT": "0000104169",
    "AMD": "0000002488",
    # Added 2026-09-12 for the 54-card valuation-IC expansion (see compute_valuation_ic.py).
    # Resolved from SEC's own www.sec.gov/files/company_tickers.json, not typed by hand.
    "AMAT": "0000006951", "ANET": "0001596532", "CAT": "0000018230",
    "CSCO": "0000858877", "DELL": "0001571996", "GE": "0000040545",
    "GS": "0000886982", "HD": "0000354950", "INTC": "0000050863",
    "KO": "0000021344", "MRK": "0000310158", "MS": "0000895421",
    "PANW": "0001327567", "RTX": "0000101829", "WFC": "0000072971",
    "AXP": "0000004962",
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
