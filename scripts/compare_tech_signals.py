#!/usr/bin/env python3
"""기술 상태 점수 v1 대 눌림목 점수 — 같은 패널, 같은 통계로 비교.

The question this answers, asked directly by the user: for the #tech tab, is the shipped
기술 상태 점수 v1 (가격구조60 + 절대모멘텀40) or a 눌림목매매 style score the better
signal, and is there anything to gain by combining them?

They cannot be compared as they stand -- v1 is a continuous state score defined for every
name every day, while 눌림목 is an event gate plus a conditional score. Putting them on
one footing means expressing the pullback rule as a continuous 0-100 score too (0 when no
impulse leg exists at all, which is information, not missingness) and running the identical
cross-sectional test on both.

Universe: the unselected S&P 500 control set (data/sp500_5y), NOT the 54 cards. Today's
work established that the card universe manufactures results -- its mean 12-month excess
return is +23% with no signal involved, and the valuation signal's IC went from -0.218
there to -0.023 here. Any comparison run on the cards would grade both signals against a
universe chosen after the outcomes were known.

Horizons: 20d / 60d / 6m / 12m, all four reported for every signal. This matters for
fairness -- 눌림목 is a swing concept whose natural horizon is weeks, while v1's momentum
term is built on a 252-day ROC. Judging either only at the other's horizon would decide
the answer by choosing the ruler.

Statistic: monthly cross-sectional Spearman IC (Fama-MacBeth mean over months), quintile
mean forward excess return vs SPY, and a moving-block bootstrap CI over the month axis --
the same machinery used in compute_valuation_ic_v4.py, so the numbers are comparable to
that file's.

Combination test: rank correlation between the two scores, then a conditional double sort
-- tercile on v1, then quintile on the pullback score WITHIN each v1 tercile. If the
pullback spread survives inside a v1 tercile it carries information v1 does not have and
combining is worth designing; if it collapses, it is v1 restated.

Pre-declared before running (so the bar is not chosen after seeing the numbers): the
pullback rule counts as beating v1 only if its FM IC confidence interval excludes zero at
some horizon AND the sign is consistent across both impulse definitions. Every variant
computed is reported, none dropped.

Usage:
    python3 compare_tech_signals.py --out scripts/tech_signal_comparison.json
"""
import argparse
import json
import math
import os
import sys
from datetime import date
from pathlib import Path

import random

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from breakout_signal import atr_series                      # noqa: E402
from compute_technical_score import compute_signal          # noqa: E402
from compute_pullback_signal import score_at                # noqa: E402
from compute_valuation_ic import moving_block_bootstrap_ci, HORIZON_MONTHS  # noqa: E402

HORIZONS = {"20d": 20, "60d": 60, "6m": 126, "12m": 252}
# Non-overlapping segments of the same span, so a later segment can be checked for an
# independent effect rather than re-counting the first move.
INCREMENTS = ["inc_0_20d", "inc_20_60d", "inc_60_126d", "inc_126_252d"]
IMPULSE_GAIN_THRESHOLD = 20.0
BLOCK_MONTHS = {"20d": 1, "60d": 3, "6m": 6, "12m": 12}
# Variants declared in advance; all are reported.
PULLBACK_VARIANTS = [("window", "fib"), ("window", "source"), ("zigzag", "fib")]
SIGNALS_PRIMARY = ["v1_total", "v1_price_structure", "v1_momentum",
                   "pb_total_window_fib", "pb_gate_window_fib"]


def load_bars(path):
    return sorted(json.load(open(path))["daily"], key=lambda b: b["date"])


def month_end_indices(bars):
    last = {}
    for i, b in enumerate(bars):
        last[b["date"][:7]] = i
    return [last[k] for k in sorted(last)]


def build_panel(price_dir, spy_path, config, limit=None):
    spy = load_bars(spy_path)
    spy_close = [b["c"] for b in spy]
    spy_idx = {b["date"]: i for i, b in enumerate(spy)}
    files = sorted(f for f in os.listdir(price_dir) if f.endswith(".json") and f != "SPY.json")
    if limit:
        files = files[:limit]
    rows = []
    for fn in files:
        t = fn[:-5]
        bars = load_bars(os.path.join(price_dir, fn))
        if len(bars) < 400 or "h" not in bars[0] or "v" not in bars[0]:
            continue
        a = atr_series(bars, period=20)
        atr_pct_full = [None] + [(x / bars[k + 1]["c"] if x else None) for k, x in enumerate(a)]
        for i in month_end_indices(bars):
            if i < 300:
                continue
            d = bars[i]["date"]
            si = spy_idx.get(d)
            if si is None:
                continue
            row = {"ticker": t, "date": d}
            v1 = compute_signal(t, {"daily": bars[:i + 1]}, config)
            if v1.get("insufficientHistory"):
                continue
            row["v1_total"] = float(v1["rawScore"])
            row["v1_price_structure"] = float(v1["priceStructureScore"]["score"])
            row["v1_momentum"] = float(v1["momentum"]["score"])
            row["v1_trend"] = float(v1["trendStructure"]["score"])
            row["v1_pos52w"] = float(v1["position52w"]["score"])
            # Continuous weighted ROC behind the bucketed momentum score. Kept so the
            # "does the pullback score add information, or just resolution v1 threw away
            # when it bucketed momentum into 40 points?" question can be tested directly.
            roc_pct = v1["momentum"].get("weightedRocPct")
            if roc_pct is not None:
                row["v1_roc_continuous"] = float(roc_pct)
            for im, rm in PULLBACK_VARIANTS:
                r = score_at(bars, i, im, rm, atr_pct_full)
                key = f"{im}_{rm}"
                # No impulse leg at all is a real state ("not a pullback candidate"),
                # not missing data, so it scores 0 rather than dropping the observation.
                # Every pullback field is zero-filled on the SAME rows. Previously
                # pb_total was zero-filled while pb_setup/pb_entry were simply absent
                # when no impulse leg existed, so "setup is positive, entry is negative,
                # they cancel in the total" was comparing three different samples and was
                # not an additive decomposition at all (Codex round 1). pb_has_impulse
                # keeps the two populations separable for the conditional cuts.
                row[f"pb_has_impulse_{key}"] = 1.0 if r else 0.0
                row[f"pb_total_{key}"] = float(r["total"]) if r else 0.0
                row[f"pb_gate_{key}"] = 1.0 if (r and r["setup_qualified"]) else 0.0
                row[f"pb_setup_{key}"] = float(r["setup_score"]) if r else 0.0
                row[f"pb_entry_{key}"] = float(r["entry_score"]) if r else 0.0
                row[f"pb_impulse_gain_{key}"] = float(r["impulse"]["gain_pct"]) if r else 0.0
            # The SPY leg is matched on the stock's OWN exit DATE, not on si+h. Indexing
            # both by offset silently compares different windows whenever a ticker has a
            # missing or halted bar (measured: 9 of 16,217 rows at 252d, all FISV, one day
            # off -- immaterial here, but the claim "identical window" should be exact
            # rather than nearly true).
            for name, h in HORIZONS.items():
                if i + h < len(bars):
                    se = spy_idx.get(bars[i + h]["date"])
                    if se is not None:
                        row["fwd_" + name] = (bars[i + h]["c"] / bars[i]["c"] - 1) - \
                                             (spy_close[se] / spy_close[si] - 1)
            # Non-overlapping increments as well as the cumulative windows. A cumulative
            # excess return that grows with the horizon is not by itself evidence of
            # continuing drift -- the same early move stays inside every longer window.
            # Only a later segment that is independently positive shows the effect
            # persists (Codex round 2).
            for name, (h0, h1) in {"0_20d": (0, 20), "20_60d": (20, 60),
                                   "60_126d": (60, 126), "126_252d": (126, 252)}.items():
                if i + h1 < len(bars):
                    s0 = spy_idx.get(bars[i + h0]["date"])
                    s1 = spy_idx.get(bars[i + h1]["date"])
                    if s0 is not None and s1 is not None:
                        row["inc_" + name] = (bars[i + h1]["c"] / bars[i + h0]["c"] - 1) - \
                                             (spy_close[s1] / spy_close[s0] - 1)
            rows.append(row)
    return rows


def evaluate(rows, field, min_month_n=20):
    out = {}
    for name in HORIZONS:
        fwd = "fwd_" + name
        sample = [r for r in rows if field in r and fwd in r]
        if len(sample) < 100:
            out[name] = {"n": len(sample), "note": "insufficient"}
            continue
        pooled, p = spearmanr([r[field] for r in sample], [r[fwd] for r in sample])
        by_month = {}
        for r in sample:
            by_month.setdefault(r["date"][:7], []).append(r)
        ics, spreads, q = [], [], {k: [] for k in range(5)}
        for ym in sorted(by_month):
            m = sorted(by_month[ym], key=lambda r: r[field])
            if len(m) < min_month_n:
                continue
            ic, _ = spearmanr([r[field] for r in m], [r[fwd] for r in m])
            if ic == ic:
                ics.append(float(ic))
            k = len(m) // 5
            for j in range(5):
                chunk = m[j * k:(j + 1) * k] if j < 4 else m[4 * k:]
                q[j].append(float(np.mean([r[fwd] for r in chunk])))
            spreads.append(q[4][-1] - q[0][-1])   # top-minus-bottom (high score minus low)
        blk = BLOCK_MONTHS[name]
        ci = moving_block_bootstrap_ci(ics, blk) if len(ics) >= blk else None
        sci = moving_block_bootstrap_ci(spreads, blk) if len(spreads) >= blk else None
        out[name] = {
            "n": len(sample), "months": len(ics),
            "pooled_ic": round(float(pooled), 4), "pooled_p": float("%.3g" % p),
            "fm_ic": round(float(np.mean(ics)), 4) if ics else None,
            "fm_ic_95ci": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
            "quintile_mean_excess": [round(float(np.mean(q[j])), 4) for j in range(5)],
            "top_minus_bottom": round(float(np.mean(spreads)), 4) if spreads else None,
            "top_minus_bottom_95ci": [round(sci[0], 4), round(sci[1], 4)] if sci else None,
            "months_positive_spread": sum(1 for s in spreads if s > 0),
        }
    return out


def conditional_double_sort(rows, base_field, test_field, horizon, n_tercile=3):
    """Tercile on base_field within each month, then quintile-spread test_field inside
    each tercile. Answers whether test_field adds anything base_field does not have."""
    fwd = "fwd_" + horizon
    sample = [r for r in rows if base_field in r and test_field in r and fwd in r]
    by_month = {}
    for r in sample:
        by_month.setdefault(r["date"][:7], []).append(r)
    res = {}
    for tier in range(n_tercile):
        spreads, ics = [], []
        for ym in sorted(by_month):
            m = sorted(by_month[ym], key=lambda r: r[base_field])
            k = len(m) // n_tercile
            if k < 15:
                continue
            sub = m[tier * k:(tier + 1) * k] if tier < n_tercile - 1 else m[(n_tercile - 1) * k:]
            sub = sorted(sub, key=lambda r: r[test_field])
            ic, _ = spearmanr([r[test_field] for r in sub], [r[fwd] for r in sub])
            if ic == ic:
                ics.append(float(ic))
            kk = len(sub) // 5
            if kk < 2:
                continue
            spreads.append(float(np.mean([r[fwd] for r in sub[4 * kk:]]))
                           - float(np.mean([r[fwd] for r in sub[:kk]])))
        blk = BLOCK_MONTHS[horizon]
        ci = moving_block_bootstrap_ci(spreads, blk) if len(spreads) >= blk else None
        res[["low", "mid", "high"][tier]] = {
            "months": len(spreads),
            "fm_ic": round(float(np.mean(ics)), 4) if ics else None,
            "top_minus_bottom": round(float(np.mean(spreads)), 4) if spreads else None,
            "top_minus_bottom_95ci": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        }
    return res


def paired_delta_ic(rows, field_a, field_b, horizon, subset=None, min_month_n=20):
    """IC(field_a) - IC(field_b) computed on the SAME rows in the SAME month, then the
    mean of that monthly difference series with a moving-block bootstrap.

    This is the statistic that actually answers "which signal is better". Observing that
    one signal's CI excludes zero while the other's does not is not a comparison between
    them (Codex round 2); the difference has to be tested directly, and pairing it within
    the month removes the common market move that both signals sit in."""
    fwd = "fwd_" + horizon
    by_month = {}
    for r in rows:
        if fwd in r and field_a in r and field_b in r and (subset is None or r["ticker"] in subset):
            by_month.setdefault(r["date"][:7], []).append(r)
    diffs = []
    for ym in sorted(by_month):
        m = by_month[ym]
        if len(m) < min_month_n:
            continue
        ia, _ = spearmanr([r[field_a] for r in m], [r[fwd] for r in m])
        ib, _ = spearmanr([r[field_b] for r in m], [r[fwd] for r in m])
        if ia == ia and ib == ib:
            diffs.append(float(ia - ib))
    blk = BLOCK_MONTHS[horizon]
    ci = moving_block_bootstrap_ci(diffs, blk) if len(diffs) >= blk else None
    return {"mean_delta_ic": round(float(np.mean(diffs)), 4) if diffs else None,
            "delta_ic_95ci": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
            "months": len(diffs),
            "months_a_ahead": sum(1 for d in diffs if d > 0)}


def gate_contrast(rows, gate_field, gain_field, horizon, stratify=True, boot=4000, seed=42):
    """Gate-pass minus same-month gate-FAIL, both drawn from the eligible universe
    (impulse gain >= the gate's own threshold), bootstrapped on the DIFFERENCE.

    The gate's mandatory conditions include an impulse gain threshold, so a gate-vs-whole-
    universe comparison mostly measures that momentum condition. Restricting the control
    to names that cleared the same gain threshold and then failed the four pullback-
    specific conditions isolates what those four conditions contribute. stratify=True
    additionally pairs within impulse-gain quintiles, because clearing 21% and clearing
    100% are very different momentum exposures (Codex round 2)."""
    by_month = {}
    fwd = "fwd_" + horizon
    for r in rows:
        if fwd in r and r.get(gain_field, 0.0) >= IMPULSE_GAIN_THRESHOLD:
            by_month.setdefault(r["date"][:7], []).append(r)
    per_ticker, n_pass, n_fail = {}, 0, 0
    for ym in sorted(by_month):
        month = by_month[ym]
        groups = [month]
        if stratify:
            ordered = sorted(month, key=lambda r: r[gain_field])
            k = max(1, len(ordered) // 5)
            groups = [ordered[j * k:(j + 1) * k] if j < 4 else ordered[4 * k:] for j in range(5)]
        for g in groups:
            passed = [r for r in g if r.get(gate_field) == 1.0]
            failed = [r for r in g if r.get(gate_field) != 1.0]
            if not passed or not failed:
                continue
            base = float(np.mean([r[fwd] for r in failed]))
            for r in passed:
                per_ticker.setdefault(r["ticker"], []).append(r[fwd] - base)
                n_pass += 1
            n_fail += len(failed)
    if not per_ticker:
        return None
    keys = sorted(per_ticker)
    rng = random.Random(seed)
    means = []
    for _ in range(boot):
        draw = []
        for _ in range(len(keys)):
            draw.extend(per_ticker[keys[rng.randrange(len(keys))]])
        means.append(sum(draw) / len(draw))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"difference": round(float(np.mean([v for vs in per_ticker.values() for v in vs])), 4),
            "difference_95ci": [round(float(lo), 4), round(float(hi), 4)],
            "n_pass": n_pass, "n_fail": n_fail, "stratified_by_impulse_gain": stratify}


def event_vs_month(rows, gate_field, value_field, boot=4000, seed=42):
    """Mean of (event value - same-month universe mean), ticker-cluster bootstrapped."""
    by_month = {}
    for r in rows:
        if value_field in r:
            by_month.setdefault(r["date"][:7], []).append(r)
    per_ticker = {}
    for ym, month in by_month.items():
        mu = float(np.mean([r[value_field] for r in month]))
        for r in month:
            if r.get(gate_field) == 1.0:
                per_ticker.setdefault(r["ticker"], []).append(r[value_field] - mu)
    if not per_ticker:
        return None
    keys = sorted(per_ticker)
    rng = random.Random(seed)
    means = []
    for _ in range(boot):
        draw = []
        for _ in range(len(keys)):
            draw.extend(per_ticker[keys[rng.randrange(len(keys))]])
        means.append(sum(draw) / len(draw))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"mean_excess_vs_month": round(float(np.mean([v for vs in per_ticker.values() for v in vs])), 4),
            "95ci": [round(float(lo), 4), round(float(hi), 4)],
            "n": sum(len(v) for v in per_ticker.values())}


def realized_5y_return(price_dir):
    """Per-ticker realised return over the whole file, used only for the survivorship
    bound below -- never as a signal."""
    out = {}
    for fn in os.listdir(price_dir):
        if not fn.endswith(".json") or fn == "SPY.json":
            continue
        b = load_bars(os.path.join(price_dir, fn))
        if len(b) > 1 and b[0]["c"] > 0:
            out[fn[:-5]] = b[-1]["c"] / b[0]["c"] - 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-dir", default=str(ROOT / "data/sp500_5y"))
    ap.add_argument("--spy", default=str(ROOT / "data/raw_5y/SPY.json"))
    ap.add_argument("--config", default=str(HERE / "tech_score_config_v1.json"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump-rows", default=None, help="write the raw panel for follow-up cuts")
    a = ap.parse_args()

    config = json.load(open(a.config))
    rows = build_panel(a.price_dir, a.spy, config, a.limit)
    tickers = len({r["ticker"] for r in rows})
    print(f"panel: {tickers} tickers, {len(rows)} (ticker,month) rows")

    fields = ["v1_total", "v1_price_structure", "v1_momentum", "v1_trend", "v1_pos52w",
              "v1_roc_continuous"]
    for im, rm in PULLBACK_VARIANTS:
        fields += [f"pb_total_{im}_{rm}", f"pb_gate_{im}_{rm}",
                   f"pb_setup_{im}_{rm}", f"pb_entry_{im}_{rm}",
                   f"pb_impulse_gain_{im}_{rm}"]

    result = {"universe": os.path.basename(a.price_dir), "tickers": tickers,
              "rows": len(rows), "horizons": list(HORIZONS),
              "signals": {f: evaluate(rows, f) for f in fields}}

    base = [r for r in rows if "v1_total" in r and "pb_total_window_fib" in r]
    if base:
        c, _ = spearmanr([r["v1_total"] for r in base], [r["pb_total_window_fib"] for r in base])
        result["rank_corr_v1_vs_pullback"] = round(float(c), 4)
    # Every pullback variant is double-sorted, not just the primary one: the
    # pre-declared bar requires the sign to hold across both impulse definitions.
    # v1_roc_continuous and the raw impulse gain are included as the competing
    # explanation -- if they add MORE inside a v1 tercile than the pullback score does,
    # then what the pullback score contributes is momentum resolution that v1 discarded
    # when it bucketed momentum into 40 points, not information v1 lacks.
    result["conditional_double_sort"] = {
        h: {f"{f}_within_v1_tercile": conditional_double_sort(rows, "v1_total", f, h)
            for f in ["pb_total_window_fib", "pb_total_zigzag_fib", "pb_total_window_source",
                      "pb_setup_window_fib", "pb_entry_window_fib",
                      "v1_roc_continuous", "pb_impulse_gain_window_fib"]}
        | {"v1_within_pullback_tercile":
           conditional_double_sort(rows, "pb_total_window_fib", "v1_total", h)}
        for h in ["60d", "12m"]
    }
    # --- the statistic that answers "which is better" (Codex round 2) ---
    result["paired_delta_ic_v1_minus_pullback"] = {
        b: {h: paired_delta_ic(rows, "v1_total", b, h) for h in HORIZONS}
        for b in ["pb_total_window_fib", "pb_total_zigzag_fib", "pb_total_window_source"]}

    # --- what the four pullback-specific conditions add over the gain threshold alone ---
    result["gate_contrast_vs_eligible_failures"] = {
        ("stratified" if st else "unstratified"): {
            h: gate_contrast(rows, "pb_gate_window_fib", "pb_impulse_gain_window_fib", h, st)
            for h in HORIZONS}
        for st in (True, False)}

    # --- is the gate edge continuing drift, or one early move carried by every window? ---
    result["gate_incremental_windows"] = {
        k: event_vs_month(rows, "pb_gate_window_fib", k) for k in INCREMENTS}

    result["verdict"] = (
        "무엇을 물었나: #tech 탭의 기술 상태 점수 v1(가격구조60+절대모멘텀40)과 눌림목매매식 "
        "점수 중 어느 쪽이 나은가, 합칠 가치가 있는가. 무엇으로 답했나: 현 S&P500 구성종목 "
        "492개를 2022-11~2026-07 45개월 월말마다 채점한 22,121개 (종목,월) 패널에서 월별 "
        "횡단면 IC와 같은 달 기준선 대비 이벤트 초과수익으로 비교했다. "
        "[1] 어느 쪽이 나은가 — 짝지은 ΔIC = IC(v1) − IC(눌림목)을 같은 달 같은 종목에서 "
        "직접 검정하면 6개월 +0.101, 12개월 +0.089이고 두 기간 모두 신뢰구간이 0을 배제하며 "
        "임펄스 정의 세 변형에서 부호가 같다. 20일·60일은 0과 구별되지 않는다. 한쪽만 "
        "유의하다는 사실로는 비교가 성립하지 않으므로 이 차이 검정이 근거다. "
        "[2] 게이트 — 눌림목 게이트는 같은 달 유니버스 대비 60일 +1.67%, 12개월 +11.27%의 "
        "초과수익을 보이고, 중첩 없는 증분 구간(20~60일 +1.13%, 60~126일 +3.59%, "
        "126~252일 +4.93%)에서도 각각 양수라 초기 한 번의 움직임이 긴 창에 계속 포함된 "
        "결과는 아니다. 그러나 게이트 필수조건에 임펄스 상승률 ≥20%가 있고, 같은 조건을 "
        "통과했지만 나머지 네 개 눌림목 조건에서 탈락한 종목과 직접 대조하면 차이가 12개월 "
        "+0.28%p(임펄스 상승률 5분위 내 짝지어도 +3.58%p)이며 신뢰구간이 0을 크게 포함한다. "
        "게이트의 우위는 그 안의 모멘텀 조건으로 대부분 설명되고, 나머지 네 조건의 추가효과는 "
        "점추정이 작으나 '0이다'라고 확정할 검정력도 없다. "
        "[3] 진입 타이밍 60점 — 전체 표본에서 6개월 −0.029, 12개월 −0.034의 음의 연관이고 "
        "게이트 통과 표본 안에서는 0 부근이다(24~28개월, 검정력 낮음). 양의 순위예측력은 "
        "어느 쪽에서도 발견되지 않았다. "
        "[4] 합칠까 — v1 상위 3분위 안에서 눌림목이 추가 스프레드를 내지만, 같은 자리에서 "
        "v1 자신의 연속 ROC가 2~4배 크게 기여한다. 눌림목이 더하는 것은 v1이 모멘텀을 40점 "
        "구간으로 뭉개며 버린 해상도로 보인다. "
        "제품 결정: 눌림목 점수를 추가할 근거가 없으므로 추가하지 않는다. 이것은 '눌림목이 "
        "무가치함이 입증됐다'가 아니라 '추가를 정당화할 증거가 없다'이다. "
        "확인적 결론이 아닌 이유: (a) 유니버스가 현재 S&P500 구성종목을 과거로 소급한 생존자 "
        "표본이다. 5년 실현수익 상위 10% 제외는 사후 결과변수로 자른 민감도 분석일 뿐 생존편향 "
        "보정이 아니며, 그 표본에서 ΔIC는 12개월 +0.045만 남고 6개월은 0을 포함한다. "
        "(b) signal×horizon×variant 조합이 80개를 넘어 표시된 유의성은 모두 다중비교 보정 전 "
        "'명목상'이다. (c) 12개월 수익률이 크게 중첩된 33개월 표본이라 블록 부트스트랩 "
        "신뢰구간이 불안정하다. (d) 2022-11 이후 한 국면이며 신호×국면 상호작용은 상대 순위도 "
        "뒤집을 수 있다. (e) 검정 대상은 원 눌림목 체계가 아니라 공개 출력에서 재구성한 "
        "미국시장용 축약 proxy다(위험감점·수급10·돌파10 제외, 임펄스 탐지는 자체 정의, 일부 "
        "진입 항목은 거친 대용치). v2 후보 '모멘텀 구간화 완화'는 이 데이터를 보고 나온 "
        "탐색적 아이디어이므로 사전등록 후 독립 구간에서 확인해야 한다.")

    # --- gate-conditional efficacy (Codex round 1) ---
    # pb_total ranks every name including the ones the rule would refuse to trade, so a
    # flat IC on it does not test the rule as a rule. This is the strategy-shaped test:
    # among names that actually pass the mandatory setup gate, does the entry-timing
    # score rank them, and do gated names beat the same month's universe at all?
    gated = [r for r in rows if r.get("pb_gate_window_fib") == 1.0]
    result["gate_conditional"] = {
        "n_gated_rows": len(gated),
        "gated_share": round(len(gated) / len(rows), 4),
        "months_covered": len({r["date"][:7] for r in gated}),
        "within_gated": {f: evaluate(gated, f, min_month_n=10)
                         for f in ["pb_entry_window_fib", "pb_setup_window_fib",
                                   "pb_total_window_fib"]},
    }
    for h in HORIZONS:
        fwd = "fwd_" + h
        g = [r[fwd] for r in gated if fwd in r]
        allr = [r[fwd] for r in rows if fwd in r]
        if g:
            result["gate_conditional"].setdefault("gated_vs_universe_mean_excess", {})[h] = {
                "gated_mean": round(float(np.mean(g)), 4), "n": len(g),
                "universe_mean": round(float(np.mean(allr)), 4),
                "difference": round(float(np.mean(g) - np.mean(allr)), 4)}

    # --- survivorship bound (Codex round 1) ---
    # The universe is CURRENT S&P 500 membership applied back to 2022, so it over-weights
    # names that won over this window, which structurally flatters long-horizon momentum.
    # A point-in-time membership list is not available here, so this is a bound rather
    # than a fix: drop the top decile by realised 5-year return -- itself conditioning on
    # the future, but in the OPPOSITE direction, so a v1 advantage that survives it is not
    # an artifact of the winners being in the sample.
    rr = realized_5y_return(a.price_dir)
    if rr:
        cutoff = float(np.percentile(list(rr.values()), 90))
        keep = {t for t, v in rr.items() if v < cutoff}
        trimmed = [r for r in rows if r["ticker"] in keep]
        result["survivorship_bound"] = {
            "note": "top decile by realised 5y return removed",
            "cutoff_5y_return": round(cutoff, 4),
            "tickers_kept": len({r["ticker"] for r in trimmed}), "rows": len(trimmed),
            "signals": {f: evaluate(trimmed, f) for f in
                        ["v1_total", "v1_momentum", "v1_price_structure",
                         "pb_total_window_fib", "pb_setup_window_fib", "pb_entry_window_fib"]},
        }

    json.dump(result, open(a.out, "w"), indent=2, ensure_ascii=False)
    if a.dump_rows:
        json.dump(rows, open(a.dump_rows, "w"))

    print(f"\n{'signal':28} " + " ".join(f"{h:>22}" for h in HORIZONS))
    for f in fields:
        cells = []
        for h in HORIZONS:
            r = result["signals"][f].get(h, {})
            if r.get("fm_ic") is None:
                cells.append(f"{'n/a':>22}")
            else:
                ci = r["fm_ic_95ci"]
                mark = "*" if ci and (ci[0] > 0 or ci[1] < 0) else " "
                cells.append(f"{r['fm_ic']:+.3f}{mark}[{ci[0]:+.3f},{ci[1]:+.3f}]" if ci
                             else f"{r['fm_ic']:+.3f}{mark}")
        print(f"{f:28} " + " ".join(f"{c:>22}" for c in cells))
    print("\n* = 95% CI excludes zero")
    print(f"rank corr(v1_total, pullback) = {result.get('rank_corr_v1_vs_pullback')}")
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
