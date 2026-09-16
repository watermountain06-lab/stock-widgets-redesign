#!/usr/bin/env python3
"""Sync each card's narrative 52-week percentages to the ones the card itself maintains.

Why this exists. A card states its position in the 52-week range twice. The
52주위치 subscore's `subscore-desc` is rewritten every day by `update_cards.py`
from preview's `site_data/tech_state/{T}.json`, which the daily pipeline
regenerates - all 65 of those files are on the current session. The narrative
sentence beside it ("52주 저점 대비로는 708.4% 상승했고, 52주 고점 대비로는
23.7% 낮은 위치") was written once, at build time, from the build's own
`scripts/{T}_tech_signal.json` snapshot, and nothing has touched it since.
Those snapshots sit anywhere from 2026-08-27 to 2026-09-11.

So the two numbers separate, and they separate twice over: the price moves, and
the 252-bar window rolls its extreme bar out. On MU the gap reached 147.7pp -
the card said the stock was up 708.4% from its 52-week low while its own
subscore said 560.70%. 37 of 66 cards carried a contradiction of this kind.

The fix reads the card's own maintained value rather than any external file, so
the script cannot disagree with what the card displays, and a card whose
subscore is itself stale is not silently "corrected" to something else.

Sign is preserved per site, because the fleet writes the drawdown both ways:
"고점 대비 -54.1%" carries the minus, "고점 대비로는 23.7% 낮은 위치" carries the
word instead. Each mention is rewritten at the precision it already uses.

A hand-written rounded claim is left alone and reported - WMT's summary says
"52주 고점 대비 20% 조정" as prose, not as a measurement, and rounding it to
20.7% would read worse, not better.

Usage:
  python3 scripts/fix_52w_prose.py [--cards-dir DIR] [--check]
    --check   write nothing; exit 1 if any card contradicts its own subscore
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CARDS = Path.home() / "Workspace/stock-widgets-preview"

# the value the daily pipeline maintains, inside the 52주위치 subscore block
MAINTAINED = re.compile(
    r'52주위치.*?<div class="subscore-desc">저점 대비 \+([\d.]+)%, 고점 대비 -([\d.]+)%</div>',
    re.S)
LOW = re.compile(r"(52주 저점 대비(?:로는)? )(\+?)([\d.]+)%")
HIGH = re.compile(r"(52주 고점 대비(?:로는)? )(-?)([\d.]+)%")
# rounded prose, not a measurement: a whole number with no decimal point
ROUNDED = re.compile(r"^\d+$")


def retune(html, pat, want, keep):
    """Rewrite every mention outside the maintained block, at its own precision."""
    edits = [0, []]

    def one(m):
        lead, sign, num = m.group(1), m.group(2), m.group(3)
        if m.start() in keep:
            return m.group(0)
        if ROUNDED.match(num):
            edits[1].append(f"{lead.strip()} {num}% (rounded prose, left alone)")
            return m.group(0)
        places = len(num.split(".")[1]) if "." in num else 0
        new = f"{want:.{places}f}"
        if new == num:
            return m.group(0)
        edits[0] += 1
        return f"{lead}{sign}{new}%"

    return pat.sub(one, html), edits[0], edits[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", default=str(DEFAULT_CARDS))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cards = Path(args.cards_dir)
    data = json.loads((cards / "site_data" / "stocks.json").read_text(encoding="utf-8"))

    changed, notes, skipped = [], [], 0
    for entry in data["tickers"]:
        tk = entry["ticker"]
        path = cards / entry["href"]
        html = path.read_text(encoding="utf-8")
        m = MAINTAINED.search(html)
        if not m:                       # 상장 이후 wording, or no technical scorecard
            skipped += 1
            continue
        rise, draw = float(m.group(1)), float(m.group(2))
        # the maintained sentence is itself a match for both patterns - leave it be
        keep = {x.start() for p in (LOW, HIGH) for x in p.finditer(html)
                if m.start() <= x.start() < m.end()}

        new, n1, r1 = retune(html, LOW, rise, keep)
        new, n2, r2 = retune(new, HIGH, draw, keep)
        for r in r1 + r2:
            notes.append(f"{tk}: {r}")
        if n1 + n2:
            changed.append(f"{tk}({n1 + n2})")
            if not args.check:
                path.write_text(new, encoding="utf-8")

    if args.check:
        print(f"cards contradicting their own 52주위치 subscore: {len(changed)}"
              + (f" - {' '.join(changed)}" if changed else ""))
        for n in notes:
            print(f"  note {n}")
        return 1 if changed else 0
    print(f"updated {len(changed)}: {' '.join(changed) or '-'}")
    print(f"no technical scorecard to read: {skipped}")
    for n in notes:
        print(f"  note {n}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if "--check" in sys.argv else 0)
