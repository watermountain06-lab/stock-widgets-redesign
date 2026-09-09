#!/usr/bin/env python3
"""VCP 판정이 어느 조건에서 대부분 탈락하는지 진단."""
import json
import statistics
from collections import defaultdict
from pathlib import Path

from breakout_signal import detect_simple_breakouts, atr_series, zigzag_swings, contractions_from_swings

DATA = Path(__file__).parent.parent / "data" / "raw_5y"
TICKERS = sorted(p.stem for p in DATA.glob("*.json") if p.stem != "SPY")


def load(t):
    return json.load(open(DATA / f"{t}.json"))["daily"]


fail_reasons = defaultdict(int)
leg_count_hist = defaultdict(int)
depth_samples = []

for t in TICKERS:
    bars = load(t)
    if len(bars) < 300:
        continue
    closes = [b["c"] for b in bars]
    vols = [b["v"] for b in bars]
    atr20 = atr_series(bars, period=20)
    atr_pct_full = [None] + [(a / closes[i + 1] if a is not None else None) for i, a in enumerate(atr20)]

    events = detect_simple_breakouts(bars)
    for ev in events:
        idx = ev["idx"]
        best_legs = 0
        reason = "no_valid_base_len"
        for base_len in range(65, 24, -5):
            start = idx - base_len
            if start < 0:
                continue
            swings = zigzag_swings(bars, atr_pct_full, start, idx)
            legs = contractions_from_swings(swings)
            best_legs = max(best_legs, len(legs))
            if len(legs) < 2:
                continue
            recent = legs[-5:]
            depths = [l["depth"] for l in recent]
            depth_samples.extend(depths)

            if not (0.02 <= depths[-1] <= 0.10):
                reason = "final_depth_out_of_range"; continue
            if not all(0.02 <= d <= 0.35 for d in depths):
                reason = "some_depth_out_of_2_35_range"; continue
            if not (depths[0] > depths[-1] and depths[-1] <= depths[0] * 0.60):
                reason = "not_shrinking_enough_first_vs_last"; continue
            one_shrink = any(depths[k+1] <= depths[k]*0.90 for k in range(len(depths)-1))
            no_blowup = all(depths[k+1] <= depths[k]*1.15 for k in range(len(depths)-1))
            if not (one_shrink and no_blowup):
                reason = "shrink_or_blowup_check_failed"; continue
            troughs = [l["trough_price"] for l in recent]
            if not all(troughs[k+1] >= troughs[k]*0.97 for k in range(len(troughs)-1)):
                reason = "trough_deteriorating"; continue
            peaks = [l["peak_price"] for l in recent]
            if not (peaks[-1] >= max(peaks)*0.97):
                reason = "pivot_too_far_below_base_high"; continue
            vol_avg50 = sum(vols[idx-50:idx])/50
            last_leg = recent[-1]
            leg_vol = statistics.median(vols[last_leg["peak_idx"]:last_leg["trough_idx"]+1] or [0])
            fvr = leg_vol/vol_avg50 if vol_avg50>0 else None
            if fvr is None or fvr > 0.70:
                reason = "final_leg_volume_not_dry"; continue
            reason = "PASSED"
            break
        leg_count_hist[best_legs] += 1
        fail_reasons[reason] += 1

print("=== 이벤트별 '최고 leg 개수'(가장 legs 많이 나온 base_len 기준) 분포 ===")
for k in sorted(leg_count_hist):
    print(f"  legs={k}: {leg_count_hist[k]}건")

print("\n=== 탈락 사유별 이벤트 수 (첫 번째 시도한 base_len에서 결정, 순서대로 시도) ===")
for reason, cnt in sorted(fail_reasons.items(), key=lambda x: -x[1]):
    print(f"  {reason}: {cnt}건")

print(f"\n=== 전체 contraction depth 분포 (n={len(depth_samples)}) ===")
if depth_samples:
    ds = sorted(depth_samples)
    print(f"  mean={statistics.mean(ds)*100:.1f}% median={statistics.median(ds)*100:.1f}% "
          f"min={ds[0]*100:.1f}% max={ds[-1]*100:.1f}%")
    print(f"  quantiles(10/25/50/75/90%): "
          f"{[round(ds[int(len(ds)*q)]*100,1) for q in (0.1,0.25,0.5,0.75,0.9)]}")
