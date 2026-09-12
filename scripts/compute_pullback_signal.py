#!/usr/bin/env python3
"""눌림목(pullback) 셋업 게이트 + 진입 타이밍 점수 — 비교검정용 구현.

Purpose: the user asked which is better for the #tech tab, the shipped 기술 상태 점수 v1
(가격구조60 + 절대모멘텀40) or a 눌림목매매 style score, and whether the two should be
combined. Neither question can be answered by argument, so both have to be put on one
panel and measured the same way. This module supplies the second signal.

The rule is reconstructed from kospi10000.kr's published data/technical_score.json
(108 KOSPI names, as_of 2026-09-08), which exposes every intermediate value and band
label, so the thresholds below are read off real output rather than guessed. Two things
found while reading it, both deliberate departures rather than oversights:

1. A LABEL/IMPLEMENTATION MISMATCH IN THE SOURCE. Its 셋업 condition is labelled
   "되돌림 비율 30~61.8%", which is the Fibonacci retracement of the impulse leg, but the
   value it stores and tests is the drawdown from the peak: (peak-close)/peak. All 108
   records match the drawdown formula and none match the Fibonacci one, and the effective
   threshold is >=10%, not 30~61.8%. 27 of the 108 names whose true Fibonacci retracement
   IS inside 30~61.8% are therefore marked 부적격 -- 삼성전자 among them (true retracement
   30.58%, stored 6.42%). This module computes BOTH and exposes them as two variants
   (`retrace_mode="source"` reproduces the site, `"fib"` implements the label), because a
   comparison that silently picks one would be assuming the answer.

2. TWO SOURCE COMPONENTS ARE NOT PORTABLE AND ARE EXCLUDED HERE.
   - 수급 점수 (별도 10점) reads institution_net_sum / foreign_net_sum, i.e. KRX's
     investor-type flow data. US markets have no equivalent (13F is quarterly and lagged).
   - 위험 감점 (0 ~ -40) was already rejected for this repo's v1 score, for double-
     penalising a weakness the sub-scores already carry and for a large negative reading
     as more alarming than warranted. The source's own output vindicates that: penalties
     reach -40, and 크래프톤 scores 5+23-35 = -7, floored to 0. Its fifth penalty item is
     also KRX flow data ("개인 단독 매수 지속"). Excluded, so the score here is
     setup(40) + entry(60) with no deductions.
   The source's 돌파 신호 (별도 10점) is excluded too: it uses a 20-day pivot, while this
   repo already ships a 60-day-pivot breakout signal whose own 20-day edge measured zero
   against a same-day baseline (see verify_breakout_vs_baseline.py).

IMPULSE DETECTION is the one piece the source does not publish. Its impulse legs run
1-26 trading days, so some swing detector is involved, but the definition is not given.
Rather than reverse-engineer it, this module implements two definitions declared IN
ADVANCE and reports both; a conclusion that holds under only one of them is not a
conclusion:
    "window"  lowest low of the trailing `impulse_lookback` bars, then the highest high
              after it. Simple and exactly reproducible.
    "zigzag"  ATR-based swing detection (reusing breakout_signal.atr_series), taking the
              most recent completed swing low -> swing high.

Scoring (from the source's published bands):
  셋업 40 = 임펄스 상승률>=20% (10) + 되돌림 적정 (10) + 종가>지지선 (10)
            + 고점 후 3~20거래일 (5) + 임펄스 구간 거래량>=직전 1.5배 (5)
  진입 60 = 지지선 이격도 (12) + 되돌림 위치 (8) + 조정중 거래량 감소 (12)
            + 변동성 축소 (10) + RSI 반등 (10) + 반전 캔들 (8)
  게이트(setup_qualified) = 임펄스·되돌림·지지선·기간 4개 필수조건 전부 충족
                            (거래량 조건은 배점에만 반영, 소스의 mandatory 판정과 동일)

Usage as a library: score_at(bars, i, ...) returns the score as of bar i, using only
bars[:i+1] -- no look-ahead. Used by compare_tech_signals.py to build a monthly panel.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from breakout_signal import atr_series  # noqa: E402

IMPULSE_MIN_GAIN_PCT = 20.0
IMPULSE_LOOKBACK = 60
PULLBACK_MIN_DAYS, PULLBACK_MAX_DAYS = 3, 20
IMPULSE_VOLUME_RATIO = 1.5
FIB_LO, FIB_HI = 30.0, 61.8
SOURCE_RETRACE_MIN = 10.0
ZIGZAG_ATR_MULT = 2.0


def _band(value, bands):
    """bands: [(upper_exclusive_or_None, score)] scanned in order; None = open-ended."""
    for upper, score in bands:
        if upper is None or value < upper:
            return score
    return 0.0


def _rsi(closes, period=14):
    """Wilder-smoothed RSI over the closes given, as of the last element."""
    if len(closes) <= period:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[1:period + 1], closes[2:period + 2]) if False else zip(closes[:period], closes[1:period + 1]):
        d = b - a
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period
    for a, b in zip(closes[period:-1], closes[period + 1:]):
        d = b - a
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def _swings(bars, end, atr_pct_full, mult=ZIGZAG_ATR_MULT):
    """ATR-threshold zigzag over bars[:end+1]. Returns alternating pivots
    [(index, price, 'L'|'H'), ...] in ascending index order."""
    piv = []
    if end < 30:
        return piv
    direction = None
    ext_i, ext_p = 0, bars[0]["c"]
    for i in range(1, end + 1):
        a = atr_pct_full[i] if i < len(atr_pct_full) else None
        thr = (a * mult) if a else 0.05
        h, l = bars[i]["h"], bars[i]["l"]
        if direction in (None, "up"):
            if h > ext_p:
                ext_i, ext_p = i, h
            elif ext_p > 0 and (ext_p - l) / ext_p >= thr:
                piv.append((ext_i, ext_p, "H"))
                direction, ext_i, ext_p = "down", i, l
                continue
            direction = "up"
        if direction == "down":
            if l < ext_p:
                ext_i, ext_p = i, l
            elif ext_p > 0 and (h - ext_p) / ext_p >= thr:
                piv.append((ext_i, ext_p, "L"))
                direction, ext_i, ext_p = "up", i, h
    return piv


def find_impulse(bars, i, mode, atr_pct_full):
    """Most recent impulse leg ending at or before bar i. Returns
    {start_index, start_price, peak_index, peak_price, gain_pct} or None."""
    if mode == "window":
        lo = max(0, i - IMPULSE_LOOKBACK + 1)
        seg = range(lo, i + 1)
        s = min(seg, key=lambda k: bars[k]["l"])
        after = range(s, i + 1)
        p = max(after, key=lambda k: bars[k]["h"])
        if p <= s:
            return None
        sp, pp = bars[s]["l"], bars[p]["h"]
    elif mode == "zigzag":
        piv = _swings(bars, i, atr_pct_full)
        low = high = None
        for idx, price, kind in reversed(piv):
            if high is None and kind == "H":
                high = (idx, price)
            elif high is not None and kind == "L":
                low = (idx, price)
                break
        if not (low and high) or high[0] <= low[0]:
            return None
        s, sp = low
        p, pp = high
    else:
        raise ValueError(mode)
    if sp <= 0 or pp <= sp:
        return None
    return {"start_index": s, "start_price": sp, "peak_index": p, "peak_price": pp,
            "gain_pct": (pp / sp - 1) * 100}


def score_at(bars, i, impulse_mode="window", retrace_mode="source", atr_pct_full=None):
    """Score as of bar i using only bars[:i+1]. Returns None when not computable."""
    if i < 80:
        return None
    if atr_pct_full is None:
        a = atr_series(bars[:i + 1], period=20)
        atr_pct_full = [None] + [(x / bars[k + 1]["c"] if x else None) for k, x in enumerate(a)]
    imp = find_impulse(bars, i, impulse_mode, atr_pct_full)
    if imp is None:
        return None

    close = bars[i]["c"]
    support, peak = imp["start_price"], imp["peak_price"]
    days_since_peak = i - imp["peak_index"]
    dd_from_peak = (peak - close) / peak * 100
    fib_retrace = (peak - close) / (peak - support) * 100
    retrace = dd_from_peak if retrace_mode == "source" else fib_retrace

    # --- 셋업 40 ---
    c_impulse = imp["gain_pct"] >= IMPULSE_MIN_GAIN_PCT
    c_retrace = (retrace >= SOURCE_RETRACE_MIN) if retrace_mode == "source" else (FIB_LO <= retrace <= FIB_HI)
    c_support = close > support
    c_days = PULLBACK_MIN_DAYS <= days_since_peak <= PULLBACK_MAX_DAYS
    ilen = imp["peak_index"] - imp["start_index"] + 1
    pri_lo = max(0, imp["start_index"] - ilen)
    imp_vol = sum(b["v"] for b in bars[imp["start_index"]:imp["peak_index"] + 1]) / ilen
    pri = bars[pri_lo:imp["start_index"]]
    pri_vol = (sum(b["v"] for b in pri) / len(pri)) if pri else None
    c_vol = bool(pri_vol) and imp_vol >= IMPULSE_VOLUME_RATIO * pri_vol
    setup = 10 * c_impulse + 10 * c_retrace + 10 * c_support + 5 * c_days + 5 * c_vol
    qualified = c_impulse and c_retrace and c_support and c_days

    # --- 진입 60 ---
    if close < support:
        s_support_dist = 0.0
    else:
        gap = (close - support) / support * 100
        s_support_dist = _band(gap, [(3, 12.0), (6, 10.0), (10, 6.0), (15, 3.0), (None, 0.0)])

    if retrace_mode == "source":
        if 20 <= retrace <= 35:
            s_retr_pos = 8.0
        elif (10 <= retrace < 20) or (35 < retrace <= 45):
            s_retr_pos = 5.0
        elif 45 < retrace <= 61.8:
            # Band unobserved in the source's 108 records (no name fell there), so its
            # score is not readable off the data; scored as the adjacent 35~45 tier.
            s_retr_pos = 5.0
        else:
            s_retr_pos = 0.0
    else:
        # Fibonacci analogue of the same shape: the classic 38.2~50 zone is the ideal one.
        if 38.2 <= retrace <= 50:
            s_retr_pos = 8.0
        elif FIB_LO <= retrace <= FIB_HI:
            s_retr_pos = 5.0
        else:
            s_retr_pos = 0.0

    pb = bars[imp["peak_index"] + 1:i + 1]
    if pb and imp_vol > 0:
        vr = (sum(b["v"] for b in pb) / len(pb)) / imp_vol * 100
        s_vol_dry = _band(vr, [(40, 10.0), (60, 10.0), (80, 7.0), (100, 3.0), (None, 0.0)])
    else:
        vr, s_vol_dry = None, 0.0

    atrp = [x for x in atr_pct_full[:i + 1] if x is not None]
    s_vc = 0.0
    if len(atrp) >= 40:
        r20, p20, r10 = sum(atrp[-20:]) / 20, sum(atrp[-40:-20]) / 20, sum(atrp[-10:]) / 10
        s_vc += 4.0 if r20 < p20 else 0.0
        s_vc += 3.0 if r10 < r20 else 0.0
    piv = _swings(bars, i, atr_pct_full)
    depths = []
    for a, b in zip(piv, piv[1:]):
        if a[2] == "H" and b[2] == "L" and a[1] > 0:
            depths.append((a[1] - b[1]) / a[1] * 100)
    if depths and dd_from_peak < depths[-1]:
        s_vc += 3.0

    closes = [b["c"] for b in bars[:i + 1]]
    rsi = _rsi(closes)
    if rsi is None:
        s_rsi = 0.0
    else:
        s_rsi = _band(rsi, [(30, 0.0), (35, 8.0), (45, 10.0), (55, 6.0), (65, 3.0), (None, 1.0)])
        if 30 <= rsi < 55:
            prev = _rsi(closes[:-1])
            if prev is not None:
                s_rsi += 1.0 if rsi > prev else -1.0
        s_rsi = max(0.0, min(10.0, s_rsi))

    hi, lo = bars[i]["h"], bars[i]["l"]
    pos = (close - lo) / (hi - lo) if hi > lo else 0.0
    s_rev = _band(pos, [(0.3, 0.0), (0.5, 2.0), (0.7, 5.0), (None, 8.0)])

    entry = s_support_dist + s_retr_pos + s_vol_dry + s_vc + s_rsi + s_rev
    return {
        "date": bars[i]["date"], "impulse_mode": impulse_mode, "retrace_mode": retrace_mode,
        "setup_score": float(setup), "entry_score": float(entry),
        "total": float(setup + entry), "setup_qualified": bool(qualified),
        "impulse": imp, "retrace_pct": retrace, "fib_retrace_pct": fib_retrace,
        "drawdown_from_peak_pct": dd_from_peak, "days_since_peak": days_since_peak,
        "rsi": rsi, "volume_dry_up_pct": vr,
        "components": {"support_distance": s_support_dist, "retrace_position": s_retr_pos,
                       "volume_dry_up": s_vol_dry, "volatility_contraction": s_vc,
                       "rsi": s_rsi, "reversal_candle": s_rev},
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--price", required=True)
    ap.add_argument("--impulse-mode", default="window", choices=["window", "zigzag"])
    ap.add_argument("--retrace-mode", default="source", choices=["source", "fib"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    bars = sorted(json.load(open(a.price))["daily"], key=lambda b: b["date"])
    r = score_at(bars, len(bars) - 1, a.impulse_mode, a.retrace_mode)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if a.out:
        json.dump(r, open(a.out, "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
