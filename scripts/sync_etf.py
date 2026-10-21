#!/usr/bin/env python3
"""preview ETF 카드·홈 ETF 데이터 → 라이브(2026-10-21 사용자 결정, 설계 dr 5라운드 합의).

preview가 매일 만드는 `preview-only-etf-data.js`·`preview-only-etf-<티커>.html`을 검증해 라이브 `etf-data.js`·`etf-<티커>.html`로
쓴다. 판정은 preview와 같다(사용자 결정) — 종목 카드 링크만 라이브 `cards/`(그날 상위 100)로 바꾸고, 라이브에 카드가 없는
종목은 회색 이름(링크 없음)으로 둔다. 판정형 페이지에는 "전체 분석 카드 N장 기준" 안내 줄을 넣는다.

입력은 preview 한 커밋(--rev)에서 `git show`로 읽는다(데이터·페이지·card JSON·홈 index.html — 같은 생성 묶음). 하나라도
검증에 어긋나면 preview에서 아무것도 가져오지 않고(입력 거부), 라이브에 이미 있는 묶음을 같은 검사로 확인한 뒤 링크만
오늘 카드 집합으로 다시 맞춘다. ETF 목록은 라이브 `etf.js`의 ORDER(화면 코드 — 손 승격으로만 바뀜).

    python3 scripts/sync_etf.py --session 2026-10-20 [--rev <preview 커밋>] [--pv ~/Workspace/stock-widgets-preview] [--check]

종료 코드: 0 정상(썼거나 같음; --check면 같음) · 1(--check) 바뀔 것 있음 · 4 입력 거부(기존 묶음 링크만 다시 맞춤) ·
5 입력 거부 + 기존 묶음도 없거나 깨짐, 또는 preview 유출 검사기가 ETF 공용화 전 버전(→ 카드 승격도 멈춘다) · 2 오류.
"""
import argparse
import html
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

LIVE = Path(__file__).resolve().parents[1]
PV_DEFAULT = Path.home() / "Workspace" / "stock-widgets-preview"
TIERS = ['저평가', '적정~저평가', '적정', '적정~고평가', '고평가', '카드 없음', '판정 보류', '그 밖 제외', '분류 안 됨']
SECTIONS = ("returns", "monthly", "holdings", "news", "verdict")
VERDICT_KEYS = ("status", "reason", "verdict", "nbar", "coverage", "S", "builtFor")   # preview etf_consistency와 같은 칸
TICK = r"[A-Za-z0-9.\-]+"
DATA_HEAD = "// 라이브 ETF 요약(scripts/sync_etf.py가 preview에서 옮긴다 — 손으로 고치지 않는다)\n"
STYLE = ('<style id="etf-live-style">.no-live,.tchip.no-live{color:var(--text3)!important;opacity:.5;cursor:default}'
         '.live-note{margin:0 0 10px}</style>')   # 칩(tchip) 글자색보다 앞서게 — 회색 이름이 링크와 구분되게


class Reject(Exception):
    """입력 거부 — preview에서 아무것도 가져오지 않는다."""


class Fatal(Exception):
    """종료 5 — 카드 승격도 멈춘다."""


# ---------- 목록·형식 ----------

def read_order(live):
    """라이브 etf.js의 ORDER(ETF 순서)와 PRICE_ONLY(가격형과 그 대조 방식)."""
    js = (live / "etf.js").read_text(encoding="utf-8")
    m = re.search(r"var ORDER = \[([^\]]*)\];", js)
    p = re.search(r"var PRICE_ONLY = \{([^}]*)\};", js)
    if not m or not p:
        raise ValueError("etf.js에서 ORDER·PRICE_ONLY를 읽지 못함")
    item = r"\s*'[A-Z]{1,5}'\s*"
    if not re.fullmatch(rf"{item}(?:,{item})*", m.group(1)):
        raise ValueError(f"ORDER 형식이 지원하는 모양(작은따옴표 티커, 쉼표)이 아님: {m.group(1)!r}")
    pitem = r"\s*[A-Z]{1,5}\s*:\s*'(?:day|history)'\s*"
    if not re.fullmatch(rf"{pitem}(?:,{pitem})*", p.group(1)):
        raise ValueError(f"PRICE_ONLY 형식이 지원하는 모양이 아님: {p.group(1)!r}")
    order = re.findall(r"'([A-Z]{1,5})'", m.group(1))
    price = dict(re.findall(r"([A-Z]{1,5})\s*:\s*'([a-z]+)'", p.group(1)))
    if not order or len(set(order)) != len(order) or not all(re.fullmatch(r"[A-Z]{1,5}", t) for t in order):
        raise ValueError(f"ORDER 형식 이상: {order}")
    if not set(price) <= set(order):
        raise ValueError("PRICE_ONLY에 ORDER 밖 티커")
    return order, price


def fin(x):
    try:   # 아주 큰 정수(JSON 10**400 등)는 isfinite에서 OverflowError — 숫자 아님으로 본다(구현 dr r2)
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    except OverflowError:
        return False


def is_day(s):
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return False
    try:
        return date.fromisoformat(s).isoformat() == s
    except ValueError:
        return False


def valid_verdict(d):
    """etf.js valid()와 같은 조건."""
    if not isinstance(d, dict) or d.get("status") not in ("ok", "held"):
        return False
    if d["status"] == "held":
        return isinstance(d.get("reasonText"), str)
    if d.get("verdict") not in TIERS[:5] or not fin(d.get("nbar")) or not -4 <= d["nbar"] <= 3:
        return False
    if not fin(d.get("coverage")) or not 0.7 <= d["coverage"] <= 1:
        return False
    bar = d.get("bar")
    if not isinstance(bar, dict) or not all(fin(bar.get(k)) and 0 <= bar[k] <= 1 for k in TIERS):
        return False
    if abs(sum(bar[k] for k in TIERS) - 1) > 1e-6 or abs(sum(bar[k] for k in TIERS[:5]) - d["coverage"]) > 1e-6:
        return False
    top = d.get("top")
    if not isinstance(top, list) or not all(isinstance(t, dict) and isinstance(t.get("company"), str) and fin(t.get("weight"))
                                            and 0 <= t["weight"] <= 1 for t in top):
        return False
    if d.get("expense") is not None and not (isinstance(d["expense"], dict) and fin(d["expense"].get("pct"))):
        return False
    pd = d.get("pending")
    if pd is not None and not (isinstance(pd, dict) and pd.get("kind") in ("issuer_lag", "home_lag") and isinstance(pd.get("P"), str)):
        return False
    return isinstance(d.get("S"), str)


def valid_price(t, d, want):
    """etf.js validPrice()와 같은 조건(want = PRICE_ONLY[t])."""
    if not isinstance(d, dict) or d.get("kind") != "price" or d.get("etf") != t or d.get("status") not in ("ok", "held") \
            or not isinstance(d.get("builtFor"), str):
        return False
    if d["status"] == "held":
        return isinstance(d.get("reasonText"), str)
    if not (fin(d.get("close")) and d["close"] > 0 and fin(d.get("chg")) and fin(d.get("ret1y")) and isinstance(d.get("S"), str)):
        return False
    if d.get("check") is None:
        return t == "IWM" and isinstance(d.get("navDate"), str)
    b, pv = d["builtFor"], d.get("prevSession")
    if d["check"] != want or d["S"] != b or not is_day(b) or not is_day(pv) or not pv < b:
        return False
    if d["check"] == "day":
        return is_day(d.get("navDate")) and d["navDate"] in (b, pv)
    if not (is_day(d.get("since")) and is_day(d.get("checkedThrough")) and d["since"] <= d["checkedThrough"]):
        return False
    return (d["checkedThrough"] == b and d.get("pendingDate") is None) or (d["checkedThrough"] == pv and d.get("pendingDate") == b)


def parse_data(text, prefix_ok=("// ",)):
    """`// …\\nwindow.ETF_DATA = {…};` → dict. 모양이 다르거나 JSON이 이상하면 Reject(중복 키·NaN·Infinity 거부)."""
    lines = text.split("\n", 1)
    if len(lines) != 2 or not lines[0].startswith(prefix_ok):
        raise Reject("데이터 파일 첫 줄이 주석이 아님")
    body = lines[1].strip()
    if not (body.startswith("window.ETF_DATA = ") and body.endswith(";")):
        raise Reject("데이터 파일 모양이 window.ETF_DATA = {…}; 가 아님")

    def no_dup(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise Reject("데이터 JSON에 중복 키")
        return dict(pairs)

    def no_const(x):
        raise Reject(f"데이터 JSON에 {x}")
    try:
        d = json.loads(body[len("window.ETF_DATA = "):-1], object_pairs_hook=no_dup, parse_constant=no_const)
    except ValueError as e:
        raise Reject(f"데이터 JSON 파싱 실패: {e}")
    if not isinstance(d, dict):
        raise Reject("데이터가 객체가 아님")
    return d


def check_slots(data, order, price, session):
    """칸 검사 + 승격용 날짜 규칙(모든 칸 builtFor 실제 날짜, ok 칸 S 실제 날짜, 미래 금지)."""
    for t in order:
        d = data.get(t)
        if not isinstance(d, dict) or d.get("etf") != t:
            raise Reject(f"{t} 칸 없음·etf 불일치")
        ok = valid_price(t, d, price[t]) if t in price else valid_verdict(d)
        if not ok:
            raise Reject(f"{t} 칸 형식 오류(홈 JS 검사와 같은 조건)")
        if not is_day(d.get("builtFor")):
            raise Reject(f"{t} builtFor가 날짜가 아님: {d.get('builtFor')!r}")
        if d["status"] == "ok" and not is_day(d.get("S")):
            raise Reject(f"{t} S가 날짜가 아님: {d.get('S')!r}")
        if session and d["builtFor"] > session:
            raise Reject(f"{t} builtFor {d['builtFor']}가 승격 세션 {session}보다 뒤")


def session_ok(d, session):
    """홈 화면이 이 세션에 값을 보이는가(etf.js 묵음 규칙과 같게) — 아니면 WARN."""
    if d.get("builtFor") == session:
        return True
    pd = d.get("pending") if d.get("status") == "ok" else None
    return bool(isinstance(pd, dict) and pd.get("kind") == "issuer_lag" and pd.get("P") == session)


# ---------- 페이지 ----------

def kdate(s):
    return s.replace("-", ".") if s else "—"


def page_facts(t, page):
    """페이지에서 읽는 대조용 값: header 상태, 현재가 날짜·종가, 판정 탭 data-etf."""
    if not page.rstrip().endswith("</html>"):
        raise Reject(f"{t} 페이지가 </html>로 끝나지 않음(잘림)")
    for sec in SECTIONS:
        if len(re.findall(r'<div id="%s" class="section"' % sec, page)) != 1:
            raise Reject(f"{t} 페이지에 #{sec} 섹션이 정확히 하나가 아님")
    hs = re.findall(r'<div class="header" data-status="([a-z]+)"', page)
    cur = re.findall(r'현재가 \(([0-9.]+|—)\)', page)
    if len(hs) != 1 or len(cur) != 1:
        raise Reject(f"{t} 페이지 머리(상태·현재가 날짜)를 읽지 못함")
    pm = re.findall(r'<div class="price-main">(.*?)</div>', page, re.S)
    close = None
    if len(pm) == 1:
        nums = re.findall(r"(?<![0-9.,+%])([0-9][0-9,]*\.[0-9]{2})(?![0-9%])", re.sub(r"<[^>]+>", " ", pm[0]))
        close = float(nums[-1].replace(",", "")) if nums else None
    v = re.findall(r'<div id="verdict" class="section" data-etf="([^"]*)"', page)
    ve = None
    if v:
        try:
            ve = json.loads(html.unescape(v[0]))
        except ValueError:
            raise Reject(f"{t} 판정 탭 data-etf를 읽지 못함")
    return {"status": hs[0], "S": cur[0], "close": close, "verdict": ve}


def same_num(a, b, tol=1e-9):
    return fin(a) and fin(b) and abs(a - b) <= tol


def check_bundle(t, slot, page, card, is_price):
    """같은 생성 묶음인가. 페이지 머리는 시세 상태 — card JSON과(있을 때), 가격형은 데이터 칸과도. 판정형 데이터 칸은 data-etf와만."""
    f = page_facts(t, page)
    if card is not None:
        if f["status"] != card.get("status") or f["S"] != kdate(card.get("S")) or (card.get("builtFor") is None):
            raise Reject(f"{t} 페이지 머리와 card JSON이 다름(상태 {f['status']}·{card.get('status')}, 날짜 {f['S']}·{card.get('S')})")
        if card.get("status") == "ok" and not (f["close"] is not None and abs(f["close"] - card.get("close", float("nan"))) < 0.005):
            raise Reject(f"{t} 페이지 머리 종가 {f['close']}와 card JSON 종가 {card.get('close')}가 다름")
    if is_price:
        if f["status"] != slot["status"] or (slot["status"] == "ok" and f["S"] != kdate(slot.get("S"))):
            raise Reject(f"{t} 가격형 페이지 머리와 데이터 칸이 다름")
        if slot["status"] == "ok" and not (f["close"] is not None and abs(f["close"] - slot["close"]) < 0.005):
            raise Reject(f"{t} 가격형 페이지 머리 종가 {f['close']}와 데이터 칸 종가 {slot['close']}가 다름")
        if card is not None:
            if card.get("builtFor") != slot["builtFor"] or card.get("status") != slot["status"]:
                raise Reject(f"{t} card JSON과 데이터 칸의 세션·상태가 다름")
            if slot["status"] == "ok" and not (same_num(card.get("close"), slot["close"], 1e-6) and same_num(card.get("chg"), slot["chg"], 1e-12)):
                raise Reject(f"{t} card JSON과 데이터 칸의 종가·등락이 다름")
    else:
        ve = f["verdict"]
        if not isinstance(ve, dict) or any(ve.get(k) != slot.get(k) for k in VERDICT_KEYS):
            raise Reject(f"{t} 판정 탭 data-etf와 데이터 칸이 다름")
    return f


# ---------- 변환 ----------

def attrs_of(s):
    return re.findall(r'([A-Za-z_:][\w:.\-]*)="([^"]*)"', s)


def build_attrs(pairs):
    return "".join(f' {k}="{v}"' for k, v in pairs)


def relink(page, cards):
    """종목 카드 링크 세 모양(원본 a, 라이브 a, 라이브 span)을 오늘 카드 집합으로. class·내용은 보존."""
    def one(tag, attr_s, inner, x_href):
        pairs = attrs_of(attr_s)
        if re.sub(r'([A-Za-z_:][\w:.\-]*)="([^"]*)"', "", attr_s).strip():
            raise Reject(f"카드 링크 요소에 지원하지 않는 속성 표기: {attr_s.strip()[:80]!r}")
        dc = dict(pairs).get("data-card")
        x = x_href or dc
        if dc and x_href and dc != x_href:
            raise Reject(f"data-card {dc}와 링크 {x_href}가 다름")
        if not re.fullmatch(TICK, x or ""):
            raise Reject(f"종목 이름 이상: {x!r}")
        keep = [(k, v) for k, v in pairs if k not in ("href", "data-card", "class")]
        cls = [c for c in dict(pairs).get("class", "").split() if c != "no-live"]
        if x in cards:
            out = [("href", f"cards/{x}_full_widget.html")] + ([("class", " ".join(cls))] if cls else []) + keep + [("data-card", x)]
            return f"<a{build_attrs(out)}>{inner}</a>"
        out = [("class", " ".join(cls + ["no-live"]))] + keep + [("data-card", x)]
        return f"<span{build_attrs(out)}>{inner}</span>"

    def a_sub(m):
        attr_s, inner = m.group(1), m.group(2)
        h = re.search(r'\bhref="(?:cards/)?(%s)_full_widget\.html"' % TICK, attr_s)
        if not h:
            return m.group(0)
        return one("a", attr_s, inner, h.group(1))

    def span_sub(m):
        attr_s, inner = m.group(1), m.group(2)
        if "no-live" not in dict(attrs_of(attr_s)).get("class", "").split() or "data-card" not in attr_s:
            return m.group(0)
        return one("span", attr_s, inner, None)

    page = re.sub(r"<a\b([^>]*)>(.*?)</a>", a_sub, page, flags=re.S)
    return re.sub(r"<span\b([^>]*)>((?:(?!<span\b).)*?)</span>", span_sub, page, flags=re.S)


def note_html(n):
    return (f'<div class="note live-note" data-base-cards="{n}">판정과 \'카드가 있는 종목\'은 전체 분석 카드 {n}장 기준이다 — '
            '이 사이트에는 시가총액 상위 100종목 카드만 있다. 회색 이름은 이 사이트에 카드가 없는 종목이다.</div>')


def add_notes(page, n):
    """판정형 페이지의 #holdings·#verdict 첫머리에 안내 줄 — 후보에 옛 안내 줄이 있으면 새 N으로 바꾼다(relink 경로는 이 함수를 쓰지 않아 기존 N 유지)."""
    for sec in ("holdings", "verdict"):
        m = re.search(r'<div id="%s" class="section"[^>]*>' % sec, page)
        if not m:
            raise Reject(f"#{sec} 섹션을 못 찾음")
        rest = page[m.end():]
        old = re.match(r'\s*<div class="note live-note"[^>]*>.*?</div>', rest, re.S)
        if old:   # 후보에 이미 있으면 새 N으로 바꾼다
            rest = rest[old.end():]
        page = page[:m.end()] + "\n" + note_html(n) + rest
    return page


def transform(page, cards, n, verdict_type):
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)   # preview 작업 메모를 라이브에 내지 않는다(script 안 JS 주석은 그대로)
    page = relink(page, cards)
    if verdict_type:
        page = add_notes(page, n)
    return live_style(page)


def live_style(page):
    """라이브 전용 스타일 한 덩이 — 없으면 넣고, 있으면 지금 STYLE로 바꾼다(스타일을 고치면 기존 페이지에도 반영)."""
    if 'id="etf-live-style"' in page:
        return re.sub(r'<style id="etf-live-style">.*?</style>', lambda m: STYLE, page, count=1, flags=re.S)
    if page.count("</head>") != 1:
        raise Reject("</head>가 정확히 하나가 아님")
    return page.replace("</head>", STYLE + "\n</head>")


def post_check(t, page, cards, live, verdict_type, needles):
    # 변환기와 따로: script 밖의 모든 태그에서 카드 파일 이름이 나오면, 그 태그는 정확히 href="cards/<X>_full_widget.html" 한 번이고
    # X가 오늘 라이브 카드여야 한다(작은따옴표·띄어 쓴 = 등 변환기가 모르는 표기는 여기서 걸린다).
    body = re.sub(r"<script\b.*?</script>", "", page, flags=re.S | re.I)
    for tag in re.findall(r"<[^<>]*_full_widget\.html[^<>]*>", body):
        hits = re.findall(r'\shref="cards/(%s)_full_widget\.html"' % TICK, tag)
        if len(hits) != 1 or len(re.findall(r"\bhref\b", tag, re.I)) != 1 or not re.match(r"<a\s", tag) \
                or tag.count("_full_widget.html") != 1 or hits[0] not in cards \
                or not (live / "cards" / f"{hits[0]}_full_widget.html").is_file():
            raise Reject(f"{t} 페이지 카드 링크가 라이브 카드를 가리키지 않음: {tag[:120]}")
    if re.search(r"_full_widget\.html", re.sub(r"<[^<>]*>", "", body)):
        raise Reject(f"{t} 페이지 본문 글자에 카드 파일 이름이 있음(링크 표기 이상)")
    if "<!--" in page:
        raise Reject(f"{t} 페이지에 HTML 주석이 남음")
    hit = [x for x in needles if x in page]
    if hit:
        raise Reject(f"{t} 페이지에 preview 전용 표식: {hit}")
    if verdict_type:
        notes_ok(t, page)


def notes_ok(t, page):
    """판정형: #holdings·#verdict 첫머리에 각각 안내 줄 하나, N은 양의 정수. 페이지 전체에 정확히 두 줄."""
    if page.count('class="note live-note"') != 2:
        raise Reject(f"{t} 판정형 페이지에 안내 줄이 둘이 아님")
    for sec in ("holdings", "verdict"):
        m = re.search(r'<div id="%s" class="section"[^>]*>\s*<div class="note live-note" data-base-cards="([1-9][0-9]*)">' % sec, page)
        if not m:
            raise Reject(f"{t} #{sec} 첫머리에 안내 줄(양의 정수 N)이 없음")


# ---------- 입력 ----------

def git_show(pv, rev, path):
    r = subprocess.run(["git", "-C", str(pv), "show", f"{rev}:{path}"], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8")


def load_checker(pv, rev, path=None):
    """preview 유출 검사기(ETF_REV 버전 하나로 고정). NEEDLES에 ETF_DATA가 있으면 공용화 전 버전 → Fatal."""
    path = path or os.environ.get("LEAK_CHECKER")
    if not path:
        src = git_show(pv, rev, "pipeline/site_ui/check_live_leak.py")
        if src is None:
            raise Fatal("preview 유출 검사기를 읽지 못함")
        fd, path = tempfile.mkstemp(suffix="_check_live_leak.py")
        os.write(fd, src.encode("utf-8"))
        os.close(fd)
    spec = importlib.util.spec_from_file_location("check_live_leak_pinned", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    needles = list(mod.NEEDLES)
    if "ETF_DATA" in needles:
        raise Fatal("preview 검사기가 ETF 공용화 전 버전(NEEDLES에 ETF_DATA) — preview 커밋을 먼저 올려야 한다")
    return needles, path


def live_cards(live):
    return {p.name[:-len("_full_widget.html")] for p in (live / "cards").glob("*_full_widget.html")}


def home_count(index_html):
    if index_html is None:
        raise Reject("preview index.html 없음")
    n = len(re.findall(r'^\s*\{"rank": \d+, "ticker": "', index_html, re.M))
    if n < 1:
        raise Reject("preview index.html에서 종목 수를 읽지 못함")
    return n


def candidate(pv, rev, live, order, price, session, cards, needles):
    """preview 커밋 하나에서 결과 묶음(파일 이름 → 내용)을 만든다. 어긋나면 Reject."""
    raw = git_show(pv, rev, "preview-only-etf-data.js")
    if raw is None:
        raise Reject(f"{rev}에 preview-only-etf-data.js 없음")
    data = parse_data(raw)
    check_slots(data, order, price, session)
    n = home_count(git_show(pv, rev, "index.html"))
    out = {}
    for t in order:
        page = git_show(pv, rev, f"preview-only-etf-{t.lower()}.html")
        cj = git_show(pv, rev, f"v2/etf/{t}_card.json")
        if page is None or cj is None:
            raise Reject(f"{t} 페이지 또는 card JSON 없음")
        try:
            card = json.loads(cj)
        except ValueError:
            raise Reject(f"{t} card JSON 파싱 실패")
        if not (isinstance(card, dict) and card.get("status") in ("ok", "held") and is_day(card.get("builtFor"))
                and (card.get("S") is None or is_day(card.get("S")))
                and (card["status"] != "ok" or (is_day(card.get("S")) and fin(card.get("close")) and fin(card.get("chg"))))):
            raise Reject(f"{t} card JSON 형식 오류")
        try:
            check_bundle(t, data[t], page, card, t in price)
            page = transform(page, cards, n, t not in price)
            post_check(t, page, cards, live, t not in price, needles)
        except (TypeError, ValueError, AttributeError, KeyError) as e:   # 후보 입력 불량은 오류(2)가 아니라 입력 거부
            raise Reject(f"{t} 입력 처리 실패: {type(e).__name__}: {e}")
        out[f"etf-{t.lower()}.html"] = page
    clean = {t: data[t] for t in order}
    out["etf-data.js"] = DATA_HEAD + "window.ETF_DATA = " + json.dumps(clean, ensure_ascii=False) + ";\n"
    return out, clean


def existing(live, order, price, cards, needles, session=""):
    """라이브에 있는 묶음을 같은 검사로(card JSON 대조만 뺌). 통과하면 링크만 다시 맞춘 결과, 아니면 Fatal."""
    try:
        data = parse_data((live / "etf-data.js").read_text(encoding="utf-8"))
        check_slots(data, order, price, session)   # 미래 날짜 금지 포함 — 날짜 규칙 전부
        out = {}
        for t in order:
            page = (live / f"etf-{t.lower()}.html").read_text(encoding="utf-8")
            check_bundle(t, data[t], page, None, t in price)
            if t not in price:
                notes_ok(t, page)
            page = live_style(relink(page, cards))
            post_check(t, page, cards, live, t not in price, needles)
            out[f"etf-{t.lower()}.html"] = page
        return out, data
    except (Reject, OSError, TypeError, ValueError, AttributeError, KeyError) as e:
        raise Fatal(f"기존 라이브 ETF 묶음도 쓸 수 없음: {e}")


# ---------- 쓰기 ----------

def write_bundle(live, files):
    """모두 임시 파일로 쓴 뒤 차례로 바꾼다. 중간에 실패하면 이미 바꾼 파일을 원본 바이트로 되돌린다(없던 파일은 지움)."""
    orig = {name: ((live / name).read_bytes() if (live / name).exists() else None) for name in files}
    tmps = {}
    try:
        for name, text in files.items():
            tmp = live / (name + ".tmp")
            tmps[name] = tmp   # 쓰다 실패해도 지우도록 먼저 등록
            tmp.write_text(text, encoding="utf-8")
        done = []
        try:
            for name, tmp in tmps.items():
                os.replace(tmp, live / name)
                done.append(name)
        except Exception:
            for name in done:
                if orig[name] is None:
                    (live / name).unlink(missing_ok=True)
                else:
                    (live / name).write_bytes(orig[name])
            raise
    finally:
        for tmp in tmps.values():
            tmp.unlink(missing_ok=True)


def changed(live, files):
    return [n for n, text in files.items() if not (live / n).exists() or (live / n).read_text(encoding="utf-8") != text]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pv", default=str(PV_DEFAULT))
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--live", default=str(LIVE))
    ap.add_argument("--session", required=True, help="승격 세션(preview v2/daily_status.json session) — 미래 builtFor 거부와 세션 경고에 쓴다")
    ap.add_argument("--leak-checker", default=None, help="고정한 preview 유출 검사기 파일(기본: 환경 변수 LEAK_CHECKER, 없으면 --rev에서 꺼냄)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    live, pv = Path(a.live), Path(a.pv)
    try:
        order, price = read_order(live)
        needles, _ = load_checker(pv, a.rev, a.leak_checker)
        cards = live_cards(live)
        old = None
        try:
            old_data = parse_data((live / "etf-data.js").read_text(encoding="utf-8"))
            check_slots(old_data, order, price, a.session)
            old = old_data
        except (Reject, OSError):
            old = None   # 기존 묶음 날짜를 믿을 수 없으면 역행 비교를 하지 않는다
        rc = 0
        try:
            files, data = candidate(pv, a.rev, live, order, price, a.session, cards, needles)
            if old:
                back = [t for t in order if data[t]["builtFor"] < old[t]["builtFor"]]
                if back:
                    raise Reject(f"역행: {back}의 builtFor가 라이브 기존 값보다 이르다")
        except Reject as e:
            print(f"ETF 입력 거부: {e}")
            files, data = existing(live, order, price, cards, needles, a.session)
            rc = 4
        warn = [t for t in order if a.session and not session_ok(data[t], a.session)]
        if warn:
            print(f"WARN ETF 세션: {warn}는 홈 세션 {a.session}에 값을 보이지 않는다(갱신 대기)")
        ch = changed(live, files)
        print(f"ETF {'입력 거부 — 기존 묶음 링크만' if rc == 4 else '후보 채택'}: 바뀔 파일 {ch or '없음'}"
              + ("" if rc == 4 else f" · session_ok={int(not warn)}"))
        if a.check:
            return rc if rc else (1 if ch else 0)
        if ch:
            write_bundle(live, {n: files[n] for n in ch})
        return rc
    except Fatal as e:
        print(f"ETF 멈춤: {e}")
        return 5
    except Exception as e:   # noqa: BLE001
        print(f"ETF 오류: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
