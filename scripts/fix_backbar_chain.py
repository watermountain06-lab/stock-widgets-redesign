#!/usr/bin/env python3
"""Rebuild every card's prev/next back-bar links from the current rank order.

The chain is hand-patched when a ticker is added: the new card points back at
its predecessor and the predecessor's disabled "다음 ▶" becomes a link. The
playbook flags this as a recurring gotcha, and it has in fact broken twice -
by 2026-09-12 the live chain had TSLA (rank 10) orphaned in both directions,
because META was wired straight to BRK.B, and WMT (rank 16) still carried the
disabled end-of-chain marker it was given when it was last, which left every
card from AMD onward unreachable going forward. Walking 다음 from rank 1
reached 15 of 54 cards.

Rather than patch two more neighbours by hand each time, this regenerates the
whole chain from stocks.json's cardRank order, which is the thing the chain is
supposed to mirror. Run it after adding a ticker, or with --check in a
verification pass.

Display labels come from each card's own back-bar-current, because they are
not always the file's ticker - BRKB's card calls itself BRK.B.

Usage: python3 scripts/fix_backbar_chain.py [--check] [--cards-dir DIR]
"""
import argparse
import json
import re
import sys
from pathlib import Path

PREVIEW = Path.home() / "Workspace/stock-widgets-preview"
BLOCK = re.compile(r'( *)<div class="back-bar-right">.*?</div>', re.S)
LABEL = re.compile(r'<span class="back-bar-current">(.*?) · 시총 (\d+)위</span>')


def build(indent, prev, label, rank, nxt, labels):
    i = indent + "  "
    left = (f'{i}<a class="back-bar-nav" href="{prev}_full_widget.html">◀ {labels[prev]}</a>'
            if prev else f'{i}<span class="back-bar-nav disabled">◀ 이전</span>')
    right = (f'{i}<a class="back-bar-nav" href="{nxt}_full_widget.html">다음 {labels[nxt]} ▶</a>'
             if nxt else f'{i}<span class="back-bar-nav disabled">다음 ▶</span>')
    return (f'{indent}<div class="back-bar-right">\n{left}\n'
            f'{i}<span class="back-bar-current">{label} · 시총 {rank}위</span>\n'
            f'{right}\n{indent}</div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--cards-dir", default=str(PREVIEW))
    args = ap.parse_args()
    cards = Path(args.cards_dir)

    data = json.loads((PREVIEW / "site_data/stocks.json").read_text(encoding="utf-8"))
    order = [t["ticker"] for t in sorted(data["tickers"], key=lambda x: x["cardRank"])]

    labels, texts = {}, {}
    for t in order:
        f = cards / f"{t}_full_widget.html"
        if not f.is_file():
            sys.exit(f"{f} missing - refusing to rebuild a partial chain")
        texts[t] = f.read_text(encoding="utf-8")
        m = LABEL.search(texts[t])
        if not m:
            sys.exit(f"{t}: no back-bar-current found")
        labels[t] = m.group(1)

    changed = []
    for i, t in enumerate(order):
        s = texts[t]
        m = BLOCK.search(s)
        if not m:
            sys.exit(f"{t}: no back-bar-right block")
        new = build(m.group(1), order[i - 1] if i else None, labels[t], i + 1,
                    order[i + 1] if i + 1 < len(order) else None, labels)
        if new != m.group(0):
            changed.append(t)
            if not args.check:
                (cards / f"{t}_full_widget.html").write_text(s[:m.start()] + new + s[m.end():],
                                                             encoding="utf-8")
    if args.check:
        print(f"{len(changed)} card(s) would change: {' '.join(changed) or '-'}")
        sys.exit(1 if changed else 0)
    print(f"rebuilt chain over {len(order)} cards; {len(changed)} changed: {' '.join(changed) or '-'}")


if __name__ == "__main__":
    main()
