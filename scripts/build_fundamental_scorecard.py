#!/usr/bin/env python3
"""Render every scored card's 재무 기본점수 block in #valuation from its score file.

Why this exists. The block was hand-written, so only 11 of the 50 scored cards ever
got one - and 8 of those 11 had gone stale, because the valuation axis is recomputed
whenever the valuation signal is refreshed while the card's HTML is not. TSM's card
showed 73.8 against a real 88.7, MU's prose said "PER 2단계" when PER had moved to 5.
The homepage's 매력도별 tab reads the score file directly, so a reader comparing the
two saw one number on the list and a different one on the card.

So the block is generated here, from `{TICKER}_fundamental_score.json` plus the
valuation signal and the config's own labels and units. Every figure on it is a value
the scorer stored; nothing is written by hand and nothing needs updating by hand
again. Run it after any scoring run.

Placement: immediately before the 종합 밸류에이션 card, which is where all 11
hand-written blocks sat and which appears exactly once on all 50 scored cards.

Usage:
  python3 scripts/build_fundamental_scorecard.py [--cards-dir DIR] [--tickers A,B] [--check]
    --check   write nothing; exit 1 if any card's block is missing or out of date
"""
import argparse
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CARDS = Path.home() / "Workspace/stock-widgets-preview"
SCORES = HERE / "fundamental_scores"
SIGNALS = HERE / "valuation_signals.json"
CONFIG = HERE / "fundamental_score_config_v1.json"

# extract_tiers_scores.py carries the same alias; a card ticker is not always the filename
SCORE_FILE = {"BRKB": "BRK_B"}

ANCHOR = re.compile(r'([ \t]*)<div class="card">\s*<div class="card-title">종합 밸류에이션</div>')
BLOCK = re.compile(r'[ \t]*<div class="scorecard">(?:(?!</div>\s*\n\s*<div class="card">).)*?재무 기본점수.*?\n\s*</div>\n',
                   re.S)

GRADE_CLASS = {"우수": "grade-strong", "양호": "grade-positive", "보통": "grade-mixed", "미흡": "grade-weak"}
AXIS_MAX = {"valuation": 33, "health": 33, "growthProfit": 34}
STAGE_WORD = {1: "매우낮음", 2: "낮음", 3: "적정", 4: "높음", 5: "매우높음"}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def num(v, unit):
    """A stored ratio, printed the way the config says it is measured."""
    if v is None:
        return "—"
    if unit == "%":
        return f"{v:,.1f}%"
    if unit in ("배", "x"):
        return f"{v:,.2f}배"
    return f"{v:,.2f}"


def find_block(html):
    """The existing scorecard, if this card has one. Returns (start, end) or None.

    The #tech tab uses the same .scorecard class, so a match only counts when the
    block actually carries 재무 기본점수 - matching on the class alone would rewrite
    the technical scorecard instead.
    """
    for m in re.finditer(r'[ \t]*<div class="scorecard">', html):
        i = m.start()
        depth, j = 0, i
        while True:
            d = re.compile(r"</?div\b").search(html, j)
            if not d:
                return None
            depth += 1 if d.group(0) == "<div" else -1
            j = d.end()
            if depth == 0:
                break
        end = html.find("\n", j)
        end = len(html) if end < 0 else end + 1
        if "재무 기본점수" in html[i:j]:
            return i, end
    return None


def tech_score(html, own):
    """The card's technical score, for the "기술 80 · 평균 83.2" line the block carries.

    #tech's scorecard uses the same markup and sits earlier in the document, but taking
    the first match blindly would read this block's own score back on a rewrite, so the
    span belonging to the fundamental block is skipped explicitly.
    """
    skip = range(*own) if own else range(0, 0)
    for m in re.finditer(r'class="scorecard-score"><span class="num">([\d.]+)</span>', html):
        if m.start() not in skip:
            return float(m.group(1))
    return None


def valuation_desc(score, sig, asof):
    v = score["valuation"]
    stage = v.get("combinedStage")
    bits = []
    if sig:
        for key, label in (("per", "PER"), ("pbr", "PBR")):
            part = sig.get(key) or {}
            if part.get("stage") is not None:
                bits.append(f"{label} {part['current']:,.2f}x {part['stage']}단계")
        tp = sig.get("targetPrice") or {}
        if tp.get("stage") is not None:
            who = f"애널리스트 {tp['numAnalysts']}명" if tp.get("numAnalysts") else "애널리스트"
            bits.append(f"목표주가 {tp['stage']}단계({who} 컨센서스 {tp['upsidePct']:+,.1f}%)")
    lead = "·".join(bits) if bits else "자체 5년 배수 이력과 목표주가"
    tail = f"종합 {stage:,.1f}/5단계(낮을수록 저평가)" if stage is not None else "종합 단계 산출 불가"
    label = (sig or {}).get("combinedLabel")
    out = f"{esc(lead)} — {esc(tail)}"
    if label:
        out += f' <span style="color:var(--gold);font-weight:700;">{esc(label)}</span>'
    cov = v.get("historicalMultipleCoverage")
    if cov is not None and cov < 2:
        out += f' <span style="color:var(--text3);">(자체 배수 이력 {cov}개만 확보 — 목표주가 비중이 커진다)</span>'
    if asof:
        out += f' <span style="color:var(--text3);">({esc(asof)} 모델 스냅샷 기준)</span>'
    return out


def ratio_desc(block, spec_ratios, used_key, top_label):
    """List each stored ratio with its own label and unit, then the raw points behind the axis.

    The raw total is what the axis score is scaled from, so it explains the bar above it;
    counting how many hit the top bucket reads as "0개" for most companies and says nothing.
    """
    parts, raw = [], 0
    for key, spec in spec_ratios.items():
        rec = block.get(key)
        if not isinstance(rec, dict) or "points" not in rec:
            continue
        parts.append(f"{spec.get('label', key)} {num(rec.get('value'), spec.get('unit', ''))}")
        raw += rec["points"]
    n = block.get(used_key) or len(parts)
    body = "·".join(esc(p) for p in parts) or "지표 없음"
    return f"{body} — {n}개 {top_label} 합계 {raw}/{n * 5}점"


def render_block(ticker, score, sig, config, tech, indent):
    total = score["totalScore"]
    grade = score.get("grade") or "—"
    cls = GRADE_CLASS.get(grade, "grade-mixed")
    # update_cards.py re-derives this line every day and refuses a card whose X does not
    # equal (fundamental + N) / 2 at ROUND_HALF_UP - float formatting disagreed with it on
    # seven cards, so the same Decimal arithmetic is used here.
    if tech is None:
        inline = "기술점수 없음"
    else:
        avg = ((Decimal(str(total)) + int(tech)) / 2).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        inline = f"기술 {int(tech)} · 평균 {avg}"
    ver = config.get("version", "1.0.1")
    frozen = config.get("formula_frozen_date", "2026-08-25")

    axes = [
        ("밸류에이션", score["valuation"], valuation_desc(score, sig, score.get("valuationAsOf"))),
        ("재무건전성", score["health"],
         ratio_desc(score["health"], config["health"]["ratios"], "ratiosUsed", "비율")),
        ("성장·수익성", score["growthProfit"],
         ratio_desc(score["growthProfit"], config["growth_profit"]["metrics"], "metricsUsed", "지표")),
    ]
    boxes = []
    for name, block, desc in axes:
        key = {"밸류에이션": "valuation", "재무건전성": "health", "성장·수익성": "growthProfit"}[name]
        pts, mx = block["axisPoints"], AXIS_MAX[key]
        boxes.append(
            f'{indent}    <div class="subscore-box">\n'
            f'{indent}      <div class="subscore-label"><span>{name}</span>'
            f'<span class="subscore-max">{pts:g}/{mx}</span></div>\n'
            f'{indent}      <div class="subscore-val">{pts:g}</div>\n'
            f'{indent}      <div class="subscore-bar">'
            f'<div class="subscore-bar-fill" style="width:{pts / mx * 100:.1f}%;"></div></div>\n'
            f'{indent}      <div class="subscore-desc">{desc}</div>\n'
            f'{indent}    </div>')

    flags = list(score.get("qualityFlags") or [])
    if score.get("coverageStatus") == "partial":
        flags.append("coverage partial")
    if flags:
        note = (f'{indent}  <div class="scorecard-noflags">⚠️ 데이터 상태 · '
                f'{esc(" · ".join(flags))} — 같은 등급대의 다른 종목과 그대로 비교하기 어렵다</div>')
    else:
        note = (f'{indent}  <div class="scorecard-noflags">ℹ️ 데이터 상태 · '
                f'주요 재무지표가 기준 커버리지를 충족합니다</div>')

    # financialsAgeMonths counts from the fiscal period end, not from the filing date, so
    # "공시 후" was wrong on every card - MRVL's FY ends 2026-01-31 but its 10-K was filed
    # 2026-03-11, which is 6.0 months to the snapshot against the 7.3 this field holds.
    age = score.get("financialsAgeMonths")
    age_txt = f" · 기준일로부터 {age:,.1f}개월 경과" if age is not None else ""
    return (
        f'{indent}<div class="scorecard">\n'
        f'{indent}  <div class="scorecard-top">\n'
        f'{indent}    <div>\n'
        f'{indent}      <div class="scorecard-score"><span class="num">{total:g}</span>'
        f'<span class="denom">/100</span></div>\n'
        f'{indent}    </div>\n'
        f'{indent}    <div class="scorecard-verdict">\n'
        f'{indent}      <div><span class="scorecard-grade {cls}">재무 기본점수 · {esc(grade)} 구간</span></div>\n'
        f'{indent}      <div class="scorecard-noOpp-inline">{inline}</div>\n'
        f'{indent}    </div>\n'
        f'{indent}  </div>\n'
        f'{indent}  <div class="scorecard-bar">'
        f'<div class="scorecard-bar-fill" style="width:{total:g}%;"></div></div>\n'
        f'{indent}  <div class="scorecard-subtitle">3축(밸류에이션·재무건전성·성장·수익성) 종합, '
        f'100점 만점 환산 · 모델 v{esc(ver)} 산식 동결 {esc(frozen)}</div>\n\n'
        f'{indent}  <div class="scorecard-subscores">\n' + "\n".join(boxes) + "\n"
        f'{indent}  </div>\n\n'
        f'{note}\n\n'
        f'{indent}  <div class="scorecard-footer">\n'
        f'{indent}    <span>재무 데이터 기준일 {esc(score.get("financialsAsOf", "—"))}{age_txt}</span>\n'
        f'{indent}    <span class="scorecard-disclaimer">서술적 스냅샷 지표 - 지금 저평가·재무건전성·'
        f'성장성이 어느 수준인지 요약할 뿐이며, 향후 수익률과의 상관관계는 검증하지 않았습니다. '
        f'기술점수와의 단순평균도 순위·매수판단용이 아닙니다.</span>\n'
        f'{indent}  </div>\n'
        f'{indent}</div>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", default=str(DEFAULT_CARDS))
    ap.add_argument("--tickers", default=None)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cards = Path(args.cards_dir)
    data = json.loads((cards / "site_data" / "stocks.json").read_text(encoding="utf-8"))
    signals = json.loads(SIGNALS.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    wanted = {t.strip().upper() for t in args.tickers.split(",")} if args.tickers else None

    written, same, added, skipped, stale = [], [], [], [], []
    for entry in data["tickers"]:
        tk = entry["ticker"]
        if wanted and tk not in wanted:
            continue
        if entry["score"]["status"] != "available":
            skipped.append(tk)          # banks and unsupported tickers get no block, by config
            continue
        path = cards / entry["href"]
        html = path.read_text(encoding="utf-8")
        score_path = SCORES / f"{SCORE_FILE.get(tk, tk)}_fundamental_score.json"
        if not score_path.exists():
            # stocks.json says this card has a score, so the file belongs in fundamental_scores/.
            # A build agent that writes it beside the other scripts leaves it invisible here.
            sys.exit(f"{tk}: stocks.json reports a score but {score_path} is missing "
                     f"- move the build's {tk}_fundamental_score.json into {SCORES.name}/")
        score = json.loads(score_path
                           .read_text(encoding="utf-8"))
        if "valuation" not in score:
            skipped.append(tk)
            continue

        found = find_block(html)
        anchor = ANCHOR.search(html)
        if not anchor:
            sys.exit(f"{tk}: no 종합 밸류에이션 card to place the block before")
        indent = anchor.group(1)
        block = render_block(tk, score, signals.get(tk), config, tech_score(html, found), indent)

        if found:
            i, j = found
            new = html[:i] + block + html[j:]
        else:
            new = html[:anchor.start()] + block + "\n" + html[anchor.start():]
        if new == html:
            same.append(tk)
            continue
        (written if found else added).append(tk)
        if args.check:
            stale.append(tk)
        else:
            path.write_text(new, encoding="utf-8")

    if args.check:
        out = sorted(set(stale))
        print(f"out of date or missing: {len(out)}" + (f" - {' '.join(out)}" if out else ""))
        sys.exit(1 if out else 0)
    print(f"added {len(added)}: {' '.join(added) or '-'}")
    print(f"rewritten {len(written)}: {' '.join(written) or '-'}")
    print(f"unchanged {len(same)}")
    print(f"no score, left without a block {len(skipped)}: {' '.join(skipped) or '-'}")


if __name__ == "__main__":
    main()
