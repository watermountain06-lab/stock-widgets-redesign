#!/usr/bin/env python3
"""List US-domestic filers that outrank a built card but have no card.

Why this exists. The candidate sweep was run once, at rank 53, and concluded
"nothing missing above the line" - correctly, because the line was IBM at
$229.21B. It was never re-run as the line moved down. Thermo Fisher ($225.5B)
sits directly below IBM and should have been rank 55; instead AXP ($219.3B) was
built next, and Marvell ($207.0B) and Amphenol ($206.9B) were skipped the same
way further down. Three cards were missing from ranks already assigned, and
nothing reported it - it surfaced only because someone happened to diff the
ranking while looking for the next ticker.

So the sweep is a command now, and it belongs before every new build rather than
once per project. It is deliberately cheap: one page fetch, then one SEC
submissions call per candidate that is not already ruled in or out, cached.

A candidate is reported when it is (a) not already built, (b) a domestic filer -
the form list contains 10-K and not 20-F/40-F, which is the project's stated
test, not the company's name or country - and (c) worth more than the smallest
card already built.

Amphenol is why the market cap is recomputed here rather than taken from the
listing: its row read $206.94B against a price of $83.92 and 1.233B shares, which
multiply to $103.5B. The listing was right and the share count was pre-split -
APH split 2:1 on 2026-09-03. A row whose own numbers do not multiply out is
flagged rather than trusted.

Usage:
  python3 scripts/check_rank_gaps.py [--data PATH] [--limit N] [--check]
    --check   exit 1 if any gap is found, printing one line per gap
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = Path.home() / "Workspace/stock-widgets-preview/site_data/stocks.json"
CACHE = HERE / "rank_gap_filer_cache.json"
LIST_URL = "https://stockanalysis.com/list/biggest-companies/"
SEC_UA = {"User-Agent": "stock-widgets research gptjhss@gmail.com"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"}

# The listing spells some tickers differently from the cards. Everything else that is
# "already built under another ticker" is caught by CIK, not by name - Alphabet alone is
# registered with SEC under GOOGL, GOOG, GOOGM and GOOGN, and the listing surfaced the
# last two as separate $4.1T companies until this check started deduping on CIK.
ALIAS = {"BRK.B": "BRKB", "BRK-B": "BRKB"}
NOT_US_EXCHANGE = {"2222.SR", "005930.KS"}


def listing():
    req = urllib.request.Request(LIST_URL, headers=BROWSER_UA)
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        c = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(c) >= 5 and c[0].isdigit():
            rows.append({"rank": int(c[0]), "ticker": c[1], "name": c[2], "cap": c[3], "price": c[4]})
    if not rows:
        sys.exit("could not parse the ranking page - its markup changed")
    return rows


def to_billions(s):
    s = s.replace(",", "").strip()
    mult = {"T": 1000.0, "B": 1.0, "M": 0.001}.get(s[-1:], None)
    return float(s[:-1]) * mult if mult else None


_TICKER_CIK = {}


def cik_of(ticker):
    """SEC's own ticker->CIK map. Scraping browse-edgar by ticker silently missed ARM."""
    if not _TICKER_CIK:
        req = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers=SEC_UA)
        for row in json.load(urllib.request.urlopen(req, timeout=60)).values():
            _TICKER_CIK[row["ticker"].upper()] = f"{row['cik_str']:010d}"
    return _TICKER_CIK.get(ticker.upper())


def is_domestic(ticker, cache):
    """The project's test: the SEC form list has 10-K and no 20-F/40-F."""
    if ticker in cache:
        return cache[ticker]
    try:
        cik = cik_of(ticker)
        if not cik:
            cache[ticker] = None
            return None
        sub = urllib.request.urlopen(urllib.request.Request(
            f"https://data.sec.gov/submissions/CIK{cik}.json", headers=SEC_UA), timeout=30)
        forms = set(json.load(sub)["filings"]["recent"]["form"])
        cache[ticker] = ("10-K" in forms) and not ({"20-F", "40-F"} & forms)
    except Exception:
        cache[ticker] = None
    time.sleep(0.3)
    return cache[ticker]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--limit", type=int, default=40, help="how far past the last card to look")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    built = {t["ticker"] for t in data["tickers"]}
    built_ciks = {c for c in (cik_of(t) for t in built) if c}
    caps = {t["ticker"]: (t["price"]["close"] or 0) * (t["shares"].get("usEquivalent") or 0) / 1e9
            for t in data["tickers"]}
    floor = min(c for c in caps.values() if c)      # the smallest card already built
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    gaps, odd, checked = [], [], 0
    for row in listing():
        cap = to_billions(row["cap"])
        if cap is None or cap < floor:
            break
        tk = ALIAS.get(row["ticker"], row["ticker"])
        if tk in built or tk in NOT_US_EXCHANGE:
            continue
        if cik_of(row["ticker"]) in built_ciks:      # another share class of a card we have
            continue
        checked += 1
        if checked > args.limit:
            break
        dom = is_domestic(row["ticker"], cache)
        if dom is None:
            odd.append((row, "could not determine filer type"))
            continue
        if not dom:
            continue                                 # foreign private issuer, out of scope
        price = to_billions(row["price"] + "B")
        shares = cap / price if price else None
        gaps.append((row, cap, shares))

    CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")

    if not gaps and not odd:
        print(f"no gaps: every US-domestic filer above ${floor:,.1f}B has a card")
        return 0
    for row, cap, shares in gaps:
        print(f"MISSING  {row['ticker']:<6} ${cap:8.2f}B  {row['name'][:44]}"
              f"   (implies {shares * 1e3:,.0f}M shares at {row['price']})")
    for row, why in odd:
        print(f"UNKNOWN  {row['ticker']:<6} {row['cap']:>9}  {why}")
    print("\nRecompute each from SEC cover shares x close before acting - a listing row whose "
          "price x shares does not equal its own cap usually means an unrecorded split.")
    return 1 if (gaps or odd) else 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if "--check" in sys.argv else 0)
