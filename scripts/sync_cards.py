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

Only the live set is copied: that day's top 100 by market cap (scripts/live_set.py,
2026-10-17 user decision). A card here that has dropped out of the set is removed, and a
ticker that has entered it gets its card and, if missing, its logo from preview's logos/.

Usage: python3 scripts/sync_cards.py [--check] [--exclude TICKER ...]
  --check    report what would change, write nothing
  --exclude  skip a card being written by something else right now
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

from build_home import BuildError, preview_data
from live_set import live_tickers

REPO = Path(__file__).resolve().parents[1]
PREVIEW = Path.home() / "Workspace/stock-widgets-preview"
DEST = REPO / "cards"
SRC_LINK = '<a class="back-bar-left" href="index.html">'
# 카드가 스스로 밝히는 시총 순위(상단 표시줄 + 소개 문장 등). 상단 표시줄의 숫자가 그 카드 자신의 순위이고, 같은 숫자의
# 언급만 자기 순위다(다른 카드를 인용한 순위는 그대로 둔다 — preview fix_card_rank_text.py와 같은 규칙).
BACKBAR = re.compile(r'<span class="back-bar-current">[^<]*?시총 (\d+)위')
MENTION = re.compile(r"시총 (\d+)위")
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
    # 2026-10-15 사용자 결정: 카드의 "시총 N위"는 그날 시가총액 순(홈과 같은 순서, build_home.preview_data)
    try:
        rank = {r["ticker"]: r["rank"] for r in preview_data()[0]}
    except BuildError as e:
        sys.exit(f"sync_cards: {e}")

    live = live_tickers()   # 그날 시총 상위 100(scripts/live_set.py)
    new, updated, unchanged, skipped, not_live = [], [], [], [], []
    for src in src_files:
        ticker = src.name.replace("_full_widget.html", "")
        if ticker in skip:
            skipped.append(ticker)
            continue
        if live is not None and ticker not in live:
            not_live.append(ticker)
            continue
        body = src.read_text(encoding="utf-8")
        if body.count(SRC_LINK) != 1:
            sys.exit(f"{src.name}: expected exactly 1 back-bar home link, found {body.count(SRC_LINK)}")
        body = body.replace(SRC_LINK, DST_LINK)
        if ticker in rank:
            bb = BACKBAR.search(body)
            if not bb:
                sys.exit(f"{src.name}: no back-bar rank label, so its own rank cannot be identified")
            stated, want = int(bb.group(1)), rank[ticker]
            body = MENTION.sub(lambda m: f"시총 {want}위" if int(m.group(1)) == stated else m.group(0), body)
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

    # 상위 100에서 빠진 종목의 카드는 지운다(2026-10-17 사용자 결정: 라이브에는 100위까지만). preview에 없는 카드는
    # 아래 orphans로 따로 알린다 — 지우지 않는다.
    removed = sorted(p.name.replace("_full_widget.html", "") for p in DEST.glob("*_full_widget.html")
                     if (PREVIEW / p.name).exists() and p.name.replace("_full_widget.html", "") not in live
                     and p.name.replace("_full_widget.html", "") not in skip)
    if not args.check:
        for t in removed:
            (DEST / f"{t}_full_widget.html").unlink()

    # 새로 들어온 종목의 로고(없으면 build_home이 멈춘다). 있는 로고는 덮어쓰지 않는다.
    logos = []
    for t in sorted(live):
        dst_logo = REPO / "logos" / f"{t.lower()}.png"
        src_logo = PREVIEW / "logos" / f"{t.lower()}.png"
        if not dst_logo.exists() and src_logo.exists():
            logos.append(t)
            if not args.check:
                shutil.copy2(src_logo, dst_logo)

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
    if not_live:
        print(f"not in the top 100 {len(not_live)}: {' '.join(not_live)}")
    print(f"{'would remove' if args.check else 'removed'} {len(removed)}: {' '.join(removed) or '-'}")
    if logos:
        print(f"{'would copy logo' if args.check else 'copied logo'} {len(logos)}: {' '.join(logos)}")
    if orphans:
        print(f"NOT IN PREVIEW, left alone {len(orphans)}: {' '.join(orphans)}")
    if args.check and (new or updated or removed or logos):
        sys.exit(1)


if __name__ == "__main__":
    main()
