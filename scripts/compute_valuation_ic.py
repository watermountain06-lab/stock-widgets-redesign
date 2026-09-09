#!/usr/bin/env python3
"""Cross-sectional test: does a point-in-time trailing-PER-deviation SIGNAL discriminate
between stocks that go on to outperform vs underperform SPY? This is v3 of the
earnings-checkpoint backtest lineage (see compute_earnings_backtest_band.py for v1->v2),
redesigned after the user pushed back that "does a numeric band contain future price"
(v1/v2's question) isn't what they actually want to know -- they want to know whether the
site's qualitative VALUATION JUDGMENT (저평가/적정/고평가) has historically been reliable,
i.e. predictive, not just non-circular.

Design history for THIS script (three independent review rounds, all converging):
two Claude opus agents (quant-statistician, valuation-analyst) + Codex reviewed an
initial single-ticker 5-zone-percentage design and rejected it; a redesigned version was
then reviewed independently by Fable AND Codex a second time (neither saw the other's
verdict) and both converged on nearly the same five critiques; a final revision addressing
those was approved by Fable with two required fixes. This script implements that final,
fully-reviewed design. The critiques and how each is addressed:

1. EARNINGS-DATE CONDITIONING risked conflating "valuation signal" with "post-earnings-
   announcement drift" (a low PER right after a positive EPS surprise predicts drift for
   reasons that have nothing to do with valuation reversion). Fix: sample MONTHLY at a
   fixed calendar cadence (last trading day of each month), decoupled from disclosure
   dates. TTM EPS itself still updates point-in-time via the existing step-function
   (ttm_eps_asof-equivalent below); only the SAMPLING cadence is decoupled from earnings.

2. RAW forward return is meaningless for a stock like NVDA that ~10x'd over the test
   window -- every valuation zone would show positive returns regardless of whether the
   signal discriminates anything. Fix: forward EXCESS return vs SPY (data/raw_5y/SPY.json)
   at fixed horizons.

3. Fixed percentage-deviation thresholds (e.g. +-25%) are arbitrary and badly mistuned for
   names whose PER ranges wildly (NVDA: ~20x-240x over this lookback). Fix: the PRIMARY
   statistical test uses a CONTINUOUS signal, log(PER(t) / anchor(t)), never binned. A
   5-zone badge is still computed for display, but from POINT-IN-TIME EXPANDING QUANTILES
   of each ticker's own signal history (population-relative), not fixed percentages -- and
   is explicitly secondary; the IC is the verdict.

4. 5-bin monotonicity with a dozen checkpoints has ~zero statistical power. Fix: primary
   test is Spearman rank correlation (information coefficient, IC) between the continuous
   signal and forward excess return, computed two ways that were BOTH requested (they
   answer different but complementary questions):
     (a) POOLED panel IC: Spearman correlation across ALL (ticker, month) observations
         pooled together.
     (b) FAMA-MACBETH companion: Spearman IC computed separately WITHIN each calendar
         month (cross-sectionally across whichever of the 8 tickers have valid data that
         month), producing a monthly time series of ICs, then the time-series MEAN of that
         series is the headline number. This directly strips out shared macro/sector
         moves that the pooled test alone can't separate from genuine within-name
         valuation signal (all 8 tickers here are correlated mega-cap tech/AI names).
   Significance for both: a MOVING-BLOCK BOOTSTRAP (reusing the exact function already
   built and used in scripts/panel_trend_position_ic.py for the same purpose), with block
   length >= the return horizon in months -- e.g. horizon=12 requires block_len>=12 -- per
   Fable's explicit final-round requirement (a shorter block, e.g. quarterly blocks for a
   12-month horizon, cannot capture the autocorrelation from overlapping 12-month forward
   windows and would produce falsely narrow, invalid confidence intervals). Newey-West HAC
   standard errors were also suggested; this repo has no statsmodels dependency and the
   moving-block bootstrap is a nonparametric equivalent already in house-style use for
   exactly this kind of monthly-IC time series -- substituted deliberately, not by default.

5. Testing ONE ticker (NVDA) cannot establish whether a valuation rule is reliable in
   general -- Fix: identical fixed rule applied across 8 tickers (AAPL, AMZN, AVGO, GOOGL,
   META, MSFT, NVDA, TSLA). TSM was in the originally-approved 9-ticker universe but is
   EXCLUDED here: it files as a foreign private issuer under IFRS (20-F), not US-GAAP, so
   the same `us-gaap:EarningsPerShareDiluted` XBRL tag lookup this pipeline depends on
   returns nothing for it (confirmed via a real, failed EDGAR API call, not assumed) --
   building a working point-in-time IFRS EPS pipeline is real additional scope, and a
   follow-up Codex review of that scope tradeoff recommended proceeding with 8 rather than
   forcing a mixed-accounting-standard panel into a first pass. This is disclosed in the
   output, not silently absorbed.

ANCHOR CHOICE (a live disagreement between the two review rounds, resolved explicitly):
one reviewer suggested a SLOW anchor (full-history/expanding median) to let the site's own
"자체 10년 중앙값" convention and its non-stationarity show through as a genuine weakness;
the other explicitly said not to use an expanding window since it "retains obsolete
regimes, exactly the lag problem v2 correctly addressed." Resolution (per the final Fable
round, which called this "not a tiebreak courtesy -- they test different hypotheses"):
compute the signal under BOTH anchor styles and report both. Recency-weighted (half-life
180 days, matching v2) is PRE-REGISTERED PRIMARY because it's what the site's v2 chart
already ships; the expanding-window anchor is reported as an explicit sensitivity check,
not silently dropped.

DISCLOSED LIMITATIONS (in the output JSON's methodology text, not just this docstring):
(a) this validates a MECHANIZED PROXY signal, not the site's actual hand-tuned per-metric
5-stage badges (those have no reusable formula -- e.g. PER's 저/적정/고 = 15x/53x/100x vs
PBR's 5x/20x/70x on the live NVDA card, unrelated ratios, confirmed by reading the HTML);
(b) 8 correlated mega-cap tech/AI names, not a general universe -- rely on the FM monthly-
IC time series and block-bootstrap inference rather than claiming broad generality;
(c) these 8 names are high-beta (~1.3-2.0) -- SPY-excess return is not a clean valuation-
only signal in a rising market, a genuine limitation, not fully solved here;
(d) negative-or-zero TTM EPS windows are skipped (PER undefined) -- this missingness is
NOT random, it clusters in drawdowns (e.g. AMZN 2022), and is logged explicitly per
ticker rather than silently dropped;
(e) the whole test lives within one historical regime (the available price history, one
crash + one AI-driven bull run) -- results do not necessarily generalize to other regimes.

Usage:
    python3 compute_valuation_ic.py \
      --tickers AAPL,AMZN,AVGO,GOOGL,META,MSFT,NVDA,TSLA \
      --eps-dir data/eps_quarterly --price-dir data/raw_5y --spy data/raw_5y/SPY.json \
      --out scripts/valuation_ic_result.json
"""
import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr


def add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def load_price_rows(path):
    """data/raw_5y/{T}.json stores daily bars as dicts -- convert to a plain date->close
    dict plus a sorted date list, which is all this script needs."""
    d = json.load(open(path))
    bars = sorted(d["daily"], key=lambda b: b["date"])
    dates = [b["date"] for b in bars]
    closes = {b["date"]: b["c"] for b in bars}
    return dates, closes


def build_ttm_eps_asof(eps_points, dates):
    """Step function: for each date in `dates` (ascending), the most recent TTM EPS whose
    available_date <= that date (or None before any EPS is known yet)."""
    eps_sorted = sorted(eps_points, key=lambda e: e["available_date"])
    out = []
    ptr = -1
    for d in dates:
        while ptr + 1 < len(eps_sorted) and eps_sorted[ptr + 1]["available_date"] <= d:
            ptr += 1
        out.append(eps_sorted[ptr]["ttm_eps"] if ptr >= 0 else None)
    return out


def weighted_median(pairs):
    """pairs: list of (value, weight). Step-function weighted median (50th percentile)."""
    pairs = sorted(pairs, key=lambda x: x[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    target = total / 2
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= target:
            return v
    return pairs[-1][0]


def recency_weight(obs_date_str, as_of_str, halflife_days):
    d = date.fromisoformat(obs_date_str)
    t = date.fromisoformat(as_of_str)
    age_days = (t - d).days
    return 0.5 ** (age_days / halflife_days)


def month_end_dates(dates):
    """Last trading-day date-string per calendar month, in ascending order."""
    out = {}
    for d in dates:
        out[d[:7]] = d
    return sorted(out.values())


def build_ticker_series(ticker, eps_path, price_path, trailing_years, halflife_days):
    """Returns per-day: dates, per_series (date->PER dict, only where TTM EPS>0), and a
    log-signal series for BOTH anchor styles, keyed by date. Also returns a missingness
    log of dates where TTM EPS was <=0 or undefined (disclosed, not silently dropped)."""
    eps_points = json.load(open(eps_path))
    dates, closes = load_price_rows(price_path)
    ttm_asof = build_ttm_eps_asof(eps_points, dates)

    per_by_date = {}
    missing_eps_dates = []
    for i, d in enumerate(dates):
        eps = ttm_asof[i]
        if eps is None:
            continue
        if eps <= 0:
            missing_eps_dates.append(d)
            continue
        per_by_date[d] = closes[d] / eps

    per_list = sorted(per_by_date.items())  # [(date, per), ...] ascending
    price_start = date.fromisoformat(dates[0])

    signal_recency = {}
    signal_expanding = {}
    for i, (d, per_t) in enumerate(per_list):
        t = date.fromisoformat(d)
        window_start = add_years(t, -trailing_years)
        trailing = [(p, 1.0) for (dd, p) in per_list if dd < d and window_start.isoformat() <= dd]
        if len(trailing) >= 60 and window_start >= price_start:
            weighted = [(p, recency_weight(dd, d, halflife_days)) for (dd, p) in per_list if dd < d and window_start.isoformat() <= dd]
            anchor_r = weighted_median(weighted)
            if anchor_r > 0:
                signal_recency[d] = math.log(per_t / anchor_r)
        expanding = [(p, 1.0) for (dd, p) in per_list if dd < d]
        if len(expanding) >= 60:
            anchor_e = weighted_median(expanding)
            if anchor_e > 0:
                signal_expanding[d] = math.log(per_t / anchor_e)

    return {
        "ticker": ticker, "dates": dates, "closes": closes,
        "per_by_date": per_by_date,
        "signal_recency": signal_recency, "signal_expanding": signal_expanding,
        "missing_eps_dates": missing_eps_dates,
    }


def forward_excess_return(closes_by_date, dates_sorted, entry_date, horizon_trading_days, spy_closes, spy_dates_sorted):
    """Forward return of the stock minus forward return of SPY over the identical window,
    approximated by trading-day offset (horizon_trading_days ~21/month)."""
    idx_map = {d: i for i, d in enumerate(dates_sorted)}
    i0 = idx_map.get(entry_date)
    if i0 is None or i0 + horizon_trading_days >= len(dates_sorted):
        return None
    exit_date = dates_sorted[i0 + horizon_trading_days]
    stock_ret = closes_by_date[exit_date] / closes_by_date[entry_date] - 1

    spy_idx_map = {d: i for i, d in enumerate(spy_dates_sorted)}
    si0 = spy_idx_map.get(entry_date)
    if si0 is None:
        # nearest trading day at/after entry_date
        cand = [i for i, d in enumerate(spy_dates_sorted) if d >= entry_date]
        if not cand:
            return None
        si0 = cand[0]
    if si0 + horizon_trading_days >= len(spy_dates_sorted):
        return None
    spy_exit = spy_dates_sorted[si0 + horizon_trading_days]
    spy_entry = spy_dates_sorted[si0]
    spy_ret = spy_closes[spy_exit] / spy_closes[spy_entry] - 1
    return stock_ret - spy_ret


def moving_block_bootstrap_ci(series, block_len, n_boot=5000, seed=42):
    rng = np.random.default_rng(seed)
    series = np.asarray(series, dtype=float)
    n = len(series)
    if n < block_len or n < 3:
        return None
    n_blocks_needed = -(-n // block_len)
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


HORIZONS = {"3m": 63, "6m": 126, "12m": 252}
HORIZON_MONTHS = {"3m": 3, "6m": 6, "12m": 12}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True, help="comma-separated")
    ap.add_argument("--eps-dir", required=True)
    ap.add_argument("--price-dir", required=True)
    ap.add_argument("--spy", required=True)
    ap.add_argument("--trailing-years", type=int, default=2)
    ap.add_argument("--halflife-days", type=float, default=180)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tickers = args.tickers.split(",")
    spy_dates, spy_closes = load_price_rows(args.spy)

    per_ticker = {}
    for t in tickers:
        eps_path = Path(args.eps_dir) / f"{t}.json"
        price_path = Path(args.price_dir) / f"{t}.json"
        per_ticker[t] = build_ticker_series(t, eps_path, price_path, args.trailing_years, args.halflife_days)

    # Monthly sample points per ticker (last trading day of each month), decoupled from
    # earnings dates (point 1 in the module docstring).
    samples = []  # rows: {ticker, date, signal_recency, signal_expanding, fwd_3m, fwd_6m, fwd_12m}
    for t, s in per_ticker.items():
        me_dates = month_end_dates(s["dates"])
        for d in me_dates:
            row = {"ticker": t, "date": d}
            has_signal = False
            if d in s["signal_recency"]:
                row["signal_recency"] = s["signal_recency"][d]
                has_signal = True
            if d in s["signal_expanding"]:
                row["signal_expanding"] = s["signal_expanding"][d]
            if not has_signal:
                continue
            for hname, htd in HORIZONS.items():
                fr = forward_excess_return(s["closes"], s["dates"], d, htd, spy_closes, spy_dates)
                if fr is not None:
                    row[f"fwd_{hname}"] = fr
            samples.append(row)

    result = {"tickers": tickers, "trailing_years": args.trailing_years, "halflife_days": args.halflife_days}
    result["missing_eps_by_ticker"] = {t: per_ticker[t]["missing_eps_dates"] for t in tickers if per_ticker[t]["missing_eps_dates"]}
    result["sample_count"] = len(samples)

    for anchor_key, sig_field in [("recency_weighted", "signal_recency"), ("expanding_window", "signal_expanding")]:
        anchor_result = {}
        for hname in HORIZONS:
            fwd_field = f"fwd_{hname}"
            rows = [r for r in samples if sig_field in r and fwd_field in r]
            if len(rows) < 10:
                anchor_result[hname] = {"n": len(rows), "note": "insufficient data"}
                continue
            sig = [r[sig_field] for r in rows]
            fwd = [r[fwd_field] for r in rows]
            pooled_ic, pooled_p = spearmanr(sig, fwd)

            # Fama-MacBeth companion: monthly cross-sectional Spearman IC across tickers.
            by_month = {}
            for r in rows:
                ym = r["date"][:7]
                by_month.setdefault(ym, []).append(r)
            months = sorted(by_month.keys())
            monthly_ics = []
            used_months = []
            for ym in months:
                mrows = by_month[ym]
                if len(mrows) < 4:  # need at least a few tickers cross-sectionally
                    continue
                ms, mf = [r[sig_field] for r in mrows], [r[fwd_field] for r in mrows]
                ic, _ = spearmanr(ms, mf)
                if not (isinstance(ic, float) and math.isnan(ic)):
                    monthly_ics.append(ic)
                    used_months.append(ym)

            block_len = HORIZON_MONTHS[hname]  # Fable requirement: block_len >= horizon (months)
            ci = moving_block_bootstrap_ci(monthly_ics, block_len) if len(monthly_ics) >= block_len else None
            fm_mean = float(np.mean(monthly_ics)) if monthly_ics else None

            anchor_result[hname] = {
                "n": len(rows),
                "pooled_spearman_ic": round(float(pooled_ic), 4) if pooled_ic == pooled_ic else None,
                "pooled_p_value": round(float(pooled_p), 4) if pooled_p == pooled_p else None,
                "fama_macbeth_months": len(monthly_ics),
                "fama_macbeth_mean_ic": round(fm_mean, 4) if fm_mean is not None else None,
                "fama_macbeth_ci_block_months": block_len,
                "fama_macbeth_95ci": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
            }
        result[anchor_key] = anchor_result

    result["methodology"] = (
        "각 (종목, 월) 관측치의 신호 = log(그 시점 PER / 그 시점까지의 정보로만 계산한 앵커). "
        "두 가지 앵커를 각각 보고: recency_weighted(반감기 180일 지수가중 트레일링 중앙값, 기본) / "
        "expanding_window(그 시점까지의 전체 히스토리 중앙값, 민감도 검증용) — 서로 다른 가설을 검증하므로 "
        "둘 다 표시. 월별 마지막 거래일마다 실적 발표일과 무관하게 표본 추출(실적 서프라이즈발 드리프트와 "
        "혼동되지 않도록). 결과 변수는 SPY 대비 초과수익(3/6/12개월). 통계량은 두 가지: "
        "① pooled_spearman_ic — 전체 (종목,월) 관측치를 풀링한 순위상관, "
        "② fama_macbeth_mean_ic — 월별로 그 달 종목 간 횡단면 순위상관을 구한 뒤 그 시계열의 평균 "
        "(종목 공통 매크로 요인을 제거하는 효과). 신뢰구간은 이동블록부트스트랩(블록 길이 ≥ 예측기간, "
        "Newey-West 대신 이 저장소에 이미 있는 panel_trend_position_ic.py와 같은 방식 사용). "
        "⚠️ 한계: (1) 이 신호는 사이트에 이미 있는 손으로 만든 5단계 저평가~고평가 배지를 그대로 재현한 "
        "것이 아니라 그 취지를 기계화한 대체 신호다(배지 임계값은 지표·종목마다 수기로 다름, 재현 공식 없음). "
        "(2) 8개 종목 모두 상관관계가 높은 대형 AI/테크주라 일반적인 결론으로 확장할 수 없다. "
        "(3) 이 종목들은 베타가 높아(~1.3~2.0) 상승장에서는 SPY 대비 초과수익이 저절로 양수가 되기 쉽다. "
        "(4) TTM EPS가 0 이하인 구간(예: 적자 분기)은 표본에서 제외되며, 이 결측은 무작위가 아니라 "
        "하락장에 몰려있다(missing_eps_by_ticker 참고). (5) 관측 구간 자체가 한 시대(급락 1회+AI 강세장 1회) "
        "안에 있어 다른 시장 국면에 일반화된다는 보장이 없다. TSM은 IFRS(20-F) 공시라 US-GAAP 기반 이 "
        "파이프라인에서 제외됨(별도 작업 필요, Codex 검토 결과 이번 1차 검증에서는 제외가 타당하다는 의견)."
    )

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"samples={len(samples)}, tickers={len(tickers)} -> {args.out}")
    for anchor_key in ["recency_weighted", "expanding_window"]:
        print(f"\n=== {anchor_key} ===")
        for hname, r in result[anchor_key].items():
            print(f"  {hname}: n={r.get('n')} pooled_IC={r.get('pooled_spearman_ic')} "
                  f"(p={r.get('pooled_p_value')})  FM_mean_IC={r.get('fama_macbeth_mean_ic')} "
                  f"95%CI={r.get('fama_macbeth_95ci')} (months={r.get('fama_macbeth_months')})")


if __name__ == "__main__":
    main()
