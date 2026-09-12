#!/usr/bin/env python3
"""Keep the header price beside the description instead of letting it wrap below.

`.header-top` is a two-child flex row — `.ticker-block` on the left, `.price-block`
on the right — with `flex-wrap: wrap`. `.ticker-block` could not shrink (no
`flex` basis, and flex children default to `min-width: auto`), so once a card's
`company-sub` got long enough the line overflowed and the price dropped onto a
second row, left-aligned.

That is why the early cards look right and the later ones do not: NVDA's
description is 43 characters and META's is 41, while RTX is 365, HD 337 and
SNDK 314. Nothing about the price markup changed - the descriptions grew.

The fix lets the left column shrink and wrap its own text, pins the price block
to its natural width, and keeps `margin-left: auto` so it stays right-aligned
even on a viewport narrow enough to still wrap.

Usage: python3 scripts/fix_header_price_row.py [--check] [--cards-dir DIR]
"""
import argparse
import sys
from pathlib import Path

PREVIEW = Path.home() / "Workspace/stock-widgets-preview"
OLD_PRICE = "  .price-block { text-align: right; }"
NEW_PRICE = "  .price-block { text-align: right; flex: 0 0 auto; margin-left: auto; }"
OLD_TICKER = "  .ticker-block { display: flex; align-items: center; gap: 16px; }"
NEW_TICKER = ("  .ticker-block { display: flex; align-items: center; gap: 16px; flex: 1 1 320px; min-width: 0; }\n"
              "  .ticker-block > div { min-width: 0; }")


def convert(text):
    if NEW_PRICE in text and "flex: 1 1 320px" in text:
        return text, 0
    if text.count(OLD_PRICE) != 1 or text.count(OLD_TICKER) != 1:
        raise RuntimeError("header CSS is not in the expected shape")
    return text.replace(OLD_PRICE, NEW_PRICE).replace(OLD_TICKER, NEW_TICKER), 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--cards-dir", default=str(PREVIEW))
    args = ap.parse_args()
    changed, skipped, failed = [], [], []
    for f in sorted(Path(args.cards_dir).glob("*_full_widget.html")):
        t = f.name.replace("_full_widget.html", "")
        s = f.read_text(encoding="utf-8")
        try:
            out, n = convert(s)
        except RuntimeError as e:
            failed.append(f"{t}: {e}")
            continue
        if n == 0:
            skipped.append(t)
            continue
        changed.append(t)
        if not args.check:
            f.write_text(out, encoding="utf-8")
    if failed:
        print("FAILED - nothing written for these:")
        for x in failed:
            print("  -", x)
        sys.exit(2)
    print(f"{'would convert' if args.check else 'converted'} {len(changed)}: {' '.join(changed) or '-'}")
    print(f"already fixed: {len(skipped)}")
    if args.check and changed:
        sys.exit(1)


if __name__ == "__main__":
    main()
