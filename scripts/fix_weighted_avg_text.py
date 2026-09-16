#!/usr/bin/env python3
"""Sync the 가중평균 a card states to the one its own badges produce.

Why this exists. Stage 2B moves every metric's badge with the price - a stage
crosses a fifth of its band and the badge is rewritten. The 가중평균 those badges
imply is quoted in the box-key bullet, and nothing rewrites that. It was correct
on the analysis date and drifts from then on.

Eleven of the thirty cards that quote one had drifted, and five had drifted far
enough to cross a 7-tier boundary: ASML 3.0 -> 2.4, SNDK 3.40 -> 3.0, KLAC 3.44
-> 3.22, VZ 4.20 -> 4.6, QCOM 3.67 -> 4.11.

The average is arithmetic, so it is synced. **The headline tier label is not**,
and the distinction is the whole design of this script: the label carries the
documented +-1 discretionary move, so it is a judgment the analyst made and not
a number a script may overwrite. After syncing, all five of the crossers sit
within +-1 of their own label, which is where the convention allows them to be.
A card whose label drifts further than that is reported, never rewritten.

Weights come off the badge, the same place `build_valuation_base.py` reads them
- "(가중치 0.5)" halves a metric, "(가중치 0)" drops it, silence means 1.0 - and
the stages come off the same badges. So this reads only what the card itself
displays and cannot disagree with it.

The card's own decimal precision is preserved: a card that wrote 4.67 keeps two
places and one that wrote 4.1 keeps one, because rewriting 4.1 as 4.10 would
claim a precision the sentence never had.

Usage:
  python3 scripts/fix_weighted_avg_text.py [--cards-dir DIR] [--check]
    --check   write nothing; exit 1 if any card states an average it no longer has
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CARDS = Path.home() / "Workspace/stock-widgets-preview"

BINS = [(1.571, "초저평가"), (2.143, "저평가"), (2.714, "적정~저평가"), (3.286, "적정"),
        (3.857, "고평가~적정"), (4.429, "고평가"), (99, "초고평가")]
ROW = re.compile(r'data-metric="(\w+)".{0,400}?<span class="stage-badge[^"]*">([^<]*)</span>', re.S)
STATED = re.compile(r"(가중평균\s*(?:약\s*)?)(\d+\.\d+)(\s*/\s*5)")


def weighted(html):
    """(average, {metric: (stage, weight)}) from the card's own badges, or (None, {})."""
    seen = {}
    for m in ROW.finditer(html):
        badge = m.group(2)
        st = re.match(r"(\d)단계", badge)
        if not st:                       # 평가 보류 and anything without a stage
            continue
        w = 0.5 if "가중치 0.5" in badge else (0.0 if re.search(r"가중치\s*0(?!\.)", badge) else 1.0)
        seen[m.group(1)] = (int(st.group(1)), w)
    den = sum(w for _, w in seen.values())
    if not den:
        return None, seen
    return sum(s * w for s, w in seen.values()) / den, seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", default=str(DEFAULT_CARDS))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cards = Path(args.cards_dir)
    data = json.loads((cards / "site_data" / "stocks.json").read_text(encoding="utf-8"))

    changed, stale, skipped, far = [], [], 0, []
    for entry in data["tickers"]:
        tk = entry["ticker"]
        path = cards / entry["href"]
        html = path.read_text(encoding="utf-8")
        if not STATED.search(html):
            skipped += 1
            continue
        avg, seen = weighted(html)
        if avg is None:
            skipped += 1
            continue
        bin_label = next(n for c, n in BINS if avg < c)
        label = entry["tier"]["value"]
        if label in [n for _, n in BINS]:
            gap = [n for _, n in BINS].index(label) - [n for _, n in BINS].index(bin_label)
            if abs(gap) >= 2:
                far.append(f"{tk}: 라벨 '{label}' vs 배지산출 '{bin_label}' ({avg:.2f}) {gap:+d}단계")

        edits = [0]

        def one(m):
            places = len(m.group(2).split(".")[1])
            new = f"{avg:.{places}f}"
            if new == m.group(2):
                return m.group(0)
            edits[0] += 1
            return f"{m.group(1)}{new}{m.group(3)}"

        new_html = STATED.sub(one, html)
        if edits[0]:
            changed.append(f"{tk}({edits[0]})")
            if args.check:
                stale.append(tk)
            else:
                path.write_text(new_html, encoding="utf-8")

    if args.check:
        print(f"cards stating a 가중평균 their badges no longer produce: {len(stale)}"
              + (f" - {' '.join(stale)}" if stale else ""))
        for f in far:
            print(f"  LABEL more than one tier from the badges, left alone - {f}")
        return 1 if stale else 0
    print(f"updated {len(changed)}: {' '.join(changed) or '-'}")
    print(f"no 가중평균 stated, or no scored badge: {skipped}")
    for f in far:
        print(f"  label more than one tier from the badges, left alone - {f}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if "--check" in sys.argv else 0)
