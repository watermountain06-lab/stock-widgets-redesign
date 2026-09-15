#!/usr/bin/env python3
"""Sync every "기술점수 N/100 등급" a card states to the one it maintains.

Why this exists. `update_cards.py` rewrites the technical scorecard every day -
the number in `.scorecard-score`, the word in `.scorecard-grade`, the bar width,
the three subscore blocks. It does not touch the summary surfaces that restate
the same headline so a reader does not have to switch tabs: the box-key bullet,
the `bb-item` evidence line, the 4개분석 종합 row. Those were written once at
build time and froze there.

Six of the nineteen cards built after rank 50 carried a stale number, and on one
of them the staleness had become a falsehood: QCOM said 기술점수 60/100 적격 while
its own maintained badge two tabs away said 50/100 부적격. The score had crossed
the 60 boundary and the grade word flipped with it, but only in the one place a
script was rewriting.

The card's own maintained scorecard is the source, not `tech_state` - the same
reason `fix_52w_prose.py` reads the subscore desc rather than the file behind it.
A script that reads the card cannot disagree with what the card displays, and a
card whose scorecard is itself stale is not silently "corrected" to something
its own badge contradicts.

The grade word travels with the number. `update_cards.py`'s GRADE_TEXT maps
displayGrade to 우수/적격/부적격, and a score that moves across 60 changes the word
as well as the digits - which is exactly what made QCOM wrong rather than merely
old.

What this does NOT touch: the narrative sentences that derive a value rather
than restate it - "가중 모멘텀 +23.81%로 40점 만점 중 30점", "ATR 38.1백분위 — 변동성이
평소보다 낮은 구간". Those carry a working and a conclusion, and rewriting the
number inside them would leave the working and the conclusion contradicting the
new figure. They have to be rewritten by hand to stop restating, not synced.

Usage:
  python3 scripts/fix_tech_score_text.py [--cards-dir DIR] [--check]
    --check   write nothing; exit 1 if any card states a score it no longer holds
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CARDS = Path.home() / "Workspace/stock-widgets-preview"

# what update_cards.py maintains, and therefore what the card actually shows
KEPT_SCORE = re.compile(r'<div class="scorecard-score"><span class="num">(\d+)</span>')
KEPT_GRADE = re.compile(r'<div class="scorecard-grade grade-[a-z]+">기술적 분석 (우수|적격|부적격)</div>')
# every restatement outside it: "기술점수 70/100(적격)", "기술점수 90/100 우수", "기술점수 5/100:"
MENTION = re.compile(r"(기술점수\s*)(\d+)(/100)(\s*\(\s*(?:우수|적격|부적격)\s*\)|\s+(?:우수|적격|부적격))?")


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
        s, g = KEPT_SCORE.search(html), KEPT_GRADE.search(html)
        if not s or not g:          # SPCX/SKHY and anything without a technical scorecard
            skipped += 1
            continue
        score, grade = s.group(1), g.group(1)

        edits = [0]

        def one(m):
            had_word = m.group(4)
            new_word = ""
            if had_word:
                # keep the card's own bracket style, replace only the word
                new_word = (f"({grade})" if "(" in had_word else f" {grade}")
                if had_word.startswith(" ("):
                    new_word = f" ({grade})"
            if m.group(2) == score and (not had_word or had_word == new_word):
                return m.group(0)
            if had_word and had_word.strip(" ()") != grade:
                flipped.append(f"{tk}: {m.group(2)}/100 {had_word.strip(' ()')} -> {score}/100 {grade}")
            edits[0] += 1
            return f"{m.group(1)}{score}{m.group(3)}{new_word}"

        new = MENTION.sub(one, html)
        if edits[0]:
            changed.append(f"{tk}({edits[0]})")
            if args.check:
                stale.append(tk)
            else:
                path.write_text(new, encoding="utf-8")

    if args.check:
        print(f"cards restating a technical score they no longer hold: {len(stale)}"
              + (f" - {' '.join(stale)}" if stale else ""))
        for f in flipped:
            print(f"  GRADE WORD ALSO WRONG - {f}")
        return 1 if stale else 0
    print(f"updated {len(changed)}: {' '.join(changed) or '-'}")
    print(f"no technical scorecard to read: {skipped}")
    for f in flipped:
        print(f"  grade word corrected - {f}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if "--check" in sys.argv else 0)
