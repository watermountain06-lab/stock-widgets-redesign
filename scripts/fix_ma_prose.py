#!/usr/bin/env python3
"""Sync the moving-average values a card quotes in prose to its own bars.

Why this exists. `update_cards.py` rewrites the `ma-row` table every day, so
the four displayed lines - MA5, MA20, MA60, MA120 - are always current. The
prose beside the table quotes the same numbers, and nothing rewrites that. It
was true on the analysis date and has drifted since.

It is worse for MA50, MA150 and MA200. Those three feed the 추세구조 score but
are not in the table, so until now nothing in the fleet could even check them:
274 of the 434 prose MA citations named a line no maintained surface displays.

The source is the card's own embedded {TICKER}_DAILY array, and the script
proves that basis before it uses it. For every card it recomputes MA5/20/60/120
from the bars and compares them against the maintained table. Only if all four
reproduce does it trust the same bars for MA50/150/200, which the table cannot
vouch for. A card whose bars disagree with its own table is skipped and named,
never "corrected" toward a basis the card itself contradicts.

What this does NOT touch: a citation with a derived figure attached - "MA150
($341.88)을 $6.86 하회", "MA60과의 격차는 $0.11(+0.03%)". Updating the value
there would leave the gap, the percentage and usually the conclusion computed
off the old one. Those have to stop restating, which is a rewrite and not a
sync, so they are counted and reported for hand work.

Ordering claims are likewise left alone. Ten cards look wrong to a naive
MA50>MA150>MA200 test and none of them are - they already say "조건 4개 중
1개만 충족" or "완전한 정배열에는 도달하지 못했다".

Usage:
  python3 scripts/fix_ma_prose.py [--cards-dir DIR] [--check]
    --check   write nothing; exit 1 if any card quotes an MA it no longer has
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

DEFAULT_CARDS = Path.home() / "Workspace/stock-widgets-preview"

# scoped to one row: a bare `MA(\d+)...ma-val` pair walks across rows and pairs
# a prose "MA200" with the table's first value, which is how I misread DIS once.
ROW_VAL = re.compile(
    r'MA(\d+)\s*\([^)]*\)</span>.{0,200}?<span class="ma-val">\$?([\d,]+\.\d+)</span>',
    re.S)
MA_ROW_BLOCK = re.compile(r'<div class="ma-row">.*?</div></div>', re.S)
SCRIPT = re.compile(r"<script.*?</script>", re.S)
CITE = re.compile(r"MA(\d+)(\s*\(\s*\$?)([\d,]+\.\d+)(\s*\))")
DERIVED = re.compile(r"[+-]?\d+\.\d+\s*%|\$\s?[\d,]+\.\d+")
# A relationship claim is not a citation. Syncing the value inside "MA5($444.95)
# 만 상회한다" leaves a freshly-numbered sentence asserting the opposite of the
# truth, which reads as authored today and is worse than an obviously old
# number. AMAT, ANET, GE, PM and XOM all came back this way on the first run.
CLAIM = re.compile(r"상회|하회|웃돌|밑돌|넘어서|위에 있|아래에 있|낮다|높다|정배열|역배열")
# a citation's own "$1,234.56" matches DERIVED, and so does the next citation's.
# Testing the raw text made MA120 look derived because MA5 followed it, so every
# citation is masked out before asking whether a *derived* figure is present.

TOL = 0.004          # the table rounds; anything inside this is the same number


def bars(html, ticker):
    m = re.search(re.escape(ticker.replace(".", "_")) + r"_DAILY\s*=\s*(\[.*?\]);",
                  html, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(1))
    except ValueError:
        arr = ast.literal_eval(m.group(1))     # some cards embed JS single quotes
    return [b[4] if isinstance(b, (list, tuple)) else b["c"] for b in arr]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", default=str(DEFAULT_CARDS))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cards = Path(args.cards_dir)
    data = json.loads((cards / "site_data" / "stocks.json").read_text(encoding="utf-8"))

    changed, stale, skipped, derived, unproven, mixed, hand = [], [], 0, 0, [], [], []
    for entry in data["tickers"]:
        tk = entry["ticker"]
        path = cards / entry["href"]
        html = path.read_text(encoding="utf-8")

        close = bars(html, tk)
        table = {}
        for row in MA_ROW_BLOCK.finditer(html):
            rv = ROW_VAL.search(row.group(0))
            if rv:
                table[int(rv.group(1))] = float(rv.group(2).replace(",", ""))
        if not close or not table:
            skipped += 1
            continue

        # prove the bars reproduce every maintained line before trusting them
        if any(abs(sum(close[-n:]) / n - v) / v > TOL
               for n, v in table.items() if n <= len(close)):
            unproven.append(tk)
            continue

        # protect what the pipeline maintains and what is not prose at all
        guard = [m.span() for m in MA_ROW_BLOCK.finditer(html)]
        guard += [m.span() for m in SCRIPT.finditer(html)]

        def inside(i):
            return any(a <= i < b for a, b in guard)

        masked = list(html)
        for m in CITE.finditer(html):
            masked[m.start():m.end()] = "\0" * (m.end() - m.start())
        masked = "".join(masked)



        # The atom is the whole card, not the sentence and not the text node.
        # Anything smaller lets one block be synced while the block beside it is
        # held back for hand rewrite, and the card then quotes two different
        # values for the same line. PM showed this twice over: its prose writes
        # a raw ">" between citations, which splits any markup-based window, and
        # its two blocks ended up disagreeing about MA20. So a card with even one
        # citation that derives something is left entirely alone.
        cites = [m for m in CITE.finditer(html)
                 if not inside(m.start()) and int(m.group(1)) <= len(close)]
        node_ok = True
        for m in cites:
            a = max(masked.rfind(">", 0, m.start()), masked.rfind('"', 0, m.start())) + 1
            nxt = [x for x in (masked.find("<", m.end()), masked.find('"', m.end()))
                   if x != -1]
            node = masked[a:min(nxt) if nxt else len(masked)]
            if DERIVED.search(node) or CLAIM.search(node):
                node_ok = False
                break
        if not node_ok:
            derived += len(cites)
            # how many of those the card actually gets wrong today - the queue
            # for hand rewriting, and the reason --check must still fail.
            drifted = sum(1 for m in cites
                          if abs(sum(close[-int(m.group(1)):]) / int(m.group(1))
                                 - float(m.group(3).replace(",", "")))
                          / (sum(close[-int(m.group(1)):]) / int(m.group(1))) > TOL)
            if drifted:
                hand.append(f"{tk}({drifted})")
            mixed.append(tk)
            continue

        edits = []
        for m in cites:
            n = int(m.group(1))
            want = sum(close[-n:]) / n
            old_val = float(m.group(3).replace(",", ""))
            if abs(want - old_val) / want <= TOL:
                continue
            places = len(m.group(3).split(".")[1])
            new_val = f"{want:,.{places}f}" if "," in m.group(3) else f"{want:.{places}f}"
            edits.append((m.start(), m.end(),
                          f"MA{m.group(1)}{m.group(2)}{new_val}{m.group(4)}"))

        if edits:
            changed.append(f"{tk}({len(edits)})")
            if args.check:
                stale.append(tk)
            else:
                out = []
                at = 0
                for a, b, text in edits:
                    out.append(html[at:a])
                    out.append(text)
                    at = b
                out.append(html[at:])
                path.write_text("".join(out), encoding="utf-8")

    if args.check:
        print(f"cards quoting an MA their own bars no longer produce: {len(stale)}"
              + (f" - {' '.join(stale)}" if stale else ""))
        print(f"citations in cards left whole for hand rewrite (derived or claim-bearing): {derived}"
              f" ({len(mixed)} cards)")
        if hand:
            print(f"  STALE and only fixable by hand: {sum(int(x.split('(')[1][:-1]) for x in hand)}"
                  f" citations in {len(hand)} cards - {' '.join(hand)}")
        for t in unproven:
            print(f"  BARS DISAGREE WITH THE MAINTAINED TABLE, skipped - {t}")
        return 1 if stale or hand else 0
    print(f"updated {len(changed)}: {' '.join(changed) or '-'}")
    print(f"citations in cards left whole for hand rewrite (derived or claim-bearing): {derived}"
          f" ({len(mixed)} cards)")
    print(f"no bars or no MA table: {skipped}")
    if hand:
        print(f"  stale and only fixable by hand: "
              f"{sum(int(x.split('(')[1][:-1]) for x in hand)} citations in "
              f"{len(hand)} cards - {' '.join(hand)}")
    for t in unproven:
        print(f"  bars disagree with the maintained table, skipped - {t}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if "--check" in sys.argv else 0)
