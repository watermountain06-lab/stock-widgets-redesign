#!/usr/bin/env python3
"""돌파신호 이벤트 기반 백테스트 — 단순형 vs VCP필터 비교.
47종목(SKHY/SPCX 제외 45종목) x 5년 실데이터. 월말 패널과 별개로
이벤트(돌파일) 단위 분석: 5/20/60일 후행수익률, MFE/MAE, 가짜돌파율, 성공률.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

from breakout_signal import detect_simple_breakouts, check_vcp, atr_series, sma

DATA = Path(__file__).parent.parent / "data" / "raw_5y"
TICKERS = sorted(p.stem for p in DATA.glob("*.json") if p.stem != "SPY")


def load(t):
    return json.load(open(DATA / f"{t}.json"))["daily"]


spy_bars = load("SPY")
spy_closes = [b["c"] for b in spy_bars]
spy_dates = [b["date"] for b in spy_bars]
spy_date_idx = {d: i for i, d in enumerate(spy_dates)}


def regime_at(date):
    import bisect
    pos = bisect.bisect_right(spy_dates, date) - 1
    if pos < 63:
        return "unknown"
    r63 = spy_closes[pos] / spy_closes[pos - 63] - 1
    if r63 > 0.05:
        return "상승장"
    if r63 < -0.05:
        return "하락장"
    return "횡보장"


def stage2_at(closes, i):
    ma150, ma200 = sma(closes, 150, i + 1), sma(closes, 200, i + 1)
    if ma150 is None or ma200 is None:
        return None
    return closes[i] > ma150 and closes[i] > ma200 and ma150 > ma200


def forward_stats(bars, closes, idx, pivot60):
    n = len(bars)
    entry = closes[idx]
    fwd = {}
    for label, d in (("5d", 5), ("20d", 20), ("60d", 60)):
        fwd[label] = (closes[idx + d] / entry - 1) if idx + d < n else None

    mfe20 = mae20 = None
    if idx + 20 < n:
        window = bars[idx + 1:idx + 21]
        mfe20 = max(b["h"] for b in window) / entry - 1
        mae20 = min(b["l"] for b in window) / entry - 1

    structural_fail = None
    if idx + 10 < n:
        below_streak = 0
        structural_fail = False
        for b in bars[idx + 1:idx + 11]:
            if b["c"] < pivot60:
                below_streak += 1
                if below_streak >= 2:
                    structural_fail = True
                    break
            else:
                below_streak = 0

    economic_fail = None
    if idx + 20 < n:
        economic_fail = False
        for b in bars[idx + 1:idx + 21]:
            hit_down = b["l"] / entry - 1 <= -0.05
            hit_up = b["h"] / entry - 1 >= 0.05
            # same-day both-hit is ambiguous from daily OHLC alone; treat as
            # "up hit first" (conservative, doesn't mark as failure)
            if hit_up:
                break
            if hit_down:
                economic_fail = True
                break

    success20 = fwd["20d"] is not None and (max(b["h"] for b in bars[idx + 1:idx + 21]) / entry - 1 >= 0.05) if idx + 20 < n else None
    success60_10 = None
    if idx + 60 < n:
        success60_10 = max(b["h"] for b in bars[idx + 1:idx + 61]) / entry - 1 >= 0.10

    return dict(fwd_5d=fwd["5d"], fwd_20d=fwd["20d"], fwd_60d=fwd["60d"],
                mfe_20d=mfe20, mae_20d=mae20,
                structural_fail_10d=structural_fail, economic_fail_20d=economic_fail,
                success_20d=success20, success_60d=success60_10)


all_events = []
for t in TICKERS:
    bars = load(t)
    if len(bars) < 300:
        continue
    closes = [b["c"] for b in bars]
    atr20 = atr_series(bars, period=20)
    atr_pct = [(a / closes[i + 1] if a is not None else None) for i, a in enumerate(atr20)]
    # atr_pct[i] corresponds to bars[i+1]; build a full-length aligned array (index 0 = None)
    atr_pct_full = [None] + atr_pct

    events = detect_simple_breakouts(bars)
    for ev in events:
        idx = ev["idx"]
        vcp = check_vcp(bars, idx, atr_pct_full)
        fstats = forward_stats(bars, closes, idx, ev["pivot60"])
        stg2 = stage2_at(closes, idx)
        all_events.append(dict(
            ticker=t, **ev, vcp_status=vcp["status"], vcp_contractions=vcp["contractions"],
            stage2=stg2, regime=regime_at(ev["date"]), **fstats,
        ))

print(f"=== 전체 단순형 돌파 이벤트: {len(all_events)}건 (45종목, 5년) ===")
print(f"종목당 연간 평균: {len(all_events) / 45 / 5:.2f}건")
tickers_with_event = len(set(e["ticker"] for e in all_events))
print(f"최소 1회 신호 발생 종목: {tickers_with_event}/45")

vcp_confirmed = [e for e in all_events if e["vcp_status"] == "confirmed"]
vcp_candidate = [e for e in all_events if e["vcp_status"] == "candidate"]
print(f"\nVCP 확인(confirmed): {len(vcp_confirmed)}건 / VCP 후보(candidate): {len(vcp_candidate)}건 / VCP 미해당: {len(all_events) - len(vcp_confirmed) - len(vcp_candidate)}건")


def summarize(events, label):
    n = len(events)
    if n == 0:
        print(f"{label}: n=0")
        return
    def dist(key):
        vals = [e[key] for e in events if e.get(key) is not None]
        if not vals:
            return "n/a"
        return f"mean={statistics.mean(vals)*100:.2f}% median={statistics.median(vals)*100:.2f}% (n={len(vals)})"
    def rate(key):
        vals = [e[key] for e in events if e.get(key) is not None]
        if not vals:
            return "n/a"
        return f"{sum(1 for v in vals if v)/len(vals)*100:.1f}% (n={len(vals)})"

    print(f"\n--- {label} (n={n}) ---")
    print(f"  fwd_5d:  {dist('fwd_5d')}")
    print(f"  fwd_20d: {dist('fwd_20d')}")
    print(f"  fwd_60d: {dist('fwd_60d')}")
    print(f"  MFE_20d: {dist('mfe_20d')}   MAE_20d: {dist('mae_20d')}")
    print(f"  구조적 가짜돌파율(10일내 pivot 2일연속 하회): {rate('structural_fail_10d')}")
    print(f"  경제적 가짜돌파율(20일내 -5%가 +5%보다 먼저): {rate('economic_fail_20d')}")
    print(f"  성공률(20일내 +5% 도달): {rate('success_20d')}")
    print(f"  성공률(60일내 +10% 도달): {rate('success_60d')}")

print("\n" + "=" * 70)
print("비교 1: 전체 단순형 vs VCP확인(부분집합)")
summarize(all_events, "전체 단순형 돌파")
summarize(vcp_confirmed, "VCP 확인(confirmed) 부분집합")
summarize(vcp_candidate, "VCP 후보(candidate) 부분집합")

print("\n" + "=" * 70)
print("비교 2: Stage2 조건 내에서 단순형 vs VCP확인")
stage2_events = [e for e in all_events if e["stage2"]]
stage2_vcp = [e for e in stage2_events if e["vcp_status"] == "confirmed"]
summarize(stage2_events, "Stage2 단순형 돌파")
summarize(stage2_vcp, "Stage2 + VCP확인")

print("\n" + "=" * 70)
print("국면별 분포 (전체 단순형)")
regime_counts = defaultdict(int)
for e in all_events:
    regime_counts[e["regime"]] += 1
print(dict(regime_counts))
for reg in ["상승장", "횡보장", "하락장"]:
    sub = [e for e in all_events if e["regime"] == reg]
    summarize(sub, f"국면={reg} 전체단순형")
    sub_vcp = [e for e in sub if e["vcp_status"] == "confirmed"]
    summarize(sub_vcp, f"국면={reg} VCP확인")

print("\n" + "=" * 70)
print("종목 단위 재표집 체크: 이벤트가 소수 종목에 몰려있는지")
by_ticker_count = defaultdict(int)
for e in all_events:
    by_ticker_count[e["ticker"]] += 1
top5 = sorted(by_ticker_count.items(), key=lambda x: -x[1])[:5]
print("이벤트 최다 종목 top5:", top5, " / 전체 대비 비중:",
      f"{sum(c for _,c in top5)/len(all_events)*100:.1f}%")
