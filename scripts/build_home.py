#!/usr/bin/env python3
"""Render this repo's index.html from the preview site's generated homepage.

Why this exists: preview's index.html is built from site_data/stocks.json by
its own pipeline and carries real macro figures, real stat-card counts and a
working 매력도별 tab. This repo's index.html was still the original mockup -
S&P 500 at 6,449.15, "5% 이상 상승 11개", 매력도별 marked 준비중 - all of it
layout-demo values sitting on the public domain. Rather than keep two hand-
maintained copies of the same page, this takes preview's rendered page and
applies the one structural difference between the repos: cards live under
cards/ here, at the root there.

Deliberately NOT a second renderer. Everything about the page's design and
data belongs to preview's build_index.py; if the page changes there, re-run
this and the change arrives. The only thing this file is allowed to know is
the href prefix.

Usage: python3 scripts/build_home.py [--check]
  --check  exit non-zero if index.html is not what this would write
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREVIEW_HOME = Path.home() / "Workspace/stock-widgets-preview/index.html"
OUT = REPO / "index.html"
HREF = re.compile(r'("href": ")([A-Z][A-Z0-9._-]*_full_widget\.html")')


def render():
    src = PREVIEW_HOME.read_text(encoding="utf-8")
    out, n = HREF.subn(r'\1cards/\2', src)
    if n == 0:
        sys.exit("no card hrefs found in preview's index.html - refusing to write")
    # every card referenced must actually exist here, or the public page links
    # to a 404 that nothing else would catch
    missing = [h for h in re.findall(r'"href": "cards/([^"]+)"', out)
               if not (REPO / "cards" / h).exists()]
    if missing:
        sys.exit(f"preview lists {len(missing)} card(s) this repo does not have: {', '.join(missing)}")
    return out, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out, n = render()
    if args.check:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != out:
            sys.exit("index.html is stale - run python3 scripts/build_home.py")
        print(f"OK - index.html matches preview's homepage ({n} cards)")
        return
    OUT.write_text(out, encoding="utf-8")
    print(f"Wrote {OUT} ({n} cards, hrefs prefixed with cards/)")


if __name__ == "__main__":
    main()
