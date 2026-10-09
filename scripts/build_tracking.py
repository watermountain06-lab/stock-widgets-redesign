#!/usr/bin/env python3
"""Build tracking-data.js: the Tracking tab (was Today) - a record of the site's v2 cheap calls
and how the price did afterwards (2026-10-09 user decisions).

What counts
  - A "call" is a stretch of consecutive sessions in which a card's v2 verdict was
    적정~저평가 or cheaper (the same line as the home 저평가 tab and value check). It
    starts at that session's close and ends at the close of the first session the verdict
    is no longer on the list; a call still on the list is "진행 중", marked to the latest close.
  - v2 only. The verdicts come from preview's v2/daily_status.json, which the daily rebuild
    commits every session with every card's verdict; its git history is the record. A call
    already on the list in the first recorded session starts there and says so.
  - "맞음" is the user's rule: the price rose over the call (price only, no dividends, no
    index comparison). Each call also shows the change from its start to today, so a call that
    left the list can still be followed.
  - The 관찰 목록 is the cards whose verdict is 적정 - one vote short by construction - shown
    folded, without returns.
  - The journal lists, per session, which cards entered or left either list and which judge
    votes moved (from daily_status verdictChanges when the change happened in that run).

Prices are the cards' own DAILY closes in this repo's cards/ (the live copies), and no session
later than stock-data.js's asOf is used, so the tab never runs ahead of the rest of the page.

Usage: python3 scripts/build_tracking.py [--check]
"""
import argparse
import json
import re
import html
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from build_home import band_position  # noqa: E402

PREVIEW = Path.home() / "Workspace/stock-widgets-preview"
STATUS = "v2/daily_status.json"
OUT = REPO / "tracking-data.js"
CHEAP = {"초저평가", "저평가", "적정~저평가"}
WATCH = {"적정"}
JUDGES = ["자기 이력", "동종업", "현금흐름"]


def git(*args):
    return subprocess.run(["git", "-C", str(PREVIEW), *args], capture_output=True, text=True, check=True).stdout


def sessions(as_of):
    """{session: {ticker: verdict}} plus {session: [verdictChanges]} from the history of daily_status.json.

    A session can have several runs (retries, partial reruns). The fullest run is the base and
    runs that finished later overlay the cards they rebuilt."""
    runs = []
    for commit in git("log", "--format=%H", "origin/main", "--", STATUS).split():
        try:
            d = json.loads(git("show", f"{commit}:{STATUS}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        if d.get("mode") not in ("daily", "weekly") or not d.get("session") or d["session"] > as_of:
            continue
        runs.append(d)
    by = {}
    for d in runs:
        by.setdefault(d["session"], []).append(d)
    # finished mixes offsets (-0400 and +0000), so compare parsed times, not strings (Codex)
    when = lambda d: datetime.fromisoformat(d["finished"]) if d.get("finished") else datetime.min.astimezone()
    state, changes, prev = {}, {}, {}
    for s in sorted(by):
        rs = sorted(by[s], key=when)
        base = max(rs, key=lambda d: (len(d.get("cards", {})), when(d)))
        v = {t: c["verdict"] for t, c in base["cards"].items() if c.get("verdict")}
        for d in rs:
            if when(d) > when(base):
                v.update({t: c["verdict"] for t, c in d.get("cards", {}).items() if c.get("verdict")})
        if len(v) < 90:
            raise SystemExit(f"{s}: only {len(v)} verdicts in daily_status - not a full session")
        # a card missing from a session is not a verdict change: keep its last seen verdict (Codex)
        state[s] = prev = {**{t: x for t, x in prev.items() if t not in v}, **v}
        # several runs in one session: first run's old votes -> last run's new votes (Codex)
        ch = {}
        for d in rs:
            for c in d.get("verdictChanges") or []:
                ch[c["ticker"]] = {**c, "old": ch[c["ticker"]]["old"]} if c["ticker"] in ch else c
        changes[s] = ch
    return state, changes


def closes(tickers):
    out = subprocess.run(["node", "-e", r"""
const fs=require('fs'),vm=require('vm');
function block(s,st){let d=0,q=null;for(let i=st;i<s.length;i++){const c=s[i];if(q){if(c==='\\'){i++;continue}if(c===q)q=null;continue}
 if(c==='"'||c==="'"||c==='`'){q=c;continue}if(c==='['||c==='{'||c==='(')d++;if(c===']'||c==='}'||c===')'){d--;if(d===0)return i+1}}}
function val(h,T,name,open){const m=h.indexOf(`const ${T}_${name} =`);if(m<0)return undefined;const k=h.indexOf(open,m);return vm.runInNewContext('('+h.slice(k,block(h,k))+')');}
const out={};for(const T of process.argv.slice(1)){const h=fs.readFileSync(`cards/${T}_full_widget.html`,'utf8');
 out[T]={close:Object.fromEntries(val(h,T,'DAILY','[').map(b=>[b[0],b[4]])),
  bt:(val(h,T,'BACKTEST','[')||[]).map(c=>[c.checkpoint_date,c.predicted_low,c.predicted_high]),
  perNA:!!((val(h,T,'VALUATION','{')||{}).perNA)};}
console.log(JSON.stringify(out));""", *tickers], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def band_on(card, session):
    """The card's 예상밴드 백테스트 band in force on `session` (the latest checkpoint on or before it), scored
    against that session's close with the home table's rule (build_home.band_position), so a past date
    shows the score it had then (2026-10-09 user decision)."""
    cps = [c for c in card["bt"] if c[0] <= session]
    b = {"perNA": card["perNA"], "low": None, "high": None, "checkpoint": None}
    if cps:
        b.update(checkpoint=cps[-1][0], low=cps[-1][1], high=cps[-1][2])
    return band_position(card["close"][session], b)


JUDGE_RE = {
    "self": r'data-vc-score="self">([^<]*)<', "selfV": r'data-vs-pill="self">([^<]*)<',
    "peer": r'data-vc-score="peer">([^<]*)<', "peerV": r'data-vs-pill="peer">([^<]*)<',
    "dcf": r'data-vs="dcf">([^<]*)<', "up": r'data-vs="upside">([^<]*)<', "dcfV": r'data-vs-pill="dcf"[^>]*>([^<]*)<',
    "peerTitle": r'title="([^"]*)">동종업 대비',
}
STEPS = ["매우 비싸다", "비싸다", "적정", "싸다", "매우 싸다"]


def judges(t):
    """The card's 밸류에이션 rows as the card prints them (자기 이력 대비 · 동종업 대비 · 현금흐름 (내재가치))."""
    h = (REPO / "cards" / f"{t}_full_widget.html").read_text(encoding="utf-8")
    j = {k: (m[1].strip() if (m := re.search(r, h)) else None) for k, r in JUDGE_RE.items()}
    title = html.unescape(j.pop("peerTitle") or "")
    # "카드 유니버스 IT 종목들보다…", "S&P500 경기소비재 종목들보다…", "같은 IT 섹터(…)보다…" → 업종 이름
    g = re.match(r"(?:카드 유니버스|S&P500|같은)\s+(.+?)\s*(?:섹터)?(?:\(.*?\))?\s*(?:종목들)?보다", title)
    j["peerGroup"] = g[1].strip() if g else None
    v = (j["dcfV"] or "").split("·")[0].strip()
    j["step"] = STEPS.index(v) if v in STEPS else None
    return j


def votes(change):
    """[[judge, old, new], ...] for the judges whose vote moved."""
    if not change:
        return []
    old, new = change["old"][0], change["new"][0]
    return [[JUDGES[i], old[i], new[i]] for i in range(min(len(old), len(new), 3)) if old[i] != new[i]]


def build():
    text = (REPO / "stock-data.js").read_text(encoding="utf-8")
    as_of = re.search(r'"asOf":\s*"([\d-]+)"', text)[1]
    names = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('{"rank"'):
            r = json.JSONDecoder().raw_decode(line)[0]
            names[r["ticker"]] = r["name"]
    state, changes = sessions(as_of)
    days = sorted(state)
    if not days:
        raise SystemExit("no v2 sessions in daily_status history")
    involved = sorted({t for s in days for t, v in state[s].items() if v in CHEAP | WATCH})
    px = closes(involved)

    def close(t, s):
        if s not in px.get(t, {}).get("close", {}):
            raise SystemExit(f"{t}: no close for {s} in cards/{t}_full_widget.html")
        return px[t]["close"][s]

    last = days[-1]
    calls = []
    for t in involved:
        start = None
        for i, s in enumerate(days + [None]):
            on = s is not None and state[s].get(t) in CHEAP
            if on and start is None:
                start = s
            elif not on and start is not None:
                end = s  # first session off the list, or None if still on it
                c0, cn = close(t, start), close(t, last)
                call = {"ticker": t, "name": names.get(t, t), "verdict": state[start][t], "start": start,
                        "startClose": c0, "fromStart": start == days[0], "now": cn,
                        "sinceStart": round(cn / c0 - 1, 4)}
                if end:
                    ce = close(t, end)
                    call.update(end=end, endClose=ce, endVerdict=state[end].get(t), onList=round(ce / c0 - 1, 4),
                                result="up" if ce > c0 else "down")
                else:
                    call.update(end=None, result="open", onList=round(cn / c0 - 1, 4))
                calls.append(call)
                start = None
    calls.sort(key=lambda c: (c["end"] is not None, c["start"], c["ticker"]))

    journal = []
    for prev, s in zip(days, days[1:]):
        for kind, group in (("list", CHEAP), ("watch", WATCH)):
            a = {t for t, v in state[prev].items() if v in group}
            b = {t for t, v in state[s].items() if v in group}
            for t in sorted(b - a):
                journal.append({"session": s, "list": kind, "move": "in", "ticker": t, "name": names.get(t, t),
                                "from": state[prev].get(t), "to": state[s][t], "votes": votes(changes[s].get(t)),
                                "close": close(t, s)})
            for t in sorted(a - b):
                journal.append({"session": s, "list": kind, "move": "out", "ticker": t, "name": names.get(t, t),
                                "from": state[prev][t], "to": state[s].get(t), "votes": votes(changes[s].get(t)),
                                "close": close(t, s)})
    # 관찰 목록 → 저평가 목록(또는 반대)으로 옮긴 것은 한 사건이라 저평가 목록 줄만 남긴다
    moved = {(j["session"], j["ticker"]) for j in journal if j["list"] == "list"}
    journal = [j for j in journal if j["list"] == "list" or (j["session"], j["ticker"]) not in moved]
    journal.sort(key=lambda j: (j["list"] != "list", j["ticker"]))
    journal.sort(key=lambda j: j["session"], reverse=True)

    current = sorted(t for t, v in state[last].items() if v in CHEAP)
    watch = sorted(t for t, v in state[last].items() if v in WATCH)
    # 종목 요약(카드 '종합 해석')과 최근 타임라인 5건 — 지금 목록·관찰 목록 종목만
    tl = json.loads(subprocess.run(["node", str(REPO / "scripts/extract_card_timelines.js")],
                                   capture_output=True, text=True, check=True).stdout)
    detail = {}
    for t in sorted(set(current + watch) | {t for s in days for t, v in state[s].items() if v in CHEAP}):
        if "error" in tl.get(t, {"error": 1}):
            raise SystemExit(f"{t}: card timeline/summary extraction failed")
        detail[t] = {"summary": tl[t]["summary"], "news": tl[t]["items"][:5]}
    # 날짜 버튼(2026-10-09): 회차마다 그날의 저평가·관찰 목록, 목록 종목의 그날 종가·판정·밴드 점수
    day_rows = []
    for s in days:
        lst = sorted(t for t, v in state[s].items() if v in CHEAP)
        day_rows.append({"session": s, "list": lst, "watch": sorted(t for t, v in state[s].items() if v in WATCH),
                         "cards": {t: {"close": close(t, s), "verdict": state[s][t], "band": band_on(px[t], s)}
                                   for t in lst}})
    listed = sorted({t for d in day_rows for t in d["list"]})
    closes_by = {t: {s: close(t, s) for s in days if s in px[t]["close"]} for t in sorted({c["ticker"] for c in calls})}
    data = {"asOf": last, "firstSession": days[0], "sessions": days, "calls": calls, "journal": journal,
            "current": current, "watch": watch, "detail": detail,
            "days": day_rows, "closes": closes_by, "judges": {t: judges(t) for t in listed}}
    return ("// Generated by scripts/build_tracking.py from preview daily_status history and cards/. Do not edit.\n"
            "window.TrackingData=" + json.dumps(data, ensure_ascii=False) + ";\n"), data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text, data = build()
    if a.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("STALE - tracking-data.js does not match preview history")
            sys.exit(1)
        print(f"OK - tracking-data.js matches ({len(data['calls'])} calls, {data['firstSession']}~{data['asOf']})")
        return
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} ({len(data['calls'])} calls, {len(data['journal'])} journal rows, "
          f"{data['firstSession']}~{data['asOf']})")


if __name__ == "__main__":
    main()
