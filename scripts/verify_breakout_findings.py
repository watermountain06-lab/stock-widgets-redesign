#!/usr/bin/env python3
"""단순형 돌파신호 결과 검증 — 벤치마크 대비 초과수익률 + 종목단위 군집부트스트랩 CI
+ 국면별 이벤트 '빈도' 정규화(품질 vs 빈도 분리).
backtest_breakouts.py의 이벤트 생성 로직을 재사용(중복 최소화 위해 재계산)."""
import bisect
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

from breakout_signal import detect_simple_breakouts, atr_series, sma

DATA = Path(__file__).parent.parent / "data" / "raw_5y"
TICKERS = sorted(p.stem for p in DATA.glob("*.json") if p.stem != "SPY")


def load(t):
    return json.load(open(DATA / f"{t}.json"))["daily"]


spy_bars = load("SPY")
spy_closes = [b["c"] for b in spy_bars]
spy_dates = [b["date"] for b in spy_bars]


def spy_idx_at(date):
    pos = bisect.bisect_right(spy_dates, date) - 1
    return pos if pos >= 0 else None


def regime_at(date):
    pos = spy_idx_at(date)
    if pos is None or pos < 63:
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


# ---- 1. 이벤트 재생성 (+ SPY 상대 초과수익률 추가) ----
all_events = []
for t in TICKERS:
    bars = load(t)
    if len(bars) < 300:
        continue
    closes = [b["c"] for b in bars]
    events = detect_simple_breakouts(bars)
    for ev in events:
        idx = ev["idx"]
        entry = closes[idx]
        n = len(bars)
        si = spy_idx_at(ev["date"])

        def excess(days):
            if idx + days >= n or si is None or si + days >= len(spy_closes):
                return None
            stock_ret = closes[idx + days] / entry - 1
            spy_ret = spy_closes[si + days] / spy_closes[si] - 1
            return stock_ret - spy_ret

        all_events.append(dict(
            ticker=t, idx=idx, date=ev["date"], close=entry,
            regime=regime_at(ev["date"]), stage2=stage2_at(closes, idx),
            fwd_20d=(closes[idx + 20] / entry - 1) if idx + 20 < n else None,
            fwd_60d=(closes[idx + 60] / entry - 1) if idx + 60 < n else None,
            excess_20d=excess(20), excess_60d=excess(60),
        ))
        # success_20d: MFE-based (max high in next 20d hits +5%)
        if idx + 20 < n:
            mfe20 = max(b["h"] for b in bars[idx + 1:idx + 21]) / entry - 1
            all_events[-1]["success_20d"] = mfe20 >= 0.05
            below = 0
            fail = False
            for b in bars[idx + 1:idx + 11] if idx + 10 < n else []:
                if b["c"] < ev["pivot60"]:
                    below += 1
                    if below >= 2:
                        fail = True
                        break
                else:
                    below = 0
            all_events[-1]["structural_fail_10d"] = fail if idx + 10 < n else None
        else:
            all_events[-1]["success_20d"] = None
            all_events[-1]["structural_fail_10d"] = None

print(f"총 이벤트: {len(all_events)}건\n")

# ---- 2. 벤치마크 대비 초과수익률 ----
print("=== 절대수익률 vs SPY 대비 초과수익률 ===")
def dist(key, events=all_events):
    vals = [e[key] for e in events if e.get(key) is not None]
    if not vals:
        return "n/a"
    return f"mean={statistics.mean(vals)*100:+.2f}% median={statistics.median(vals)*100:+.2f}% (n={len(vals)})"

print(f"20일 절대수익률: {dist('fwd_20d')}")
print(f"20일 SPY대비 초과수익률: {dist('excess_20d')}")
print(f"60일 절대수익률: {dist('fwd_60d')}")
print(f"60일 SPY대비 초과수익률: {dist('excess_60d')}")

print("\n국면별 20일 초과수익률:")
for reg in ["상승장", "횡보장", "하락장"]:
    sub = [e for e in all_events if e["regime"] == reg]
    print(f"  {reg} (n={len(sub)}): {dist('excess_20d', sub)}")


# ---- 3. 종목단위 군집 부트스트랩 CI ----
print("\n=== 종목단위 군집 부트스트랩 95% CI (2000회 리샘플, 종목 단위로 통째로 재추출) ===")
by_ticker = defaultdict(list)
for e in all_events:
    by_ticker[e["ticker"]].append(e)
ticker_list = list(by_ticker.keys())

random.seed(42)

def cluster_bootstrap_rate(key, n_boot=2000):
    point_vals = [e[key] for e in all_events if e.get(key) is not None]
    point = sum(1 for v in point_vals if v) / len(point_vals)
    boot_rates = []
    for _ in range(n_boot):
        resampled_tickers = [random.choice(ticker_list) for _ in ticker_list]
        vals = []
        for t in resampled_tickers:
            vals.extend(e[key] for e in by_ticker[t] if e.get(key) is not None)
        if vals:
            boot_rates.append(sum(1 for v in vals if v) / len(vals))
    boot_rates.sort()
    lo = boot_rates[int(len(boot_rates) * 0.025)]
    hi = boot_rates[int(len(boot_rates) * 0.975)]
    return point, lo, hi

for key, label in [("success_20d", "성공률(20일 MFE +5%)"), ("structural_fail_10d", "구조적 가짜돌파율")]:
    point, lo, hi = cluster_bootstrap_rate(key)
    naive_n = sum(1 for e in all_events if e.get(key) is not None)
    naive_se = (point * (1 - point) / naive_n) ** 0.5
    print(f"{label}: 점추정 {point*100:.1f}%  |  단순CI(비군집) [{(point-1.96*naive_se)*100:.1f}%, {(point+1.96*naive_se)*100:.1f}%]  |  종목군집부트스트랩CI [{lo*100:.1f}%, {hi*100:.1f}%]")


def cluster_bootstrap_mean(key, n_boot=2000):
    point_vals = [e[key] for e in all_events if e.get(key) is not None]
    point = statistics.mean(point_vals)
    boot_means = []
    for _ in range(n_boot):
        resampled_tickers = [random.choice(ticker_list) for _ in ticker_list]
        vals = []
        for t in resampled_tickers:
            vals.extend(e[key] for e in by_ticker[t] if e.get(key) is not None)
        if vals:
            boot_means.append(statistics.mean(vals))
    boot_means.sort()
    lo = boot_means[int(len(boot_means) * 0.025)]
    hi = boot_means[int(len(boot_means) * 0.975)]
    return point, lo, hi

for key, label in [("excess_20d", "20일 초과수익률 평균"), ("excess_60d", "60일 초과수익률 평균")]:
    point, lo, hi = cluster_bootstrap_mean(key)
    print(f"{label}: 점추정 {point*100:+.2f}%  |  종목군집부트스트랩CI [{lo*100:+.2f}%, {hi*100:+.2f}%]")

# ---- 4. 국면별 이벤트 '빈도' 정규화 — 품질 vs 빈도 분리 ----
print("\n=== 국면별 이벤트 발생 '빈도' 정규화 (사용자 가설: 상승장엔 돌파가 흔해서 덜 의미있는가?) ===")
regime_days = defaultdict(int)
for d in spy_dates:
    regime_days[regime_at(d)] += 1
print(f"5년 전체 거래일 중 국면별 일수: {dict(regime_days)}")

regime_event_counts = defaultdict(int)
for e in all_events:
    regime_event_counts[e["regime"]] += 1

print("\n국면별 '종목-거래일당 이벤트 발생률' (이벤트수 / (국면일수 x 45종목) x 10000, 만분율):")
for reg in ["상승장", "횡보장", "하락장"]:
    exposure = regime_days[reg] * 45
    rate = regime_event_counts[reg] / exposure * 10000 if exposure else 0
    print(f"  {reg}: 이벤트 {regime_event_counts[reg]}건 / 노출(거래일x종목) {exposure} = {rate:.2f} (만분율)")
