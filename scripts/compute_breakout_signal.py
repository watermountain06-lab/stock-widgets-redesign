#!/usr/bin/env python3
"""돌파신호 v1 (연구용 후보 탐지 규칙) — fetch_price.py 출력에서 "오늘 기준
활성 돌파 배지"를 계산. compute_technical_score.py와 동일한 CLI 컨벤션.

status: candidate detection rule, NOT a validated trading strategy.
자세한 근거/한계는 breakout_config_v1.json의 backtest_evidence 참고.
신호는 "신호일 종가" 기준이며 실전 최초 진입 가능 시점은 다음 거래일 시가.
"""
import argparse
import json
import sys
from pathlib import Path

from breakout_signal import detect_simple_breakouts, check_vcp, atr_series

DEFAULT_CONFIG_PATH = Path(__file__).parent / "breakout_config_v1.json"


def compute_active_breakout(ticker, price_data, config):
    bars = price_data["daily"]
    n = len(bars)
    as_of = bars[-1]["date"]

    result = {
        "ticker": ticker, "asOf": as_of, "close": bars[-1]["c"],
        "modelVersion": config["version"], "modelFrozenDate": config["frozen_date"],
        "status": config["status"],
        "entryBasisNote": "신호는 신호일 종가 기준으로 판정됨; 실전 최초 진입 가능 시점은 다음 거래일 시가(과거 검증: 갭 평균+0.26%, 결론을 바꿀 수준은 아님)",
    }

    sb = config["simple_breakout"]
    events = detect_simple_breakouts(
        bars, pivot_window=sb["pivot_window_days"], vol_window=sb["volume_avg_window_days"],
        confirm_margin=sb["confirm_margin"], vol_ratio_min=sb["volume_ratio_min"],
        dedup_gap=sb["dedup_gap_days"],
    )

    if not events:
        result["activeBreakout"] = None
        return result

    last = events[-1]
    days_ago = (n - 1) - last["idx"]
    hold = sb["badge_max_hold_days"]

    if days_ago > hold:
        result["activeBreakout"] = None
        return result

    # 조기 종료 조건: 신호일 이후 종가가 pivot*(1-0.02) 아래로, 또는 2일 연속 pivot 하회
    pivot = last["pivot60"]
    below_streak = 0
    early_exit = False
    for b in bars[last["idx"] + 1: n]:
        if b["c"] < pivot * (1 - sb["badge_early_exit_close_below_pivot_pct"]):
            early_exit = True
            break
        if b["c"] < pivot:
            below_streak += 1
            if below_streak >= sb["badge_early_exit_consecutive_days_below_pivot"]:
                early_exit = True
                break
        else:
            below_streak = 0

    if early_exit:
        result["activeBreakout"] = None
        return result

    atr20 = atr_series(bars, period=20)
    closes = [b["c"] for b in bars]
    atr_pct_full = [None] + [(a / closes[i + 1] if a is not None else None) for i, a in enumerate(atr20)]
    vcp = check_vcp(bars, last["idx"], atr_pct_full)

    result["activeBreakout"] = {
        "eventDate": last["date"], "daysAgo": days_ago, "grade": last["grade"],
        "volumeRatio": last["volume_ratio"], "new52wHigh": last["new_52w_high"],
        "pivot60": round(pivot, 2), "vcpStatus": vcp["status"],
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--price", required=True, help="fetch_price.py --range 5y (or 2y+) output")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.price) as f:
        price_data = json.load(f)
    with open(args.config) as f:
        config = json.load(f)

    result = compute_active_breakout(args.ticker.upper(), price_data, config)

    out_path = args.out or f"{args.ticker.upper()}_breakout_signal.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    ab = result.get("activeBreakout")
    print(f"Wrote {out_path} - activeBreakout={'없음' if ab is None else ab['grade']+' ('+str(ab['daysAgo'])+'일전)'}")


if __name__ == "__main__":
    main()
