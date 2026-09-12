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
    result["verdict"] = (
        "통제 유니버스 492종목·22,121 (종목,월) 표본에서 기술 상태 점수 v1이 모든 기간에서 "
        "눌림목 점수를 이긴다. v1 FM IC는 60일 +0.051 / 6개월 +0.112 / 12개월 +0.109으로 "
        "신뢰구간이 0을 배제하고, 눌림목 총점은 20일 −0.009 / 60일 +0.018 / 6개월 +0.011 / "
        "12개월 +0.020으로 어느 기간에서도 0과 구별되지 않는다. 눌림목의 본진인 20~60일에서도 "
        "0이므로 '기간 선택이 불공정했다'로는 설명되지 않는다. 부수적으로, 손으로 고르지 않은 "
        "유니버스에서 v1을 처음 재채점한 결과 두 절반이 모두 살아남았다(가격구조 12개월 +0.090, "
        "모멘텀 +0.111). 눌림목을 분해하면 셋업 40점은 약한 양(12개월 +0.075)이고 진입 타이밍 "
        "60점은 유의하게 음(−0.048)이어서 서로 상쇄된다. 셋업이 일하는 이유는 필수조건인 "
        "'임펄스 상승률 ≥20%'가 모멘텀의 약한 대용이기 때문이고, 진입 점수가 역방향인 이유는 "
        "지지선 근접·깊은 되돌림·낮은 RSI에 높은 점수를 줘서 더 많이 빠진 종목을 고르기 "
        "때문이다. 합치는 문제: v1 상위 3분위 안에서 눌림목 총점이 60일 +2.73%의 추가 스프레드를 "
        "내고 세 변형 모두 같은 부호로 재현되지만(12개월은 zigzag에서 부호가 뒤집혀 사전선언 "
        "기준 미달), 같은 자리에서 v1 자신의 연속 ROC가 +7.23%, 임펄스 상승률이 +6.69%로 더 "
        "크게 기여한다. 즉 눌림목이 더하는 것은 v1에 없는 정보가 아니라 v1이 모멘텀을 40점 "
        "구간으로 뭉개며 버린 해상도이며, 그 해상도는 눌림목을 붙이는 것보다 모멘텀의 구간화를 "
        "푸는 쪽이 더 잘 회복한다. 결론: 눌림목 도입 근거 없음, v1 유지, v2 후보는 "
        "'모멘텀 구간화 완화'(탐색적 결과이므로 사전선언 후 별도 검정 필요).")

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
