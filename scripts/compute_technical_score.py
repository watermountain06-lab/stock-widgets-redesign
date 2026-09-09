#!/usr/bin/env python3
"""Compute the '기술 상태 점수' (v1) from fetch_price.py output.

v1 spec (frozen 2026-08-18, see tech_score_config_v1.json):
  가격구조(60) = 추세구조(40) + 52주위치(20)  [conceptual grouping only]
  절대모멘텀(40)
  원점수 = 가격구조 + 절대모멘텀 (0-100)
  표시등급 = 원점수에 히스테리시스 적용(진입/이탈 경계 분리), 이전 상태 필요

Relative-momentum (vs SPY) was dropped: 45-ticker x 48-month backtest showed
Spearman rank correlation with absolute momentum >= 0.992 in every regime
(bull/bear/sideways) - the benchmark adjustment barely re-ranks tickers,
so it added complexity without discriminating power.

Not investment advice; a rule-based summary of price/volume state only.

Usage:
  python3 compute_technical_score.py TICKER --price NVDA_price_5y.json \\
      [--prev-state NVDA_tech_state.json] [--config tech_score_config_v1.json] \\
      [--out NVDA_tech_signal.json]
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).parent / "tech_score_config_v1.json"


def sma(closes, n, end):
    w = closes[end - n:end]
    return sum(w) / n if len(w) == n else None


def roc(closes, n, end):
    """end follows the same convention as sma(): exclusive length, so the
    last included bar is closes[end-1]."""
    idx = end - 1
    return closes[idx] / closes[idx - n] - 1 if idx - n >= 0 else None


def true_range_series(bars):
    tr = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return tr


def atr_pct_series(bars, period=14):
    tr = true_range_series(bars)
    closes = [b["c"] for b in bars[1:]]
    out = []
    for i in range(len(tr)):
        if i + 1 < period:
            out.append(None)
            continue
        atr = sum(tr[i + 1 - period:i + 1]) / period
        out.append(atr / closes[i] * 100)
    return out


def percentile_rank(series, value):
    valid = [x for x in series if x is not None]
    if len(valid) < 30:
        return None
    below = sum(1 for x in valid if x <= value)
    return below / len(valid) * 100


def bucket_score(value, bands):
    for band in bands:
        if band["upper_exclusive"] is None or value < band["upper_exclusive"]:
            return band["points"]
    return bands[-1]["points"]


def raw_grade(score, cuts):
    if score >= cuts["강한"]: return "강한"
    if score >= cuts["긍정적"]: return "긍정적"
    if score >= cuts["혼조"]: return "혼조"
    return "약한"


ORDER = ["약한", "혼조", "긍정적", "강한"]


def display_grade(score, prev_display_grade, cuts, gap):
    """Hysteresis: to move UP a level need score >= cut+gap/2,
    to move DOWN a level need score < cut-gap/2. No prior state -> raw grade."""
    half = gap / 2
    level_cuts = [cuts["혼조"], cuts["긍정적"], cuts["강한"]]  # 3 boundaries between 4 levels
    if prev_display_grade is None:
        return raw_grade(score, cuts)
    cur = ORDER.index(prev_display_grade)
    while cur < 3 and score >= level_cuts[cur] + half:
        cur += 1
    while cur > 0 and score < level_cuts[cur - 1] - half:
        cur -= 1
    return ORDER[cur]


def validate_prev_state(prev_state, ticker, config):
    """Return a usable prior displayGrade, or None (=treat as fresh/no-hysteresis)
    if the state is missing, malformed, from a different ticker, or from a
    different model version - never let a stale/foreign state crash the run
    or silently drive hysteresis under a different version's grade cuts."""
    if not isinstance(prev_state, dict):
        return None
    grade = prev_state.get("displayGrade")
    if grade not in ORDER:
        if prev_state:
            print(f"warning: prev-state displayGrade {grade!r} is not a recognized grade, ignoring", file=sys.stderr)
        return None
    if prev_state.get("ticker") not in (None, ticker):
        print(f"warning: prev-state ticker {prev_state.get('ticker')!r} != {ticker!r}, ignoring", file=sys.stderr)
        return None
    if prev_state.get("modelVersion") not in (None, config["version"]):
        print(f"warning: prev-state modelVersion {prev_state.get('modelVersion')!r} != {config['version']!r}, ignoring", file=sys.stderr)
        return None
    return grade


def compute_signal(ticker, price_data, config, prev_state=None):
    bars = price_data["daily"]
    closes = [b["c"] for b in bars]
    n = len(bars)
    as_of = bars[-1]["date"]
    close = closes[-1]

    result = {
        "ticker": ticker, "asOf": as_of, "close": close,
        "modelVersion": config["version"], "modelFrozenDate": config["frozen_date"],
        "disclaimer": "가격/거래량 데이터로 계산한 규칙 기반 기술 상태 요약이며, 투자 권고나 미래 수익률 예측이 아닙니다.",
    }

    if n < config["min_history_days"]:
        result["insufficientHistory"] = True
        result["nBars"] = n
        result["requiredBars"] = config["min_history_days"]
        return result
    result["insufficientHistory"] = False

    ts = config["trend_structure"]
    ma_short, ma_mid, ma_long = ts["ma_short"], ts["ma_mid"], ts["ma_long"]
    ma50, ma150, ma200 = sma(closes, ma_short, n), sma(closes, ma_mid, n), sma(closes, ma_long, n)
    ma200_prev = sma(closes, ma_long, n - ts["slope_lookback_days"])
    conds = {
        f"close>ma{ma_mid}_and_close>ma{ma_long}": close > ma150 and close > ma200,
        f"ma{ma_mid}>ma{ma_long}": ma150 > ma200,
        f"ma{ma_long}>ma{ma_long}_{ts['slope_lookback_days']}d_ago": ma200 > ma200_prev,
        f"ma{ma_short}>ma{ma_mid}_and_ma{ma_short}>ma{ma_long}": ma50 > ma150 and ma50 > ma200,
    }
    trend_score = sum(ts["points_per_condition"] for v in conds.values() if v)

    mc = config["momentum"]
    rocs = {p: roc(closes, p, n) for p in mc["periods_days"]}
    if len(mc["weights"]) != len(mc["periods_days"]):
        raise ValueError("momentum.weights and momentum.periods_days must be the same length")
    if any(v is None for v in rocs.values()):
        result["momentumUnavailable"] = True
        abs_mom, momentum_score = None, 0
    else:
        result["momentumUnavailable"] = False
        abs_mom = sum(w * rocs[p] for w, p in zip(mc["weights"], mc["periods_days"])) * 100
        momentum_score = bucket_score(abs_mom, mc["buckets"])

    pc = config["position_52w"]
    window = min(pc["window_days"], n)
    highs = [b["h"] for b in bars[-window:]]
    lows = [b["l"] for b in bars[-window:]]
    hi52, lo52 = max(highs), min(lows)
    rise = (close / lo52 - 1) * 100
    dd = (1 - close / hi52) * 100
    position_score = bucket_score(rise, pc["rise_from_low_bands"]) + bucket_score(dd, pc["drawdown_from_high_bands"])

    price_structure_score = trend_score + position_score  # conceptual "가격구조" grouping
    price_structure_max = ts["max_points"] + pc["max_points"]
    total = price_structure_score + momentum_score

    rf = config["risk_flags"]
    atr_series = atr_pct_series(bars, period=rf["atr_period"])
    atr_now = atr_series[-1] if atr_series else None
    # note: current value is included in its own percentile window by design
    # ("어디쯤 위치하는가" among the trailing window, not "vs strictly-prior history").
    atr_pctile = percentile_rank(atr_series[-rf["atr_history_window"]:], atr_now) if atr_now is not None else None

    flags = []
    if close < ma200:
        flags.append("장기추세이탈")
    if dd > rf["big_drawdown_from_high_pct"]:
        flags.append("고점대비큰조정")
    if atr_pctile is not None and atr_pctile >= rf["volatility_atr_percentile_threshold"]:
        flags.append("변동성급증(자체이력대비)")
    if close < ma50:
        flags.append("단기추세이탈")
    flags_sorted = [f for f in rf["priority_order"] if f in flags]

    grade_raw = raw_grade(total, config["raw_grade_cuts"])
    prev_display = validate_prev_state(prev_state, ticker, config)
    grade_display = display_grade(total, prev_display, config["raw_grade_cuts"],
                                   config["display_hysteresis"]["gap_points"]) if config["display_hysteresis"]["enabled"] else grade_raw

    result.update(
        trendStructure={"score": trend_score, "max": ts["max_points"], "conditions": conds},
        momentum={"score": momentum_score, "max": mc["max_points"], "weightedRocPct": round(abs_mom, 2) if abs_mom is not None else None},
        position52w={"score": position_score, "max": pc["max_points"], "riseFromLowPct": round(rise, 2), "drawdownFromHighPct": round(dd, 2),
                     "high52w": hi52, "low52w": lo52},
        priceStructureScore={"score": price_structure_score, "max": price_structure_max, "note": "추세구조+52주위치 개념적 상위그룹(v1, 상관 0.82로 별도 배점 재검토는 v2)"},
        rawScore=total,
        rawGrade=grade_raw,
        displayGrade=grade_display,
        riskFlags=flags_sorted,
        riskFlagsShown=flags_sorted[:rf["max_shown_on_card"]],
        atr={"pctNow": round(atr_now, 2) if atr_now is not None else None,
             "percentileVsOwnHistory": round(atr_pctile, 1) if atr_pctile is not None else None},
    )
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--price", required=True, help="fetch_price.py --range 5y (or 2y minimum) output")
    ap.add_argument("--prev-state", default=None, help="previous run's output JSON, for display-grade hysteresis")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.price) as f:
        price_data = json.load(f)
    with open(args.config) as f:
        config = json.load(f)
    prev_state = None
    if args.prev_state:
        try:
            with open(args.prev_state) as f:
                prev_state = json.load(f)
        except FileNotFoundError:
            print(f"warning: {args.prev_state} not found, no hysteresis prior state", file=sys.stderr)
        except json.JSONDecodeError:
            print(f"warning: {args.prev_state} is not valid JSON (possibly a truncated write), "
                  f"no hysteresis prior state", file=sys.stderr)

    result = compute_signal(args.ticker.upper(), price_data, config, prev_state)

    out_path = args.out or f"{args.ticker.upper()}_tech_signal.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path} - rawScore={result.get('rawScore','N/A')} "
          f"displayGrade={result.get('displayGrade','N/A')} flags={result.get('riskFlagsShown',[])}")


if __name__ == "__main__":
    main()
