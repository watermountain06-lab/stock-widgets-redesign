#!/usr/bin/env python3
"""Make each card's peer-comparison chart read its own identity instead of the template's.

`renderMultipleChart()` hardcoded three things about the card's own bar: the
ticker shown under it, the MULTIPLE_DATA key its value comes from, and its two
brand colours. None of them move when a card is copied, so every new ticker
inherited the template's — and a rename of the data key does not reach
`labels[0]` at all. Both halves shipped: 26 cards were drawing their own bar in
another company's brand colour (fixed 2026-09-12), C shipped in KLAC's teal a
few hours later because the sweep predated it, and the AXP build caught its own
bar about to render under the label "IBM".

Fixing the instances does not fix the mechanism, so this rewrites the three to
be derived at runtime:
  - the label comes from the card's own back-bar (which is also why BRKB keeps
    calling itself BRK.B),
  - the value comes from whichever MULTIPLE_DATA key ends in "Value", so the
    six cards whose key still carries a previous ticker's name keep working,
  - the colours come from --accent / --accent2.

Deliberately untouched: the early-return branches some cards use to draw a
withheld metric as a single neutral bar, and NVDA's inverted fill/border pair.

Usage: python3 scripts/fix_chart_identity.py [--check] [--cards-dir DIR]
"""
import argparse
import re
import sys
from pathlib import Path

PREVIEW = Path.home() / "Workspace/stock-widgets-preview"
ANCHOR = "if (multipleChart) multipleChart.destroy();"
DERIVE = """
    // Self identity and colour are derived, never hardcoded — copying a card
    // used to carry the template ticker's name and brand colour into the new
    // card's own bar, and renaming the MULTIPLE_DATA key never reached labels[0].
    const selfKey = Object.keys(d).find(function (k) { return /Value$/.test(k); });
    const _bbc = document.querySelector('.back-bar-current');
    const selfLabel = (_bbc ? _bbc.textContent.split('\\u00b7')[0].trim() : '')
      || (selfKey ? selfKey.replace(/Value$/, '').toUpperCase() : '');
    const _cs = getComputedStyle(document.documentElement);
    const selfBd = _cs.getPropertyValue('--accent').trim();
    const selfBg = _cs.getPropertyValue('--accent2').trim();"""

SUBS = [
    (re.compile(r"(const labels = \[\s*)'[^']*'(\s*,\s*\.\.\.d\.peers)"), r"\1selfLabel\2"),
    (re.compile(r"(const data = \[\s*)d\.\w+Value(\s*,\s*\.\.\.d\.peers)"), r"\1d[selfKey]\2"),
    (re.compile(r"(const bg = \[\s*)'#[0-9a-fA-F]{6}'(\s*,\s*\.\.\.d\.peers)"), r"\1selfBg\2"),
    (re.compile(r"(const bd = \[\s*)'#[0-9a-fA-F]{6}'(\s*,\s*\.\.\.d\.peers)"), r"\1selfBd\2"),
]


def convert(text):
    if "const selfKey = Object.keys(d)" in text:
        return text, 0            # already converted
    n = 0
    for pat, rep in SUBS:
        text, k = pat.subn(rep, text)
        n += k
    if n == 0:
        return text, 0
    if n != len(SUBS):
        raise RuntimeError(f"expected {len(SUBS)} substitutions, made {n} - refusing a partial rewrite")
    i = text.index(ANCHOR) + len(ANCHOR)
    return text[:i] + DERIVE + text[i:], n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--cards-dir", default=str(PREVIEW))
    args = ap.parse_args()
    cards = Path(args.cards_dir)
    changed, skipped, failed = [], [], []
    for f in sorted(cards.glob("*_full_widget.html")):
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
    verb = "would convert" if args.check else "converted"
    print(f"{verb} {len(changed)}: {' '.join(changed) or '-'}")
    print(f"already derived or no peer chart: {len(skipped)}: {' '.join(skipped)}")
    if args.check and changed:
        sys.exit(1)


if __name__ == "__main__":
    main()
