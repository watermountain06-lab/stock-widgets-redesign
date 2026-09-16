#!/usr/bin/env python3
"""Sync the 절대모멘텀 figure and score a card restates to the ones it maintains.

Why this exists. `update_cards.py` rewrites the 절대모멘텀 subscore every day -
the score in `.subscore-val` and the weighted return in `.subscore-desc`. The
prose beside it restates both, and nothing rewrites that. Sixty-one of the
sixty-five cards that quote the figure had drifted from their own subscore, and
the drift is not small: SNDK said +654.8% against a maintained +454.78%, MU
+228.2% against +165.87%, LRCX +71.23% against +30.98%.

Two things are synced and they come from the same block:
  - the weighted return, from `최근 3개월~1년 가중 수익률 X%`
  - the score out of forty, from `.subscore-val` in the same subscore-box

A card whose maintained figure has crossed zero since the sentence was written
is NOT synced. The sentence around the number is a judgment - "매우 강하다",
"부진하다", "만점에 크게 못 미친다" - and a judgment written about a positive
return does not survive having a negative one dropped into it. META (-12.9%
stated, +4.82% maintained) and GE (+9.34% stated, -0.82% maintained) both
reversed sign, so both are reported for hand rewrite instead.

That is the same rule fix_ma_prose.py arrived at by a longer road: syncing a
value inside a sentence whose claim has reversed produces a freshly-numbered
falsehood, which reads as authored today and is worse than an obviously old
number.

Usage:
  python3 scripts/fix_momentum_text.py [--cards-dir DIR] [--check]
    --check   write nothing; exit 1 if any card restates a figure it no longer holds
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CARDS = Path.home() / "Workspace/stock-widgets-preview"

BOX = re.compile(
    r'<span>절대모멘텀</span>.{0,400}?<div class="subscore-val">(\d+)</div>'
    r'.{0,400}?<div class="subscore-desc">최근 3개월~1년 가중 수익률 ([+-][\d.]+)%</div>',
    re.S)
# every restatement of the figure, outside that block
FIGURE = re.compile(
    r"((?:가중\s*모멘텀|가중\s*수익률|절대모멘텀)[^.<]{0,30}?)([+-]?\d+\.?\d*)(%)")
# "40점 만점 중 30점", "40점 만점에 20점", "40점 만점의 절반인 20점"
SCORE = re.compile(r"(40점\s*만점(?:\s*(?:중|에|의))?[^.<]{0,12}?)(\d+)(점)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", default=str(DEFAULT_CARDS))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cards = Path(args.cards_dir)
    data = json.loads((cards / "site_data" / "stocks.json").read_text(encoding="utf-8"))

    changed, stale, skipped, flipped = [], [], 0, []
    for entry in data["tickers"]:
        tk = entry["ticker"]
        path = cards / entry["href"]
        html = path.read_text(encoding="utf-8")
        box = BOX.search(html)
        if not box:
            skipped += 1
            continue
        score, ret = box.group(1), float(box.group(2))
        guard = box.span()

        # a sign change invalidates the judgment wrapped around the number
        sign_clash = False
        for m in FIGURE.finditer(html):
            if guard[0] <= m.start() < guard[1]:
                continue
            old = float(m.group(2))
            if (old >= 0) != (ret >= 0):
                sign_clash = True
                flipped.append(f"{tk}: {m.group(2)}% stated vs {ret:+.2f}% maintained")
        if sign_clash:
            stale.append(tk)
            continue

        edits = [0]

        def fig(m):
            if guard[0] <= m.start() < guard[1]:
                return m.group(0)
            places = len(m.group(2).split(".")[1]) if "." in m.group(2) else 0
            sign = "+" if m.group(2).startswith(("+", "-")) else ""
            new = f"{ret:{sign}.{places}f}"
            if new == m.group(2):
                return m.group(0)
            edits[0] += 1
            return f"{m.group(1)}{new}{m.group(3)}"

        def sc(m):
            if m.group(2) == score:
                return m.group(0)
            edits[0] += 1
            return f"{m.group(1)}{score}{m.group(3)}"

        new_html = SCORE.sub(sc, FIGURE.sub(fig, html))
        if edits[0]:
            changed.append(f"{tk}({edits[0]})")
            if args.check:
                stale.append(tk)
            else:
                path.write_text(new_html, encoding="utf-8")

    if args.check:
        print(f"cards restating a momentum figure they no longer hold: {len(stale)}"
              + (f" - {' '.join(stale)}" if stale else ""))
        for f in flipped:
            print(f"  SIGN REVERSED, judgment no longer fits - hand rewrite - {f}")
        return 1 if stale else 0
    print(f"updated {len(changed)}: {' '.join(changed) or '-'}")
    print(f"no 절대모멘텀 subscore to read: {skipped}")
    for f in flipped:
        print(f"  sign reversed, left for hand rewrite - {f}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if "--check" in sys.argv else 0)
