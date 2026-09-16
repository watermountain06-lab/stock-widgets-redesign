#!/usr/bin/env python3
"""Sync each card's own "시총 N위" text to its cardRank in stocks.json.

Why this exists. Every new card until now was appended at the end, so a card's
rank never changed after it was written and the number baked into its HTML stayed
right by accident. That ended when three companies turned out to be missing from
ranks already assigned (TMO, MRVL, APH) - inserting them moves everything below
down, and nothing else in the repo rewrites the rank a card states about itself.
`fix_backbar_chain.py` reads that label to get the display name; it does not
correct the number.

Each card states its rank twice: in the back-bar (`AMGN · 시총 59위`) and in the
company description line (`미국 상장기업 시총 59위`). Both are rewritten.

A card may also cite ANOTHER card's rank - C's valuation note says "가장 최근에
만든 은행 카드(WFC, 시총 46위)". Those must not be touched.

Telling the two apart by wording or position does not work. The description line
is phrased at least five ways across the fleet ("미국 상장기업 시총 55위", "S&P
500 시총 5위", "세계 시총 13위", a bare "· 시총 9위", and TSLA has a third
mention in a styled div of its own), and looking for a nearby ticker symbol is
worse than useless because the back-bar always carries the PREVIOUS card's
ticker right before the label (`◀ KLAC` then `C · 시총 53위`).

What does work: the back-bar label is always present and always the card's own
rank, so it says which number this card currently claims. Every mention equal to
that number is the card talking about itself; every other mention is a citation.
Ranks are unique, so a citation can never collide with the citing card's own.

Usage:
  python3 scripts/fix_card_rank_text.py [--cards-dir DIR] [--check]
    --check   write nothing; exit 1 if any card states a rank it no longer holds
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CARDS = Path.home() / "Workspace/stock-widgets-preview"
BACKBAR = re.compile(r'<span class="back-bar-current">[^<]*?시총 (\d+)위')
MENTION = re.compile(r"시총 (\d+)위")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", default=str(DEFAULT_CARDS))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cards = Path(args.cards_dir)
    data = json.loads((cards / "site_data" / "stocks.json").read_text(encoding="utf-8"))
    rank = {t["ticker"]: t["cardRank"] for t in data["tickers"]}
    others = {t["ticker"] for t in data["tickers"]}

    changed, stale, skipped = [], [], 0
    for entry in data["tickers"]:
        tk = entry["ticker"]
        path = cards / entry["href"]
        html = path.read_text(encoding="utf-8")
        want = rank[tk]
        bb = BACKBAR.search(html)
        if not bb:
            sys.exit(f"{tk}: no back-bar rank label, so its own rank cannot be identified")
        stated = int(bb.group(1))
        skipped += sum(1 for m in MENTION.finditer(html) if int(m.group(1)) != stated)
        if stated == want:
            continue
        edits = sum(1 for m in MENTION.finditer(html) if int(m.group(1)) == stated)
        new = MENTION.sub(
            lambda m: f"시총 {want}위" if int(m.group(1)) == stated else m.group(0), html)

        if not edits:
            continue
        changed.append(f"{tk}({edits})")
        if args.check:
            stale.append(tk)
        else:
            path.write_text(new, encoding="utf-8")

    if args.check:
        print(f"cards stating a rank they no longer hold: {len(stale)}"
              + (f" - {' '.join(stale)}" if stale else ""))
        return 1 if stale else 0
    print(f"updated {len(changed)}: {' '.join(changed) or '-'}")
    print(f"left alone (a mention of another card's rank): {skipped}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if "--check" in sys.argv else 0)
