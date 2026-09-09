#!/usr/bin/env python3
"""Tier 1: 추세구조(T) vs 52주위치(P) 월별 횡단면 IC 비교.

Codex 2라운드 검증을 거친 축소 설계(2026-08-18):
  - signed 다이버전스 D = T/40 - P/20, 월별 횡단면 tercile로 상태 기술통계만 (확정검정 아님)
  - 핵심검정: 매월 47종목 횡단면에서 IC_T=corr(T, fwd), IC_P=corr(P, fwd) (Spearman),
    ΔIC(t) = IC_T(t) - IC_P(t) 의 48개월 시계열 → 이동블록부트스트랩(월 축)으로 CI
  - 이 핵심검정이 답하는 질문: "전체 횡단면에서 T·P 중 어느 쪽 단독 순위예측력이 더 강한가"
    (다이버전스 상황에서의 우열이 아님 - tercile 안에서 재검정하면 월별 표본이
    ~15종목까지 줄어 불안정해지므로 하지 않음, Codex round-2 권고)
  - 패널 고정효과 회귀 / two-way clustering / walk-forward OOS 리웨이팅은 Tier 2(미실행)

Not investment advice; a research diagnostic on top of a rule-based technical score.
"""
import json
import statistics
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

import sys
sys.path.insert(0, str(Path(__file__).parent))
from compute_technical_score import sma  # noqa: E402

DATA = Path(__file__).parent.parent / "data" / "raw_5y"
CONFIG = json.load(open(Path(__file__).parent / "tech_score_config_v1.json"))
MIN_HISTORY = CONFIG["min_history_days"]
TS = CONFIG["trend_structure"]
PC = CONFIG["position_52w"]

TICKERS = sorted(p.stem for p in DATA.glob("*.json") if p.stem != "SPY")


def load(t):
    return json.load(open(DATA / f"{t}.json"))["daily"]


def bucket_score(value, bands):
    for band in bands:
        if band["upper_exclusive"] is None or value < band["upper_exclusive"]:
            return band["points"]
    return bands[-1]["points"]


def trend_and_position(bars, closes, idx):
    """idx = last included bar (0-based). Mirrors compute_technical_score.compute_signal's
    trend_score/position_score exactly, but evaluated as-of a historical idx instead of
    the last bar, so no data beyond idx leaks into the score."""
    n = idx + 1
    ma_short, ma_mid, ma_long = TS["ma_short"], TS["ma_mid"], TS["ma_long"]
    ma50 = sma(closes, ma_short, n)
    ma150 = sma(closes, ma_mid, n)
    ma200 = sma(closes, ma_long, n)
    ma200_prev = sma(closes, ma_long, n - TS["slope_lookback_days"])
    if None in (ma50, ma150, ma200, ma200_prev):
        return None, None
    conds = [
        close_gt_both := (closes[idx] > ma150 and closes[idx] > ma200),
        ma150 > ma200,
        ma200 > ma200_prev,
        (ma50 > ma150 and ma50 > ma200),
    ]
    trend_score = sum(TS["points_per_condition"] for c in conds if c)

    window = min(PC["window_days"], n)
    hi_window = bars[idx + 1 - window:idx + 1]
    hi52 = max(b["h"] for b in hi_window)
    lo52 = min(b["l"] for b in hi_window)
    close = closes[idx]
    rise = (close / lo52 - 1) * 100
    dd = (1 - close / hi52) * 100
    position_score = bucket_score(rise, PC["rise_from_low_bands"]) + bucket_score(dd, PC["drawdown_from_high_bands"])
    return trend_score, position_score


def month_end_indices(dates):
    """Last trading-day index per calendar month, in order."""
    out = {}
    for i, d in enumerate(dates):
        out[d[:7]] = i
    return out


def build_panel():
    """Returns dict: yyyymm -> list of rows {ticker, T, P, fwd20, fwd60}."""
    panel = {}
    for t in TICKERS:
        bars = load(t)
        closes = [b["c"] for b in bars]
        n = len(bars)
        me = month_end_indices([b["date"] for b in bars])
        for ym, idx in me.items():
            if idx + 1 < MIN_HISTORY:
                continue
            if idx + 60 >= n:
                continue  # need 60d forward available (also covers 20d)
            trend_score, position_score = trend_and_position(bars, closes, idx)
            if trend_score is None:
                continue
            entry = closes[idx]
            fwd20 = closes[idx + 20] / entry - 1
            fwd60 = closes[idx + 60] / entry - 1
            row = dict(ticker=t, T=trend_score, P=position_score, fwd20=fwd20, fwd60=fwd60)
            panel.setdefault(ym, []).append(row)
    return panel


def monthly_ic_series(panel, fwd_key, min_n=10):
    """Per month: Spearman(T, fwd), Spearman(P, fwd) across that month's tickers."""
    months = sorted(panel.keys())
    ic_t, ic_p, used_months = [], [], []
    for ym in months:
        rows = panel[ym]
        if len(rows) < min_n:
            continue
        Ts = [r["T"] for r in rows]
        Ps = [r["P"] for r in rows]
        Fs = [r[fwd_key] for r in rows]
        # guard against zero-variance months (all T equal, etc.) -> spearmanr gives nan
        rt, _ = spearmanr(Ts, Fs)
        rp, _ = spearmanr(Ps, Fs)
        if np.isnan(rt) or np.isnan(rp):
            continue
        ic_t.append(rt)
        ic_p.append(rp)
        used_months.append(ym)
    return used_months, np.array(ic_t), np.array(ic_p)


def moving_block_bootstrap_ci(series, block_len, n_boot=5000, seed=42):
    """Moving-block bootstrap CI for the mean of a 1D series."""
    rng = np.random.default_rng(seed)
    n = len(series)
    if n < block_len:
        return None
    n_blocks_needed = -(-n // block_len)  # ceil
    starts_max = n - block_len
    means = np.empty(n_boot)
    for b in range(n_boot):
        idxs = []
        for _ in range(n_blocks_needed):
            s = rng.integers(0, starts_max + 1)
            idxs.extend(range(s, s + block_len))
        sample = series[idxs[:n]]
        means[b] = sample.mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def describe_state_returns(panel):
    """Descriptive only: monthly cross-sectional D=T/40-P/20 tercile states."""
    months = sorted(panel.keys())
    states = {"추세우위": {"fwd20": [], "fwd60": []},
              "일치": {"fwd20": [], "fwd60": []},
              "위치우위": {"fwd20": [], "fwd60": []}}
    for ym in months:
        rows = panel[ym]
        if len(rows) < 10:
            continue
        Ds = [(r["ticker"], r["T"] / 40 - r["P"] / 20) for r in rows]
        Ds_sorted = sorted(Ds, key=lambda x: x[1])
        n = len(Ds_sorted)
        lo_cut = n // 3
        hi_cut = n - n // 3
        lo_set = {tk for tk, _ in Ds_sorted[:lo_cut]}       # D 하위 tercile = 위치우위
        hi_set = {tk for tk, _ in Ds_sorted[hi_cut:]}       # D 상위 tercile = 추세우위
        for r in rows:
            if r["ticker"] in hi_set:
                label = "추세우위"
            elif r["ticker"] in lo_set:
                label = "위치우위"
            else:
                label = "일치"
            states[label]["fwd20"].append(r["fwd20"])
            states[label]["fwd60"].append(r["fwd60"])
    return states


def main():
    print("패널 구축 중...")
    panel = build_panel()
    months = sorted(panel.keys())
    print(f"패널: {len(months)}개월 ({months[0]} ~ {months[-1]}), "
          f"종목-월 관측치 총 {sum(len(v) for v in panel.values())}건, "
          f"유니버스 {len(TICKERS)}종목")

    print("\n" + "=" * 70)
    print("(1) 상태별 순방향수익률 기술통계 (signed D=T/40-P/20, 월별 횡단면 tercile)")
    print("    *** 확정 검정 아님, 해석용 기술통계만 ***")
    states = describe_state_returns(panel)
    for label in ["추세우위", "일치", "위치우위"]:
        for hz in ["fwd20", "fwd60"]:
            vals = states[label][hz]
            if not vals:
                continue
            print(f"  {label:6s} {hz}: mean={statistics.mean(vals)*100:+.2f}%  "
                  f"median={statistics.median(vals)*100:+.2f}%  n={len(vals)}")

    print("\n" + "=" * 70)
    print("(2) 핵심검정: 월별 횡단면 IC 시계열 및 ΔIC=IC_T-IC_P")
    print("    질문: 전체 횡단면에서 T·P 중 어느 쪽 단독 순위예측력이 평균적으로 더 강한가")
    for fwd_key, hz_label, block_lens in [("fwd20", "20일", [2]), ("fwd60", "60일", [2, 3, 4, 6])]:
        used_months, ic_t, ic_p = monthly_ic_series(panel, fwd_key)
        delta = ic_t - ic_p
        print(f"\n  --- {hz_label} 순방향수익률 기준, 유효 {len(used_months)}개월 "
              f"({used_months[0]}~{used_months[-1]}) ---")
        print(f"  IC_T  mean={ic_t.mean():+.4f} median={np.median(ic_t):+.4f}")
        print(f"  IC_P  mean={ic_p.mean():+.4f} median={np.median(ic_p):+.4f}")
        sign_ratio = (delta > 0).mean()
        print(f"  ΔIC   mean={delta.mean():+.4f} median={np.median(delta):+.4f} "
              f"부호일관성(ΔIC>0인 달 비율)={sign_ratio*100:.1f}%")
        for bl in block_lens:
            ci = moving_block_bootstrap_ci(delta, bl)
            if ci:
                print(f"    블록길이{bl}개월 부트스트랩 95%CI: [{ci[0]:+.4f}, {ci[1]:+.4f}]"
                      f"{'  <- 기본값' if (hz_label=='20일' and bl==2) or (hz_label=='60일' and bl==3) else ''}")

        # leave-few-months-out sensitivity: drop each decile of months, recompute mean delta
        print("  민감도(월 10% 무작위 제외 x 20회, mean ΔIC 범위):", end=" ")
        rng = np.random.default_rng(1)
        drop_n = max(1, len(delta) // 10)
        alt_means = []
        for _ in range(20):
            keep = np.ones(len(delta), dtype=bool)
            drop_idx = rng.choice(len(delta), size=drop_n, replace=False)
            keep[drop_idx] = False
            alt_means.append(delta[keep].mean())
        print(f"[{min(alt_means):+.4f}, {max(alt_means):+.4f}]")

    print("\n" + "=" * 70)
    print("(3) 사전등록된 Tier 2 진입기준 판정 (결과 확인 전 확정된 6개 기준)")
    used20, ict20, icp20 = monthly_ic_series(panel, "fwd20")
    used60, ict60, icp60 = monthly_ic_series(panel, "fwd60")
    d20, d60 = ict20 - icp20, ict60 - icp60
    crit = {
        "1. 평균 ΔIC 방향 20일=60일 일치": (d20.mean() > 0) == (d60.mean() > 0),
        "2. 중앙값 ΔIC 방향 20일=60일 일치": (np.median(d20) > 0) == (np.median(d60) > 0),
        "3. 부호비율이 50%대 중반 밖 (60d 기준, <40% 또는 >60%)": not (0.40 <= (d60 > 0).mean() <= 0.60),
    }
    for k, v in crit.items():
        print(f"  {'PASS' if v else 'FAIL'} - {k}")
    print("  4~6번(블록길이 민감도/월제외 민감도/효과크기 실질성)은 위 출력 수치를 보고 육안 판단 필요")


if __name__ == "__main__":
    main()
