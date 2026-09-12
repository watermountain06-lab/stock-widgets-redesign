#!/usr/bin/env python3
"""Bring this repo's cards up to date with their preview copies.

Preview runs the daily pipeline; this repo does not. That was tolerable while
this repo's homepage also sat at each card's build day, but once the homepage
started rendering preview's data (scripts/build_home.py) the two disagreed in
public - ANET read $199.59 on the homepage and $192.93 on its own card. This
closes that gap by making preview the single source for card content.

The only difference between a preview card and its copy here is the back-bar's
link to the homepage: preview serves cards from the repo root, this repo serves
them from cards/. Everything else - prices, MA arrays, tech score, as-of
labels, the valuation tab - is whatever preview's pipeline last wrote.

Usage: python3 scripts/sync_cards.py [--check] [--exclude TICKER ...]
  --check    report what would change, write nothing
  --exclude  skip a card being written by something else right now
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREVIEW = Path.home() / "Workspace/stock-widgets-preview"
DEST = REPO / "cards"
SRC_LINK = '<a class="back-bar-left" href="index.html">'
DST_LINK = '<a class="back-bar-left" href="../index.html">'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--exclude", nargs="*", default=[])
    args = ap.parse_args()
    skip = {t.upper() for t in args.exclude}

    src_files = sorted(PREVIEW.glob("*_full_widget.html"))
    if not src_files:
        sys.exit(f"no cards found in {PREVIEW}")

    new, updated, unchanged, skipped = [], [], [], []
    for src in src_files:
        ticker = src.name.replace("_full_widget.html", "")
        if ticker in skip:
            skipped.append(ticker)
            continue
        body = src.read_text(encoding="utf-8")
        if body.count(SRC_LINK) != 1:
            sys.exit(f"{src.name}: expected exactly 1 back-bar home link, found {body.count(SRC_LINK)}")
        body = body.replace(SRC_LINK, DST_LINK)
        dst = DEST / src.name
        if not dst.exists():
            new.append(ticker)
        elif dst.read_text(encoding="utf-8") != body:
            updated.append(ticker)
        else:
            unchanged.append(ticker)
            continue
        if not args.check:
            dst.write_text(body, encoding="utf-8")

    # a card here with no preview copy is not an error - it may be mid-build -
    # but it will not be updated by anything, so say so out loud
    orphans = sorted(p.name.replace("_full_widget.html", "") for p in DEST.glob("*_full_widget.html")
                     if not (PREVIEW / p.name).exists())

    verb = "would add" if args.check else "added"
    print(f"{verb} {len(new)}: {' '.join(new) or '-'}")
    print(f"{'would update' if args.check else 'updated'} {len(updated)}: {' '.join(updated) or '-'}")
    print(f"unchanged {len(unchanged)}")
    if skipped:
        print(f"skipped (in flight) {len(skipped)}: {' '.join(skipped)}")
    if orphans:
        print(f"NOT IN PREVIEW, left alone {len(orphans)}: {' '.join(orphans)}")
    if args.check and (new or updated):
        sys.exit(1)


if __name__ == "__main__":
    main()
