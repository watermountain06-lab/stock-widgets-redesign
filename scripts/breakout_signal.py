#!/usr/bin/env python3
"""돌파신호 v1 (실험) — 단순형 + VCP형(품질 필터).

스펙 출처: Codex 검증 라운드(2026-08-18), tech_score와 별개로 총점 100점 밖의
"기회 배지"로만 사용한다 (compute_technical_score.py의 rawScore/displayGrade에
편입하지 않음).

단순형:
  pivot_60  = max(High[t-60:t-1])   (오늘 제외)
  breakout  = Close[t] >= pivot_60 * 1.005
  volume_ratio = Volume[t] / mean(Volume[t-50:t-1])
  confirmed = breakout and volume_ratio >= 1.50

VCP형 (단순형의 부분집합 필터):
  적응형 ATR zigzag로 스윙(고점/저점) 탐지 -> peak->trough를 contraction으로 정의
  -> 최근 contraction들이 순차적으로 얕아지는지, 저점이 무너지지 않는지,
     거래량이 마르는지 확인.
"""
import statistics


def true_range_series(bars):
    """bars[1:]에 대응하는 True Range 리스트."""
    tr = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return tr


def atr_series(bars, period=20):
    """bars[1:]에 대응하는 단순이동평균 ATR (Wilder 평활화 아님, RSI/ATR14와 동일 관례)."""
    tr = true_range_series(bars)
    out = []
    for i in range(len(tr)):
        if i + 1 < period:
            out.append(None)
            continue
        out.append(sum(tr[i + 1 - period:i + 1]) / period)
    return out  # out[i] corresponds to bars[i+1]


def sma(closes, n, end):
    w = closes[end - n:end]
    return sum(w) / n if len(w) == n else None


# ---------------------------------------------------------------- 단순형 ----

def detect_simple_breakouts(bars, pivot_window=60, vol_window=50,
                             confirm_margin=0.005, vol_ratio_min=1.50,
                             dedup_gap=10):
    """전체 bars를 스캔해서 확인된(volume_ratio>=1.5) 단순형 돌파 이벤트 리스트 반환.
    각 이벤트: {idx, date, close, pivot60, pivot252, volume_ratio, new_52w_high}
    중복(같은 저항선 위에서 dedup_gap 거래일 이내 재발)은 제거."""
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    vols = [b["v"] for b in bars]
    events = []
    last_event_idx = -10**9
    for i in range(max(pivot_window, vol_window), len(bars)):
        if i - last_event_idx < dedup_gap:
            continue
        pivot60 = max(highs[i - pivot_window:i])
        pivot252 = max(highs[max(0, i - 252):i]) if i >= 252 else None
        vol_avg = sum(vols[i - vol_window:i]) / vol_window
        if vol_avg <= 0:
            continue
        vol_ratio = vols[i] / vol_avg
        breakout = closes[i] >= pivot60 * (1 + confirm_margin)
        if breakout and vol_ratio >= vol_ratio_min:
            new_52w = pivot252 is not None and closes[i] >= pivot252 * 0.995
            grade = "강한돌파" if vol_ratio >= 2.0 else "확인돌파"
            events.append(dict(
                idx=i, date=bars[i]["date"], close=closes[i],
                pivot60=pivot60, pivot252=pivot252,
                volume_ratio=round(vol_ratio, 2),
                new_52w_high=new_52w, grade=grade,
            ))
            last_event_idx = i
    return events


# -------------------------------------------------------------- VCP형 ------

def zigzag_swings(bars, atr_pct, start_idx, end_idx,
                   min_pct=0.03, atr_mult=1.25,
                   min_leg_days=3, min_peak_gap_days=5):
    """bars[start_idx:end_idx] 구간에서 적응형 ATR zigzag 스윙 탐지.
    반환: [{"type": "peak"|"trough", "idx": i, "price": v}, ...] (시간순)."""
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]

    def threshold(i):
        a = atr_pct[i] if i < len(atr_pct) and atr_pct[i] is not None else None
        base = atr_mult * a if a is not None else 0
        return max(min_pct, base)

    if end_idx - start_idx < min_leg_days * 2:
        return []

    direction = None
    candidate_high_idx = start_idx
    candidate_low_idx = start_idx
    swings = []

    i = start_idx
    # 초기 방향 결정: 첫 임계값 이상 움직임의 방향
    while i < end_idx and direction is None:
        ref = closes[start_idx]
        if closes[i] <= ref * (1 - threshold(i)):
            direction = "down"
            candidate_low_idx = i
        elif closes[i] >= ref * (1 + threshold(i)):
            direction = "up"
            candidate_high_idx = i
        i += 1
    if direction is None:
        return []

    for j in range(i, end_idx):
        if direction == "up":
            if highs[j] > highs[candidate_high_idx]:
                candidate_high_idx = j
            if closes[j] <= highs[candidate_high_idx] * (1 - threshold(j)):
                if j - candidate_high_idx >= min_leg_days or not swings:
                    swings.append({"type": "peak", "idx": candidate_high_idx,
                                    "price": highs[candidate_high_idx]})
                    direction = "down"
                    candidate_low_idx = j
        else:
            if lows[j] < lows[candidate_low_idx]:
                candidate_low_idx = j
            if closes[j] >= lows[candidate_low_idx] * (1 + threshold(j)):
                if j - candidate_low_idx >= min_leg_days or not swings:
                    swings.append({"type": "trough", "idx": candidate_low_idx,
                                    "price": lows[candidate_low_idx]})
                    direction = "up"
                    candidate_high_idx = j

    # 인접 동일유형 극점 중 너무 가까우면(min_peak_gap_days) 더 극단적인 것만 유지
    cleaned = []
    for s in swings:
        if cleaned and cleaned[-1]["type"] == s["type"] and s["idx"] - cleaned[-1]["idx"] < min_peak_gap_days:
            keep_new = (s["price"] > cleaned[-1]["price"]) if s["type"] == "peak" else (s["price"] < cleaned[-1]["price"])
            if keep_new:
                cleaned[-1] = s
        else:
            cleaned.append(s)
    return cleaned


def contractions_from_swings(swings):
    """Peak->Trough 쌍을 contraction으로. depth = (peak-trough)/peak."""
    legs = []
    for a, b in zip(swings, swings[1:]):
        if a["type"] == "peak" and b["type"] == "trough":
            depth = (a["price"] - b["price"]) / a["price"]
            legs.append(dict(peak_idx=a["idx"], peak_price=a["price"],
                              trough_idx=b["idx"], trough_price=b["price"],
                              depth=depth))
    return legs


def check_vcp(bars, breakout_idx, atr_pct,
              base_min=25, base_max=65, min_contractions=3,
              final_depth_min=0.02, final_depth_max=0.10,
              shrink_ratio=0.90, min_one_shrink=0.90,
              trough_tolerance=0.97, pivot_tolerance=0.97,
              vol_window=50, final_vol_ratio_max=0.70):
    """breakout_idx 직전 base_min~base_max 거래일을 VCP 베이스 후보로 보고 판정.
    반환: {"status": "none"|"candidate"|"confirmed", "contractions": n, "legs": [...]}"""
    closes = [b["c"] for b in bars]
    vols = [b["v"] for b in bars]
    best = {"status": "none", "contractions": 0, "legs": []}

    for base_len in range(base_max, base_min - 1, -5):
        start = breakout_idx - base_len
        if start < 0:
            continue
        swings = zigzag_swings(bars, atr_pct, start, breakout_idx)
        legs = contractions_from_swings(swings)
        if len(legs) < 2:
            continue
        recent = legs[-5:]
        depths = [l["depth"] for l in recent]

        if not (final_depth_min <= depths[-1] <= final_depth_max):
            continue
        if not all(0.02 <= d <= 0.35 for d in depths):
            continue
        if not (depths[0] > depths[-1] and depths[-1] <= depths[0] * 0.60):
            continue
        one_shrink = any(depths[k + 1] <= depths[k] * shrink_ratio for k in range(len(depths) - 1))
        no_blowup = all(depths[k + 1] <= depths[k] * 1.15 for k in range(len(depths) - 1))
        if not (one_shrink and no_blowup):
            continue

        troughs = [l["trough_price"] for l in recent]
        if not all(troughs[k + 1] >= troughs[k] * trough_tolerance for k in range(len(troughs) - 1)):
            continue

        peaks = [l["peak_price"] for l in recent]
        if not (peaks[-1] >= max(peaks) * pivot_tolerance):
            continue

        vol_avg50 = sum(vols[breakout_idx - vol_window:breakout_idx]) / vol_window
        last_leg = recent[-1]
        leg_vol = statistics.median(vols[last_leg["peak_idx"]:last_leg["trough_idx"] + 1] or [0])
        final_vol_ratio = leg_vol / vol_avg50 if vol_avg50 > 0 else None
        if final_vol_ratio is None or final_vol_ratio > final_vol_ratio_max:
            continue

        status = "confirmed" if len(recent) >= min_contractions else "candidate"
        if status == "confirmed" or best["status"] == "none":
            best = {"status": status, "contractions": len(recent), "legs": recent,
                    "base_len": base_len, "final_vol_ratio": round(final_vol_ratio, 2)}
        if status == "confirmed":
            break
    return best
