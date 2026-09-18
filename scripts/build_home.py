#!/usr/bin/env python3
"""Refresh the data this repo's homepage reads, without touching its design.

What changed and why: this script used to overwrite index.html with preview's
rendered homepage. That kept the numbers honest but made preview the owner of
the page's design too, so every promotion silently discarded this repo's own
layout - the carousel, the Today section, the theme - and the public domain
ended up serving preview's plain page under a placeholder title. The design
belongs here; only the numbers belong to preview.

So the split is now explicit:
  - index.html, theme.css, today.html and friends are this repo's, hand-owned,
    and nothing generated writes to them;
  - stock-data.js carries the numbers, and this script rewrites exactly two
    regions of it from preview's rendered homepage.

stock-data.js is hand-written JS, not JSON: window.StockData is an object with
three keys and two functions hung off it afterwards. Only `stocks` and `meta`
are generated. `days` is the Today schedule - which tickers were featured on
which day - and is an editorial choice preview knows nothing about, so it is
preserved byte for byte, as are StockData.selectionReason and .quoteLabel,
which today.js calls at render time.

Usage: python3 scripts/build_home.py [--check]
  --check  write nothing; exit non-zero if stock-data.js is not up to date
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREVIEW_HOME = Path.home() / "Workspace/stock-widgets-preview/index.html"
OUT = REPO / "stock-data.js"

# What the page says about where its numbers came from. Preview runs the daily
# pipeline; this repo does not, so the page must not imply a live quote.
QUOTE_SOURCE = "preview 일일 파이프라인"
META_SOURCE = "저장 시세·공시 분석"

# The page groups non-comparable scores separately and marks the cheap end of
# the tier scale. Only these two tiers carry a valuation badge; everything else
# renders without one, which is what `null` means here.
VALUATION = {"저평가": "undervalued", "초저평가": "deep-value"}


class BuildError(Exception):
    """Refuse to write rather than publish a page built on a guess."""


def preview_data():
    """DATA, META and MACRO as preview's build_index.py inlined them.

    MACRO is null until preview's first macro run, and an indicator can be absent or
    carry status "unavailable" when a source failed. That is passed through rather than
    smoothed over: the strip is supposed to say a figure is missing, not invent one.
    """
    src = PREVIEW_HOME.read_text(encoding="utf-8")
    try:
        a = src.index("var DATA = [")
        b = src.index("\n  ];", a)
        rows = json.loads(src[a + len("var DATA = "): b + len("\n  ]")])
        m = re.search(r"var META = (\{.*?\});", src, re.S)
        meta = json.loads(m.group(1))
        mc = re.search(r"var MACRO = (\{.*?\}|null);\n", src, re.S)
        macro = json.loads(mc.group(1)) if mc else None
    except (ValueError, AttributeError) as e:
        raise BuildError(f"cannot read DATA/META from {PREVIEW_HOME}: {e}") from e
    if not rows:
        raise BuildError("preview's homepage lists no tickers")
    return rows, meta, macro


def money(v):
    """$1575.15 - no thousands separator, matching every price already on the page."""
    return f"${v:.2f}"


def cap(v):
    """$5.08T above a trillion, $930.7B below it - the two forms the page uses."""
    return f"${v / 1e12:.2f}T" if v >= 1e12 else f"${v / 1e9:.1f}B"


def record(r, session):
    """One preview row as the homepage's JS expects it.

    The thirteen fields preview publishes are carried across unchanged, so the
    page and preview can never disagree about a number. The five extra fields
    are derived here: two formatted strings beside their raw values (the tables
    sort on the raw ones), the session the prices came from, a label saying the
    quote is stored rather than live, and the valuation badge, which is a pure
    function of the tier preview already maintains.
    """
    out = dict(r)
    out["href"] = f"cards/{r['href']}"
    out["priceValue"] = r["price"]
    out["marketCapValue"] = r["marketCap"]
    out["price"] = money(r["price"])
    out["marketCap"] = cap(r["marketCap"])
    out["quoteDate"] = session
    out["quoteSource"] = QUOTE_SOURCE
    out["valuation"] = VALUATION.get(r["tier"])
    return out


def check_assets(rows):
    """A missing card is a 404 and a missing logo is a blank box - both render quietly."""
    missing = [r["ticker"] for r in rows
               if not (REPO / "cards" / f"{r['ticker']}_full_widget.html").exists()]
    if missing:
        raise BuildError(f"preview lists {len(missing)} card(s) this repo does not have: "
                         f"{', '.join(missing)}")
    have = {f.name.lower() for f in (REPO / "logos").glob("*.png")}
    no_logo = sorted(r["ticker"] for r in rows if f"{r['ticker'].lower()}.png" not in have)
    if no_logo:
        raise BuildError(f"no logos/<ticker>.png in this repo for: {', '.join(no_logo)}")


def splice(cur, rows, meta, macro):
    """Replace the `stocks` array and the `meta` object, leave everything else alone.

    The macro indicators ride inside `meta` rather than as a fourth top-level key. The
    page's strip needs them, but `meta` is already fully regenerated here, so reusing
    that one replacement keeps the file's structure untouched - there is no second
    splice boundary to get wrong, and a stray brace in this file blanks the whole page.
    """
    i, j = cur.find("stocks:["), cur.find("days:[")
    k = cur.find("meta:{")
    if i < 0 or j < 0 or k < 0 or not (i < j < k):
        raise BuildError("stock-data.js does not have stocks/days/meta in the expected order")
    # `end` is the brace that closes the meta object itself, not the object literal
    # around it: the file ends "...delayMinutes":null}};". json.dumps below writes
    # meta's own closing brace, so the tail has to resume AFTER it - slicing from
    # `end` instead of `end + 1` leaves "}}};" and the whole file stops parsing,
    # which takes window.StockData with it and blanks the page.
    end = cur.find("}};", k)
    if end < 0:
        raise BuildError("stock-data.js: no closing }}; after meta")

    body = ",\n  ".join(json.dumps(record(r, meta["priceSession"]), ensure_ascii=False)
                        for r in rows)
    m = dict(meta)
    m.update({"mode": "snapshot", "source": META_SOURCE, "asOf": meta["priceSession"],
              "updatedAt": None, "delayMinutes": None, "macro": macro})
    out = (cur[:i] + "stocks:[\n  " + body + "],\n"
           + cur[j:k] + "meta:" + json.dumps(m, ensure_ascii=False) + cur[end + 1:])

    # the Today schedule survived, and still points at tickers the page has
    kept = re.search(r"days:\[(.*?)\],?\s*meta:", out, re.S)
    if not kept:
        raise BuildError("the Today schedule did not survive the splice")
    listed = {r["ticker"] for r in rows}
    orphans = sorted(set(re.findall(r"'([A-Z][A-Z0-9._-]*)'", kept.group(1))) - listed)
    if orphans:
        raise BuildError(f"the Today schedule names tickers the homepage no longer lists: "
                         f"{', '.join(orphans)}")
    for fn in ("window.StockData.selectionReason=", "window.StockData.quoteLabel="):
        if out.count(fn) != 1:
            raise BuildError(f"{fn} is not intact after the splice")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        rows, meta, macro = preview_data()
        check_assets(rows)
        cur = OUT.read_text(encoding="utf-8")
        new = splice(cur, rows, meta, macro)
    except BuildError as e:
        sys.exit(f"build_home: {e}")

    if args.check:
        if new != cur:
            sys.exit("stock-data.js is stale - run python3 scripts/build_home.py")
        print(f"OK - stock-data.js matches preview ({len(rows)} tickers, {meta['priceSession']})")
        return
    if new == cur:
        print("stock-data.js already up to date")
        return
    OUT.write_text(new, encoding="utf-8")
    print(f"Wrote {OUT} ({len(rows)} tickers, session {meta['priceSession']})")


if __name__ == "__main__":
    main()
