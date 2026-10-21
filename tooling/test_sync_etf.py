"""scripts/sync_etf.py 시험(2026-10-21). 입력은 이 파일이 만드는 고정 가짜 preview(임시 git 저장소) — 그날 preview 산출물에
기대지 않는다(자동 승격 안에서 돌기 때문, 구현 dr r1). 실제 preview 저장본으로도 돌리려면 ETF_TEST_PV=<경로>.

링크 변환(라이브 카드 있음 → cards/, 없음 → 회색 이름, 다시 들면 복원, class 보존, 지원 않는 표기 거부), 입력 거부(칸·페이지·
card JSON·묶음·날짜·유출 표식·역행) → 기존 묶음 링크만(종료 4), 기존 묶음도 없음·미래 날짜 → 5, 검사기 옛 버전 → 5, ORDER 형식 → 2,
묶음 쓰기 실패 → 원본 복구, 홈 JS와 같은 칸 검사, build_static의 dist 정리.
"""
import contextlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sync_etf as S  # noqa: E402

P, Q = "2026-10-20", "2026-10-19"
CHECKER = 'NEEDLES = ["preview-only", "PreviewOnly", "range-bar", "STOCKS_DATA_START", "pf-lock"]\n'
TICKS = ["AAPL", "MSFT", "NVDA", "BRK-B", "ZZZ"]          # 라이브 카드: 앞의 셋만
LIVE_CARDS = {"AAPL", "MSFT", "NVDA"}


def order():
    return S.read_order(ROOT)


def verdict_slot(t):
    bar = {k: 0.0 for k in S.TIERS}
    bar.update({"적정": 0.5, "고평가": 0.3, "카드 없음": 0.2})
    return {"etf": t, "name": t, "status": "ok", "reason": None, "reasonText": None, "verdict": "적정~고평가", "nbar": -2.0,
            "coverage": 0.8, "range": [-2.5, -1.0], "bar": bar, "top": [{"company": "A", "weight": 0.1}],
            "S": P, "builtFor": P, "ruleVersion": "etf-v1", "pending": None}


def price_slot(t, check):
    d = {"etf": t, "kind": "price", "status": "ok", "builtFor": P, "S": P, "check": check, "prevSession": Q,
         "close": 100.25, "chg": 0.01, "ret1y": 0.1}
    if check == "day":
        d["navDate"] = P
    else:
        d.update(since="2016-10-19", checkedThrough=P, pendingDate=None)
    return d


def page(t, slot, card, links=True, extra=""):
    ok = card["status"] == "ok"
    price = f'<span class="price-change">▲ +0.34%</span> {card["close"]:,.2f}' if ok else "—"
    chips = "".join(f'<a class="tchip" href="{x}_full_widget.html"><i style="background:#000"></i>{x}</a>' for x in TICKS) if links else ""
    top = '<a href="MSFT_full_widget.html">MICROSOFT</a>' if links else ""
    vattr = f' data-etf="{html.escape(json.dumps({k: slot.get(k) for k in S.VERDICT_KEYS}, ensure_ascii=False), quote=True)}"' if links else ""
    return ('<!DOCTYPE html>\n<html><head>\n<!-- 지수 카드 머리: NVDA_full_widget.html의 <head> -->\n<style>.x{}</style>\n</head><body>\n'
            f'<div class="header" data-status="{card["status"]}"><div>현재가 ({S.kdate(card.get("S"))})</div>'
            f'<div class="price-main">{price}</div></div>\n'
            '<div id="returns" class="section"></div><div id="monthly" class="section"></div>\n'
            f'<div id="holdings" class="section"><div class="card">{top}{chips}</div></div>\n<div id="news" class="section"></div>\n'
            f'<div id="verdict" class="section"{vattr}>판정</div>\n{extra}'
            '<script>// 종목 카드(NVDA_full_widget.html) 코드 — if (a < b) {}</script>\n</body></html>\n')


def bundle():
    """가짜 preview 파일 묶음 {경로: 글}."""
    o, price = order()
    data, files = {}, {}
    for t in o:
        slot = price_slot(t, price[t]) if t in price else verdict_slot(t)
        card = {"status": "ok", "S": P, "builtFor": P, "close": slot.get("close", 500.5), "chg": slot.get("chg", 0.002)}
        data[t] = slot
        files[f"v2/etf/{t}_card.json"] = json.dumps(card)
        files[f"preview-only-etf-{t.lower()}.html"] = page(t, slot, card, links=t not in price)
    files["preview-only-etf-data.js"] = "// preview\nwindow.ETF_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n"
    files["index.html"] = "var DATA = [\n" + "".join(f'    {{"rank": {i}, "ticker": "T{i}"}},\n' for i in range(1, 8)) + "];\n"
    files["pipeline/site_ui/check_live_leak.py"] = CHECKER
    return files


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout


class SyncEtfTest(unittest.TestCase):
    def setUp(self):
        self.saved_env = os.environ.pop("LEAK_CHECKER", None)   # 자동 승격이 export한 검사기를 물려받지 않는다(구현 dr r1)
        self.tmp = Path(tempfile.mkdtemp())
        self.pv, self.live = self.tmp / "pv", self.tmp / "live"
        self.pv.mkdir()
        git(self.pv, "init", "-q")
        git(self.pv, "config", "user.email", "t@t")
        git(self.pv, "config", "user.name", "t")
        self.src = bundle()
        self.commit(self.src)
        (self.live / "cards").mkdir(parents=True)
        shutil.copy(ROOT / "etf.js", self.live / "etf.js")
        for t in LIVE_CARDS:
            (self.live / "cards" / f"{t}_full_widget.html").write_text("x")

    def tearDown(self):
        shutil.rmtree(self.tmp)
        if self.saved_env is not None:
            os.environ["LEAK_CHECKER"] = self.saved_env

    def commit(self, files):
        for n, text in files.items():
            p = self.pv / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        git(self.pv, "add", "-A")
        git(self.pv, "commit", "-q", "-m", "x", "--allow-empty")

    def run_sync(self, *extra, session=P):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = S.main(["--pv", str(self.pv), "--live", str(self.live), "--session", session] + list(extra))
        self.out = buf.getvalue()
        return rc

    def text(self, n):
        return (self.live / n).read_text(encoding="utf-8")

    def data_js(self, d):
        return "// x\nwindow.ETF_DATA = " + json.dumps(d, ensure_ascii=False) + ";\n"

    # ---- 정상 ----
    def test_first_sync_links_notes_idempotent(self):
        self.assertEqual(self.run_sync(), 0, self.out)
        spy = self.text("etf-spy.html")
        self.assertIn('href="cards/AAPL_full_widget.html" class="tchip" data-card="AAPL"', spy)
        self.assertIn('href="cards/MSFT_full_widget.html" data-card="MSFT">MICROSOFT</a>', spy)
        self.assertIn('<span class="tchip no-live" data-card="ZZZ">', spy)                 # class 보존 + 회색
        self.assertIn('<span class="tchip no-live" data-card="BRK-B">', spy)
        self.assertEqual(spy.count('class="note live-note" data-base-cards="7"'), 2)        # N = 가짜 index.html 7종목
        self.assertNotIn("<!--", spy)
        self.assertIn("NVDA_full_widget.html) 코드", spy)                                 # script 안 JS 주석은 그대로
        self.assertNotIn('class="note live-note"', self.text("etf-gld.html"))              # 가격형은 안내 줄 없음
        self.assertEqual(list(S.parse_data(self.text("etf-data.js"))), order()[0])
        names = ["etf-data.js"] + [f"etf-{t.lower()}.html" for t in order()[0]]
        before = {n: self.text(n) for n in names}
        self.assertEqual(self.run_sync("--check"), 0)
        self.assertEqual(self.run_sync(), 0)
        self.assertEqual(before, {n: self.text(n) for n in names})

    def test_candidate_old_note_gets_new_count(self):
        pg = self.src["preview-only-etf-spy.html"].replace('<div id="holdings" class="section">',
                                                          '<div id="holdings" class="section"><div class="note live-note" data-base-cards="3">옛 안내</div>')
        self.commit({"preview-only-etf-spy.html": pg})
        self.assertEqual(self.run_sync(), 0, self.out)
        spy = self.text("etf-spy.html")
        self.assertNotIn('data-base-cards="3"', spy)
        self.assertEqual(spy.count('data-base-cards="7"'), 2)

    def test_card_set_change_relinks_both_ways(self):
        self.run_sync()
        (self.live / "cards" / "AAPL_full_widget.html").unlink()
        (self.live / "cards" / "ZZZ_full_widget.html").write_text("x")
        self.assertEqual(self.run_sync(), 0)
        spy = self.text("etf-spy.html")
        self.assertIn('<span class="tchip no-live" data-card="AAPL">', spy)
        self.assertIn('href="cards/ZZZ_full_widget.html" class="tchip" data-card="ZZZ"', spy)

    # ---- 입력 거부 → 기존 묶음 링크만(4) ----
    def reject_case(self, files, msg=None):
        self.assertEqual(self.run_sync(), 0, self.out)
        (self.live / "cards" / "AAPL_full_widget.html").unlink()     # 오늘 카드 집합이 바뀐 날
        data_before = self.text("etf-data.js")
        self.commit(files)
        rc = self.run_sync()
        self.assertEqual(rc, 4, self.out)
        if msg:
            self.assertIn(msg, self.out)
        self.assertEqual(self.text("etf-data.js"), data_before)       # preview 것은 안 가져옴
        self.assertNotIn('href="cards/AAPL_full_widget.html"', self.text("etf-spy.html"))   # 링크는 오늘 집합으로

    def mutate(self, fn):
        d = S.parse_data(self.src["preview-only-etf-data.js"])
        fn(d)
        return {"preview-only-etf-data.js": self.data_js(d)}

    def test_reject_missing_key(self):
        self.reject_case(self.mutate(lambda d: d.pop("TLT")), "TLT 칸 없음")

    def test_reject_truncated_page(self):
        self.reject_case({"preview-only-etf-qqq.html": self.src["preview-only-etf-qqq.html"][:300]}, "잘림")

    def test_reject_price_bundle_mismatch(self):
        cj = json.loads(self.src["v2/etf/GLD_card.json"])
        cj["close"] += 1
        self.reject_case({"v2/etf/GLD_card.json": json.dumps(cj)}, "종가")

    def test_reject_bad_card_json_types(self):
        for bad in ("[]", '{"status": "ok", "S": 20261020, "builtFor": "2026-10-20", "close": 1, "chg": 0}',
                    '{"status": "ok", "S": "2026-10-20", "builtFor": "2026-10-20", "close": "1", "chg": 0}'):
            with self.subTest(bad=bad):
                self.tearDown()
                self.setUp()
                self.reject_case({"v2/etf/IWM_card.json": bad}, "card JSON 형식 오류")

    def test_reject_verdict_bundle_mismatch(self):
        self.reject_case(self.mutate(lambda d: d["SPY"].update(nbar=-1.5)), "data-etf")

    def test_reject_future_and_bad_dates(self):
        self.reject_case(self.mutate(lambda d: d["DIA"].update(builtFor="2099-01-01")), "보다 뒤")
        self.tearDown()
        self.setUp()
        self.reject_case(self.mutate(lambda d: d["IWM"].update(builtFor="2026-02-30")), "IWM 칸 형식 오류")

    def test_reject_preview_marker(self):
        self.reject_case({"preview-only-etf-dia.html": self.src["preview-only-etf-dia.html"].replace("</body>", '<div class="range-bar"></div></body>')},
                         "preview 전용 표식")

    def test_reject_unsupported_link_spelling(self):
        pg = self.src["preview-only-etf-qqq.html"].replace('<a href="MSFT_full_widget.html">', "<a href='MSFT_full_widget.html'>")
        self.reject_case({"preview-only-etf-qqq.html": pg}, "가리키지 않음")

    def test_reject_regression(self):
        """라이브가 더 새 세션이면(역행) 후보 거부 → 기존 묶음 링크만(4), 데이터 그대로."""
        self.run_sync()
        newer = "2026-10-21"
        d = S.parse_data(self.text("etf-data.js"))
        d["SPY"].update(builtFor=newer, S=newer)
        (self.live / "etf-data.js").write_text(self.data_js(d))
        spy = self.text("etf-spy.html")
        m = re.search(r'id="verdict" class="section" data-etf="([^"]*)"', spy)
        ve = json.loads(html.unescape(m.group(1)))
        ve.update(builtFor=newer, S=newer)
        spy = spy[:m.start(1)] + html.escape(json.dumps(ve, ensure_ascii=False), quote=True) + spy[m.end(1):]
        (self.live / "etf-spy.html").write_text(spy)
        before = self.text("etf-data.js")
        self.assertEqual(self.run_sync(session=newer), 4, self.out)
        self.assertIn("역행", self.out)
        self.assertEqual(self.text("etf-data.js"), before)

    def test_reject_huge_integer(self):
        self.reject_case(self.mutate(lambda d: d["SPY"].update(nbar=10 ** 400)), "SPY 칸 형식 오류")

    def test_reject_double_href(self):
        pg = self.src["preview-only-etf-qqq.html"].replace('<a href="MSFT_full_widget.html">', '<A href="index.html" href="MSFT_full_widget.html">')
        self.reject_case({"preview-only-etf-qqq.html": pg}, "가리키지 않음")

    def test_reject_nan_and_dup_keys(self):
        with self.assertRaises(S.Reject):
            S.parse_data('// x\nwindow.ETF_DATA = {"SPY": {"nbar": NaN}};')
        with self.assertRaises(S.Reject):
            S.parse_data('// x\nwindow.ETF_DATA = {"SPY": 1, "SPY": 2};')

    # ---- 5: 카드 승격도 멈춤 ----
    def test_no_existing_bundle_is_fatal(self):
        self.commit(self.mutate(lambda d: d.pop("GLD")))
        self.assertEqual(self.run_sync(), 5)
        self.assertFalse((self.live / "etf-data.js").exists())

    def test_existing_future_bundle_is_fatal(self):
        self.run_sync()
        self.commit(self.mutate(lambda d: d.pop("GLD")))
        self.assertEqual(self.run_sync(session=Q), 5, self.out)   # 기존 묶음 builtFor P가 승격 세션 Q보다 뒤

    def test_old_checker_is_fatal(self):
        self.commit({"pipeline/site_ui/check_live_leak.py": 'NEEDLES = ["preview-only", "ETF_DATA"]\n'})
        self.assertEqual(self.run_sync(), 5)

    def test_existing_page_price_mismatch_is_fatal(self):
        self.run_sync()
        pg = self.text("etf-tlt.html").replace("100.25</div>", "1.23</div>")
        self.assertIn("1.23</div>", pg)
        (self.live / "etf-tlt.html").write_text(pg)
        self.commit(self.mutate(lambda d: d.pop("SPY")))
        self.assertEqual(self.run_sync(), 5)

    # ---- 형식·쓰기 ----
    def test_order_format(self):
        js = (ROOT / "etf.js").read_text(encoding="utf-8")
        mixed = "var ORDER = ['SPY', \"QQQ\", 'DIA', 'IWM', 'TLT', 'GLD'];"   # QQQ만 큰따옴표 — 조용히 빠지면 안 된다
        for bad in (re.sub(r"var ORDER = \[[^\]]*\];", lambda m: mixed, js), "var nothing;"):
            (self.live / "etf.js").write_text(bad)
            self.assertEqual(self.run_sync(), 2)

    def test_write_rollback_and_tmp_cleanup(self):
        self.run_sync()
        names = ["etf-data.js", "etf-spy.html", "etf-qqq.html"]
        before = {n: (self.live / n).read_bytes() for n in names}
        real, calls = os.replace, []

        def flaky(a, b):
            calls.append(b)
            if len(calls) == 3:
                raise OSError("disk")
            return real(a, b)
        S.os.replace = flaky
        try:
            with self.assertRaises(OSError):
                S.write_bundle(self.live, {"etf-data.js": "a", "etf-spy.html": "b", "etf-qqq.html": "c", "etf-new.html": "d"})
        finally:
            S.os.replace = real
        self.assertEqual(before, {n: (self.live / n).read_bytes() for n in names})
        self.assertFalse((self.live / "etf-new.html").exists())
        self.assertFalse(list(self.live.glob("*.tmp")))

    def test_link_edge_cases(self):
        out = S.relink('<a class="tchip" href="BRK-B_full_widget.html"><i></i>BRK-B</a><a href="index.html">홈</a>'
                       '<span class="tchip no-live" data-card="A.B">A.B</span>', {"BRK-B", "A.B"})
        self.assertIn('<a href="cards/BRK-B_full_widget.html" class="tchip" data-card="BRK-B"><i></i>BRK-B</a>', out)
        self.assertIn('<a href="cards/A.B_full_widget.html" class="tchip" data-card="A.B">A.B</a>', out)
        self.assertIn('<a href="index.html">홈</a>', out)
        with self.assertRaises(S.Reject):
            S.relink('<a href="cards/X_full_widget.html" data-card="Y">X</a>', {"X"})
        with self.assertRaises(S.Reject):
            S.relink("<a class='c' href=\"X_full_widget.html\">X</a>", {"X"})

    @unittest.skipUnless(shutil.which("node"), "node 없음")
    def test_js_python_validity_agree(self):
        """홈 JS valid()·validPrice()와 파이썬 판정이 같은 사례에서 같다."""
        d = S.parse_data(self.src["preview-only-etf-data.js"])
        o, price = order()
        cases = []
        for t in o:
            cases.append((t, d[t]))
            cases.append((t, dict(d[t], status="weird")))
        cases += [("GLD", dict(d["GLD"], check="day")), ("SPY", dict(d["SPY"], coverage=0.5)), ("TLT", dict(d["TLT"], navDate="2026-10-01")),
                  ("IWM", {k: v for k, v in d["IWM"].items() if k not in ("check", "prevSession")})]
        js = (ROOT / "etf.js").read_text(encoding="utf-8").replace(
            "if (document.readyState === 'loading')", "window.__t={valid:valid,validPrice:validPrice}; if (document.readyState === 'loading')")
        probe = ("global.window={StockData:{meta:{}}};global.document={readyState:'loading',addEventListener(){}};eval(require('fs').readFileSync(0,'utf8'));"
                 "const C=%s;const P=%s;console.log(JSON.stringify(C.map(([t,x])=>P[t]?window.__t.validPrice(t,x):window.__t.valid(x))))") % (
            json.dumps(cases, ensure_ascii=False), json.dumps(price))
        r = subprocess.run(["node", "-e", probe], input=js, capture_output=True, text=True)
        self.assertEqual(json.loads(r.stdout), [S.valid_price(t, x, price[t]) if t in price else S.valid_verdict(x) for t, x in cases], r.stderr)


@unittest.skipUnless(os.environ.get("ETF_TEST_PV"), "실제 preview 저장본 시험은 ETF_TEST_PV를 줄 때만")
class RealPreviewTest(unittest.TestCase):
    def test_real_preview_head_is_accepted(self):
        pv = Path(os.environ["ETF_TEST_PV"])
        tmp = Path(tempfile.mkdtemp())
        saved = os.environ.pop("LEAK_CHECKER", None)
        try:
            live = tmp / "live"
            (live / "cards").mkdir(parents=True)
            shutil.copy(ROOT / "etf.js", live / "etf.js")
            for p in (ROOT / "cards").glob("*_full_widget.html"):
                (live / "cards" / p.name).write_text("x")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = S.main(["--pv", str(pv), "--live", str(live), "--rev", os.environ.get("ETF_TEST_REV", "HEAD"),
                             "--session", json.loads(subprocess.run(["git", "-C", str(pv), "show", os.environ.get("ETF_TEST_REV", "HEAD") + ":v2/daily_status.json"],
                                                                    capture_output=True, text=True).stdout or "{}").get("session", "9999-12-31")]
                            + (["--leak-checker", os.environ["ETF_TEST_CHECKER"]] if os.environ.get("ETF_TEST_CHECKER") else []))
            self.assertEqual(rc, 0, buf.getvalue())
        finally:
            shutil.rmtree(tmp)
            if saved is not None:
                os.environ["LEAK_CHECKER"] = saved


class BuildStaticEtfTest(unittest.TestCase):
    def test_dist_drops_unlisted_etf_pages(self):
        sys.path.insert(0, str(ROOT / "tooling"))
        import build_static
        extra = ROOT / "dist" / "etf-zzz.html"
        extra.parent.mkdir(exist_ok=True)
        extra.write_text("old")
        try:
            build_static.build()
            self.assertFalse(extra.exists())
            for n in build_static.etf_files():
                self.assertTrue((ROOT / "dist" / n).exists(), n)
        finally:
            extra.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
