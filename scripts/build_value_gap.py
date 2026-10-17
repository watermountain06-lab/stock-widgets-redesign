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
  - A quarterly count of cards whose verdict was 적정~저평가 or cheaper at least once in the
    quarter (2026-10-13; was cards under their 기준가), so a day with none reads as the usual
    state rather than as a broken page. Replay month-ends through 2026Q3, daily verdicts after.
    Each card in a quarter is shown against its 진입가 (first cheap close in the quarter).

Sources (read only): preview v2 cards through v2/research/extract_card_verdicts.js, the
{T}_DCF block of each card for `hard`, its {T}_BACKTEST (예상밴드) and {T}_VALUATION (perNA)
blocks, v2/research/verdict_replay_panel.json
and the git history of v2/daily_status.json. Names come from this
repo's stock-data.js, so run build_home.py first.

Usage: python3 scripts/build_value_gap.py [--check] [--refresh-replay]
"""
import argparse
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_set import live_tickers  # noqa: E402

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
    return (card_block(t, "DCF") or {}).get("hard") or []


QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def card_block(t, name):
    """A `const {T}_<name> = {...}` JSON block of the preview card, or None."""
    html = (PREVIEW_V2 / f"{t}_full_widget.html").read_text(encoding="utf-8")
    key = f"const {t}_{name} = "
    if key not in html:
        return None
    return json.JSONDecoder().raw_decode(html, html.index(key) + len(key))[0]


def band_on(t, day, upto, cache={}):
    """The card's 예상밴드 in force on `day`: the latest 예상밴드 백테스트 checkpoint on or before it
    (2026-10-13 user decisions - the band on the 진입일, as the Tracking tab's band_on), with the
    span it covers and the actual closing low~high over that same span, so the two are compared
    on one span, not on the calendar quarter. None for a card without bands (PER not meaningful,
    or none published by then).

    A closed checkpoint runs to the day before the next earnings and its realized range is the
    card's (closes from the checkpoint day through period_end_date - recomputing it that way from
    load_daily matched all 30 closed bands, 2026-10-13). An open one's period_end_date is only the
    day the card's backtest was last refreshed, so its range is recomputed the same way through
    `upto`, the date of the card's own 현재가; otherwise today's price could sit outside an open
    range (ACN: 214.87 > 212.30, Codex and Fable). Ending on the card's price date rather than
    stock-data's asOf keeps the two the same close even when one card was not rebuilt that day. The checkpoints are the card's own backtest as it stands today, not a
    point-in-time record."""
    if t not in cache:
        val = card_block(t, "VALUATION") or {}
        cache[t] = [] if val.get("perNA") else (card_block(t, "BACKTEST") or [])
    cps = [c for c in cache[t] if c["checkpoint_date"] <= day]
    if not cps:
        return None
    c = max(cps, key=lambda c: c["checkpoint_date"])
    # No checkpoint has empty band values today (0 of 1,764, 2026-10-13), so a gap is a data
    # error, never a reason to fall back quietly to the quarter range (Codex).
    nums = [c.get(k) for k in ("predicted_low", "predicted_high", "realized_price_low", "realized_price_high")]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in nums) or nums[0] > nums[1] or nums[2] > nums[3]:
        raise SystemExit(f"{t} {c['checkpoint_date']}: incomplete 예상밴드 checkpoint {nums}")
    out = {"from": c["checkpoint_date"], "to": c.get("period_end_date"), "open": bool(c.get("is_open")),
           "low": round(nums[0], 2), "high": round(nums[1], 2),
           "actualLow": round(nums[2], 2), "actualHigh": round(nums[3], 2)}
    if out["open"]:
        closes = [b for b in daily(t) if c["checkpoint_date"] <= b[0] <= upto]
        # the open range must end on the card's price date, the same close as the popup's 현재가
        if not closes or closes[-1][0] != upto:
            raise SystemExit(f"{t}: open 예상밴드 range ends {closes[-1][0] if closes else None}, not on its price date {upto}")
        out["to"] = closes[-1][0]
        out["actualLow"] = round(min(b[4] for b in closes), 2)
        out["actualHigh"] = round(max(b[4] for b in closes), 2)
    elif not out["from"] <= day <= out["to"]:
        raise SystemExit(f"{t}: entry {day} falls in no 예상밴드 period (last ended {out['to']})")
    return out


def daily(t, cache={}):
    """The card's own traded daily bars [date, open, high, low, close], sorted
    (build_multiple_history.load_daily). Not history_daily: for SKHY that swaps all but the last
    bar for KRX shares converted to dollars, which sit ~20% under the ADR, so an entry price from
    it against today's ADR close read +27% in four sessions."""
    if t not in cache:
        if str(PREVIEW_V2) not in sys.path:
            sys.path.insert(0, str(PREVIEW_V2))
        import build_multiple_history as bmh
        cache[t] = sorted(bmh.load_daily(t))
    return cache[t]


def quarter_bars(t, quarter, as_of):
    """daily(t) over the calendar quarter; an unfinished quarter runs to the last bar on or
    before as_of (the page's 종가 date)."""
    y, n = quarter.split("Q")
    lo, hi = f"{y}-{(int(n) - 1) * 3 + 1:02d}-01", f"{y}-{QUARTER_END[int(n)]}"
    return [b for b in daily(t) if lo <= b[0] <= min(hi, as_of)]


REPLAY_FIRST = "2024-07"  # 2024Q2 has only its June month-end in the replay panel
# User decision 2026-10-13: replay through 2026Q3, the daily record from 2026Q4 - fixed here, so
# extending the replay panel later cannot quietly swap a daily quarter for month-ends (Codex).
REPLAY_LAST, LIVE_FIRST = "2026Q3", "2026Q4"


REPLAY_SNAPSHOT = REPO / "scripts/verdict_replay_through_2026Q3.json"


def replay_verdicts(cards):
    """{(quarter, ticker): [(month-end, verdict)]} from preview's point-in-time replay
    (v2/research/verdict_replay_panel.json, 2024-06~2026-09 month-ends): the v2 rule recomputed
    each month-end with only what was filed by then. Financials, ASML, TSM, SKHY, GEV, SNDK and
    SPCX are not in the panel, so 81 of the cards are covered.

    Read from a snapshot in this repo (REPLAY_SNAPSHOT): the panel is a 5.7 MB research file preview
    keeps out of git, so the Actions auto-promotion could not read it (2026-10-15). The replay is
    fixed through REPLAY_LAST, so the snapshot does not go stale; rewrite it with --refresh-replay
    only if the panel or the v2 rule is recomputed."""
    out = defaultdict(list)
    for t, d, g in json.loads(REPLAY_SNAPSHOT.read_text(encoding="utf-8"))["rows"]:
        if t in cards:
            out[(quarter_of(d), t)].append((d, g))
    return out


def refresh_replay_snapshot():
    """Recompute the replay from preview's local panel (verdict_replay.py, numpy/scipy) and write REPLAY_SNAPSHOT."""
    import contextlib
    import io
    research = str(PREVIEW_V2 / "research")
    for path in (research, str(PREVIEW_V2)):
        if path not in sys.path:
            sys.path.insert(0, path)
    with contextlib.redirect_stdout(io.StringIO()):
        import verdict_replay as vr
        rows = json.loads((PREVIEW_V2 / "research/verdict_replay_panel.json").read_text(encoding="utf-8"))["rows"]
        vr.peer_scores(rows)  # peers are the whole S&P500 sector, so score before narrowing to cards
        vr.assign(rows)
    keep = sorted([r["t"], r["d"], r["g_V0"]] for r in rows
                  if r["m"] >= REPLAY_FIRST and quarter_of(r["d"]) <= REPLAY_LAST and r.get("g_V0"))
    REPLAY_SNAPSHOT.write_text(json.dumps({"from": "preview v2/research/verdict_replay_panel.json via verdict_replay.py",
                                           "first": REPLAY_FIRST, "last": REPLAY_LAST, "rows": keep},
                                          ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {REPLAY_SNAPSHOT} ({len(keep)} month-end verdicts)")


def live_verdicts(as_of, first_quarter, cards):
    """{(quarter, ticker): [(session, verdict)]} from the daily_status history (the record the
    Tracking tab uses), for quarters after the replay panel ends, and its first session. The
    record starts 2026-10-06, so 2026Q4's entries can be no earlier than that. Only today's
    cards, as in the replay."""
    sys.path.insert(0, str(REPO / "scripts"))
    from build_tracking import sessions
    state, _ = sessions(as_of)
    out = defaultdict(list)
    for s, v in state.items():
        if quarter_of(s) >= first_quarter:
            for t, g in v.items():
                if t in cards:
                    out[(quarter_of(s), t)].append((s, g))
    return out, min(state)


def quarter_of(day):
    return f"{day[:4]}Q{(int(day[5:7]) - 1) // 3 + 1}"


def history(name, current, as_of, priced):
    """Per calendar quarter: cards whose v2 verdict was 적정~저평가 or cheaper at least once in
    that quarter (2026-10-13 user decision - the count used to be price <= 0.9 x DCF base, a
    single judge the user does not trust on its own).

    Through 2026Q3 the verdicts are the replay's month-ends; from 2026Q4 the cards' own daily
    verdicts. Each listed card shows its 진입가 - the close on the first month-end (replay) or
    session (daily) in that quarter with a cheap verdict - and how the quarter's last close
    (finished quarters only) and today's close compare with it (2026-10-13 user decisions).
    """
    seen = replay_verdicts(set(current))
    live, live_from = live_verdicts(as_of, LIVE_FIRST, set(current))
    seen.update(live)
    running = quarter_of(as_of)
    q = defaultdict(lambda: {"total": 0, "stocks": []})
    for (quarter, t), marks in sorted(seen.items()):
        q[quarter]["total"] += 1
        hits = sorted(m[:2] for m in marks if m[1] in CHEAP)
        if not hits:
            continue
        day, verdict = hits[0]
        bars = quarter_bars(t, quarter, as_of)
        at = [b for b in bars if b[0] == day]
        if not at:
            raise SystemExit(f"{t} {quarter}: no daily bar on its entry {day}")
        entry = round(at[0][4], 2)
        # 분기 말 only for a finished quarter whose last bar is its last week (a gap would read as
        # the quarter's end), and not when the entry is that bar - the change would be 0 by construction.
        end = None
        if quarter < running:
            y, n = quarter.split("Q")
            if bars[-1][0] < (date.fromisoformat(f"{y}-{QUARTER_END[int(n)]}") - timedelta(days=7)).isoformat():
                raise SystemExit(f"{t} {quarter}: daily bars stop at {bars[-1][0]}, before the quarter's last week")
            if bars[-1][0] > day:
                end = round(bars[-1][4], 2)
        # a card whose price is older than the entry would turn "진입가 대비 현재" into a change from
        # before the entry, and cut the entry out of an open band's range (Fable)
        if priced.get(t) and priced[t] < day:
            raise SystemExit(f"{t} {quarter}: card price date {priced[t]} is before its entry {day}")
        cur = current.get(t)
        q[quarter]["stocks"].append({"ticker": t, "name": name.get(t, t), "verdict": verdict,
                                     "entryDate": day, "entryPrice": entry, "band": band_on(t, day, priced.get(t) or as_of),
                                     "endPrice": end, "endChange": round(end / entry - 1, 4) if end else None,
                                     "current": cur, "change": round(cur / entry - 1, 4) if cur else None,
                                     # the quarter's closing low~high: the yellow band when the card has no 예상밴드
                                     # (closes, like the band's actual range - Fable)
                                     "low": round(min(b[4] for b in bars), 2),
                                     "high": round(max(b[4] for b in bars), 2)})
    out = []
    for k, v in sorted(q.items()):
        v["stocks"].sort(key=lambda s: (s["entryDate"], s["ticker"]))
        out.append({"quarter": k, "under": len(v["stocks"]), "total": v["total"],
                    "running": k == running, "daily": k >= LIVE_FIRST, "stocks": v["stocks"]})
    return out, live_from


def build():
    out = subprocess.run(["node", str(PREVIEW_V2 / "research/extract_card_verdicts.js")],
                         capture_output=True, text=True, check=True).stdout
    verdicts = json.loads(out)
    live = live_tickers()   # 라이브에는 그날 시총 상위 100만(scripts/live_set.py)
    if live is not None:
        verdicts = {t: v for t, v in verdicts.items() if t in live}
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
            "stocks": rows}
    as_of = re.search(r'"asOf":\s*"([\d-]+)"', (REPO / "stock-data.js").read_text(encoding="utf-8"))[1]
    data["history"], data["liveFrom"] = history(name, {k: v.get("price") for k, v in verdicts.items()}, as_of,
                                                {k: v.get("date") for k, v in verdicts.items()})
    return ("// Generated by scripts/build_value_gap.py from preview v2 cards. Do not edit.\n"
            "window.ValueGap=" + json.dumps(data, ensure_ascii=False) + ";\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--refresh-replay", action="store_true", help="rewrite the replay snapshot from preview's local panel")
    a = ap.parse_args()
    if a.refresh_replay:
        refresh_replay_snapshot()
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
