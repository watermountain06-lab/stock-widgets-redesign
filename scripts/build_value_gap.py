#!/usr/bin/env python3
"""Build value-data.js: the homepage's "매수 기준가" section (2026-10-07 prototype).

What the section shows and why (team review 2026-10-07 — value analyst, viz designer,
statistics skeptic, Codex, Fable):
  - Only cards whose v2 verdict is 적정~저평가 or cheaper. The user wants the cards that
    have a reason to be called cheap, not the whole universe.
  - For each, the price at which the 현금흐름 judge turns '싸다' (기본 내재가치 x 0.9) and
    how far the current price sits from it. That is a statement of the site's rule, not a
    forecast: the DCF ratio's rank IC is +0.014 [-0.023, +0.054] on the point-in-time panel
    (verdict_replay_result.json), so no "upside %" or base/optimistic target is shown.
    보수·낙관 are left out too - 47 of 99 cards break the low <= base <= high order.
  - A quarterly count of cards that were under their 기준가, from preview's dcf_track files,
    so a day with none reads as the usual state rather than as a broken page.

Sources (read only): preview v2 cards through v2/research/extract_card_verdicts.js, the
{T}_DCF block of each card for `hard`, and v2/{T}_dcf_track.json. Names come from this
repo's stock-data.js, so run build_home.py first.

Usage: python3 scripts/build_value_gap.py [--check]
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREVIEW_V2 = Path.home() / "Workspace/stock-widgets-preview/v2"
OUT = REPO / "value-data.js"

CHEAP = ["초저평가", "저평가", "적정~저평가"]
BUY_FACTOR = 0.9  # dcfLevel: r <= 0.9 is '싸다'


def names():
    rows = {}
    for line in (REPO / "stock-data.js").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith('{"rank"'):
            r = json.JSONDecoder().raw_decode(line)[0]
            rows[r["ticker"]] = r["name"]
    return rows


def dcf_hard(t):
    html = (PREVIEW_V2 / f"{t}_full_widget.html").read_text(encoding="utf-8")
    key = f"const {t}_DCF = "
    if key not in html:
        return []
    block = json.JSONDecoder().raw_decode(html, html.index(key) + len(key))[0]
    return block.get("hard") or []


QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def quarter_range(t, quarter, cache={}):
    """Lowest low and highest high over the calendar quarter, from the same daily series
    dcf_track priced its points with (build_multiple_history.history_daily - for SKHY the
    KRX shares converted to one ADR in dollars, not the ADR itself). An unfinished quarter
    runs to the last bar."""
    if t not in cache:
        if str(PREVIEW_V2) not in sys.path:
            sys.path.insert(0, str(PREVIEW_V2))
        import build_multiple_history as bmh
        cache[t] = bmh.history_daily(t, bmh.load_daily(t))
    y, n = quarter.split("Q")
    lo, hi = f"{y}-{(int(n) - 1) * 3 + 1:02d}-01", f"{y}-{QUARTER_END[int(n)]}"
    bars = [b for b in cache[t] if lo <= b[0] <= hi]
    if not bars:
        return None, None
    return round(min(b[3] for b in bars), 2), round(max(b[2] for b in bars), 2)


def history(name, current):
    """Per calendar quarter: cards whose price was at or under 0.9 x base, of those with a base.

    Each card counts once per quarter, at its last point in that quarter - a card with two
    points in one quarter used to be counted twice (2026Q1 had 91 of 90 tracked cards).
    The cards under the line are listed so the homepage can show them on click.
    """
    last = {}  # (quarter, ticker) -> point
    for f in sorted(PREVIEW_V2.glob("*_dcf_track.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for p in d["points"]:
            if p.get("base") is None or p.get("price") is None:
                continue
            key = (f"{p['date'][:4]}Q{(int(p['date'][5:7]) - 1) // 3 + 1}", d["ticker"])
            if key not in last or p["date"] > last[key]["date"]:
                last[key] = p
    q = defaultdict(lambda: {"total": 0, "stocks": []})
    for (quarter, t), p in sorted(last.items()):
        q[quarter]["total"] += 1
        if p["base"] > 0 and p["price"] / p["base"] <= BUY_FACTOR:
            buy = round(p["base"] * BUY_FACTOR, 2)
            low, high = quarter_range(t, quarter)
            q[quarter]["stocks"].append({"ticker": t, "name": name.get(t, t), "date": p["date"],
                                         "price": round(p["price"], 2), "buyPrice": buy,
                                         "gap": round(p["price"] / buy - 1, 4),
                                         "low": low, "high": high, "current": current.get(t)})
    out = []
    for k, v in sorted(q.items()):
        v["stocks"].sort(key=lambda s: s["gap"])
        out.append({"quarter": k, "under": len(v["stocks"]), "total": v["total"], "stocks": v["stocks"]})
    return out


def build():
    out = subprocess.run(["node", str(PREVIEW_V2 / "research/extract_card_verdicts.js")],
                         capture_output=True, text=True, check=True).stdout
    verdicts = json.loads(out)
    name = names()
    rows, dates = [], set()
    for t, v in verdicts.items():
        if "error" in v:
            raise SystemExit(f"{t}: verdict extraction failed - {v['error']}")
        if v["verdict"] not in CHEAP:
            continue
        if not (isinstance(v.get("base"), (int, float)) and v["base"] > 0 and v.get("price")):
            raise SystemExit(f"{t}: cheap verdict without a positive base value")
        buy = round(v["base"] * BUY_FACTOR, 2)
        dates.add(v["date"])
        rows.append({
            "ticker": t, "name": name.get(t, t), "verdict": v["verdict"],
            "price": v["price"], "buyPrice": buy,
            "gap": round(v["price"] / buy - 1, 4),
            "judges": [[j[0], j[1]] for j in v["judges"]],
            "hard": dcf_hard(t),
            "href": f"cards/{t}_full_widget.html",
        })
    rows.sort(key=lambda r: r["gap"])
    data = {"asOf": max(dates) if dates else None, "buyFactor": BUY_FACTOR,
            "stocks": rows, "history": history(name, {k: v.get("price") for k, v in verdicts.items()})}
    return ("// Generated by scripts/build_value_gap.py from preview v2 cards. Do not edit.\n"
            "window.ValueGap=" + json.dumps(data, ensure_ascii=False) + ";\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = build()
    if a.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("STALE - value-data.js does not match preview")
            sys.exit(1)
        print("OK - value-data.js matches preview")
        return
    OUT.write_text(text, encoding="utf-8")
    n = len(json.loads(re.search(r"=(\{.*\});", text, re.S).group(1))["stocks"])
    print(f"Wrote {OUT} ({n} cards at or cheaper than 적정~저평가)")


if __name__ == "__main__":
    main()
