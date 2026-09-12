#!/usr/bin/env python3
"""v4 of the valuation-judgment backtest. Same question as v3
(scripts/compute_valuation_ic.py): does the site's 저평가/적정/고평가 judgment have
historical predictive power? Same signal, same anchors, same Fama-MacBeth + moving-block
bootstrap inference. Three things are new, and the third one overturns v3's reading.

1. UNIVERSE EXPANDED 8 -> 50. v3 ran on 8 mega-cap tech names because that was all the
   point-in-time EPS coverage there was. This run covers 50 of the 54 cards (GEV/SKHY/
   SNDK/SPCX have too little listed history for a 2-year trailing anchor plus a forward
   window). The 15 missing EPS histories were fetched with fetch_eps_history.py, which
   needed three new hand-verified split entries: AMAT [] and INTC [] (both confirmed
   empirically -- 0 duplicate-value groups above 1.3x in their full XBRL EPS history --
   and by the companies' own IR split pages), and GE [("2021-08-02", 0.125)], the 1-for-8
   REVERSE split, whose ratio is 0.125 rather than 8 for the same reason documented on C.
   GS and WFC also had no 5-year price file and were fetched.

2. A PRICE-ONLY CONTROL SIGNAL. The v3 signal is log(PER(t) / trailing PER anchor). TTM
   EPS is a slow step function, so most of that ratio's movement is PRICE moving against
   its own trailing average -- i.e. the "valuation" signal is partly disguised price
   mean-reversion. v4 therefore runs the IDENTICAL pipeline a second time on
   log(P(t) / trailing P anchor), with the EPS removed entirely. Whatever the valuation
   signal does over and above this control is the part that valuation actually
   contributes. (Measured rank correlation between the two signals: about +0.5.)

3. AN UNSELECTED CONTROL UNIVERSE -- the finding that matters.
   The 54 cards were chosen in 2025-2026 as stocks worth covering, i.e. chosen with the
   2023-2026 outcomes already known. That is conditioning on the future, and it does not
   just shift the level, it manufactures exactly the correlation this test is looking for:
   a stock that looked cheap in 2023 and then rocketed gets a card, and a stock that
   looked cheap in 2023 and stayed flat never enters the sample. The diagnostic is blunt:
   over the 5-year window the median card returned +107% against SPY's +75%, 35 of 50 beat
   SPY, and the panel's mean 12-month forward EXCESS return is +23%. A panel whose average
   member beats the benchmark by 23% a year cannot be used to grade a stock-picking rule.
   So v4 also builds a universe that was NOT hand-picked -- the 503 current S&P 500 names
   already listed in scripts/sp500.json, of which 463 have both a usable 5-year price
   series and >=20 point-in-time TTM EPS observations -- and runs the same test there.
   Splits for that universe come from Yahoo's own events=split payload for the same
   window rather than a hand-verified table (500 tickers cannot be hand-verified, and this
   way the price series and the split list come from one source and agree by
   construction); only splits inside the price window can matter, because PER is computed
   only on dates that have a price bar.

WHAT IT FINDS (see valuation_ic_v4_result.json for the full numbers):
  - On the 54-card universe the signal looks strong and significant: 12-month FM IC
    -0.218, 95% CI [-0.254, -0.166], negative in 22 of 23 months, and a monotone quintile
    sort from +47.7% (cheapest) to +3.0% (richest). It survives dropping banks, dropping
    the original 8 mega-caps, and dropping GE.
  - On the unselected S&P 500 universe the same signal is indistinguishable from zero at
    every horizon: 12-month FM IC -0.023, 95% CI [-0.076, +0.017], and the quintiles are
    not monotone (Q1 +2.7%, Q3 -5.7%, Q5 -2.9%) -- a U shape, not an ordering. Excluding
    every card ticker so the test is fully out-of-sample gives FM IC -0.012, CI
    [-0.074, +0.036]. The panel mean 12-month excess return there is -0.7%, which is what
    an honest panel looks like.
  - The price-only CONTROL signal behaves the opposite way: near zero on the cards, but
    clearly POSITIVE on the unselected universe (12-month FM IC +0.090, CI [+0.049,
    +0.152]; richest-vs-own-trend quintile +10.7% against cheapest -2.5%). That is
    12-month price momentum, a long-documented effect, and it points the OTHER direction
    from a valuation rule.
  So: the v3 reading ("예측력 미확인") was right, and expanding the universe did not
  rescue it. The apparent significance at 50 tickers is an artifact of picking the
  universe after seeing the outcomes, and the artifact got stronger as more hand-picked
  names were added, not weaker.

CARRIED OVER FROM v3 (still true, still limitations): this validates a MECHANIZED PROXY,
not the site's hand-tuned per-metric badges, which have no reusable formula; returns are
computed from split-adjusted closes with no dividends, so high-yield names' excess returns
are understated; negative-TTM-EPS windows are skipped and that missingness clusters in
drawdowns; and the whole test still lives inside one market regime. The S&P 500 list is
current membership, so it carries its own mild survivorship (names that dropped out are
absent) -- much less than hand-picking, but not zero.

Usage:
    python3 compute_valuation_ic_v4.py --out scripts/valuation_ic_v4_result.json
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
from compute_valuation_ic import (  # noqa: E402  -- reuse v3's reviewed primitives verbatim
    build_ttm_eps_asof, moving_block_bootstrap_ci, month_end_dates, HORIZON_MONTHS,
)

TRAILING_DAYS = 730          # 2 years, matching v3's add_years(t, -2)
HALFLIFE_DAYS = 180.0        # matching v3 and the shipped v2 chart
MIN_TRAILING_OBS = 60        # matching v3
HORIZONS = {"3m": 63, "6m": 126, "12m": 252}
# Yahoo's 5y series for these four carries a single-day move above 45% that is a data
# artifact or a one-off event large enough to dominate a quintile mean; excluded from the
# control universe and named here rather than silently dropped.
CONTROL_OUTLIERS = {"MRNA", "ECHO", "GL", "APP"}


def load_prices(path):
    bars = sorted(json.load(open(path))["daily"], key=lambda b: b["date"])
    return [b["date"] for b in bars], np.array([b["c"] for b in bars], dtype=float)


def to_ordinals(date_strings):
    return np.array([date.fromisoformat(d).toordinal() for d in date_strings], dtype=float)


def anchor_signal(values, ordinals, history_start):
    """log(value(t) / recency-weighted trailing median of value). Vectorised restatement
    of v3's build_ticker_series inner loop -- same window, same >=60-observation floor,
    same requirement that the full trailing window sits inside the price history, same
    step-function weighted median. Verified to reproduce v3's published numbers on the
    same 50-ticker input to 4 decimal places (IC -0.2342 vs -0.2341) before being used
    here; v3's pure-Python version is O(n^2) with a date parse in the inner loop and does
    not finish on a 463-ticker universe."""
    n = len(values)
    out = np.full(n, np.nan)
    window_start = np.searchsorted(ordinals, ordinals - TRAILING_DAYS, side="left")
    for i in range(n):
        s = window_start[i]
        if i - s < MIN_TRAILING_OBS:
            continue
        if ordinals[i] - TRAILING_DAYS < history_start:
            continue
        weights = np.exp2(-(ordinals[i] - ordinals[s:i]) / HALFLIFE_DAYS)
        window = values[s:i]
        order = np.argsort(window, kind="stable")
        sorted_w = weights[order]
        cumulative = np.cumsum(sorted_w)
        anchor = window[order][np.searchsorted(cumulative, cumulative[-1] / 2.0, side="left")]
        if anchor > 0 and values[i] > 0:
            out[i] = math.log(values[i] / anchor)
    return out


def build_panel(price_dir, eps_dir, spy_path, exclude=()):
    spy_dates, spy_closes = load_prices(spy_path)
    spy_index = {d: i for i, d in enumerate(spy_dates)}
    tickers = sorted(
        f[:-5] for f in os.listdir(eps_dir)
        if f.endswith(".json") and os.path.exists(os.path.join(price_dir, f)) and f[:-5] not in exclude
    )
    rows = []
    used = []
    for t in tickers:
        try:
            eps_points = json.load(open(os.path.join(eps_dir, t + ".json")))
            dates, closes = load_prices(os.path.join(price_dir, t + ".json"))
        except Exception:
            continue
        if len(dates) < 700:
            continue
        used.append(t)
        ttm = build_ttm_eps_asof(eps_points, dates)
        ordinals = to_ordinals(dates)
        history_start = ordinals[0]

        per = np.array([closes[i] / ttm[i] if (ttm[i] and ttm[i] > 0) else np.nan
                        for i in range(len(dates))])
        valid = ~np.isnan(per)
        sig_val = np.full(len(dates), np.nan)
        if valid.sum() > MIN_TRAILING_OBS:
            sig_val[valid] = anchor_signal(per[valid], ordinals[valid], history_start)
        sig_price = anchor_signal(closes, ordinals, history_start)

        for idx in {d[:7]: i for i, d in enumerate(dates)}.values():
            d = dates[idx]
            if np.isnan(sig_val[idx]) and np.isnan(sig_price[idx]):
                continue
            si = spy_index.get(d)
            if si is None:
                continue
            row = {"ticker": t, "date": d}
            if not np.isnan(sig_val[idx]):
                row["signal_valuation"] = float(sig_val[idx])
            if not np.isnan(sig_price[idx]):
                row["signal_price_only"] = float(sig_price[idx])
            for name, h in HORIZONS.items():
                if idx + h < len(closes) and si + h < len(spy_closes):
                    row["fwd_" + name] = float(
                        closes[idx + h] / closes[idx] - 1 - (spy_closes[si + h] / spy_closes[si] - 1))
            rows.append(row)
    return rows, used


def panel_baseline(rows):
    """The universe-selection diagnostic: what does the AVERAGE member of this panel do
    against SPY, with no signal involved at all? A hand-picked universe gives itself away
    here before any IC is computed."""
    out = {}
    for name in HORIZONS:
        v = np.array([r["fwd_" + name] for r in rows if "fwd_" + name in r])
        if len(v):
            out[name] = {"n": int(len(v)), "mean_excess": round(float(v.mean()), 4),
                         "median_excess": round(float(np.median(v)), 4),
                         "pct_positive": round(float((v > 0).mean()), 4)}
    return out


def evaluate(rows, field, min_month_n):
    result = {}
    for name in HORIZONS:
        fwd = "fwd_" + name
        sample = [r for r in rows if field in r and fwd in r]
        if len(sample) < 50:
            result[name] = {"n": len(sample), "note": "insufficient data"}
            continue
        pooled_ic, pooled_p = spearmanr([r[field] for r in sample], [r[fwd] for r in sample])
        by_month = {}
        for r in sample:
            by_month.setdefault(r["date"][:7], []).append(r)
        monthly_ics, spreads, quintiles = [], [], {i: [] for i in range(5)}
        for ym in sorted(by_month):
            month = sorted(by_month[ym], key=lambda r: r[field])
            if len(month) < min_month_n:
                continue
            ic, _ = spearmanr([r[field] for r in month], [r[fwd] for r in month])
            if ic == ic:
                monthly_ics.append(float(ic))
            k = len(month) // 5
            for i in range(5):
                chunk = month[i * k:(i + 1) * k] if i < 4 else month[4 * k:]
                quintiles[i].append(float(np.mean([r[fwd] for r in chunk])))
            spreads.append(quintiles[0][-1] - quintiles[4][-1])
        block = HORIZON_MONTHS[name]
        ic_ci = moving_block_bootstrap_ci(monthly_ics, block) if len(monthly_ics) >= block else None
        spread_ci = moving_block_bootstrap_ci(spreads, block) if len(spreads) >= block else None
        result[name] = {
            "n": len(sample),
            "months": len(monthly_ics),
            "pooled_spearman_ic": round(float(pooled_ic), 4),
            "pooled_p_value": float("%.4g" % pooled_p),
            "fama_macbeth_mean_ic": round(float(np.mean(monthly_ics)), 4) if monthly_ics else None,
            "fama_macbeth_ci_block_months": block,
            "fama_macbeth_95ci": [round(ic_ci[0], 4), round(ic_ci[1], 4)] if ic_ci else None,
            "quintile_mean_excess": [round(float(np.mean(quintiles[i])), 4) for i in range(5)],
            "quintile_spread_q1_minus_q5": round(float(np.mean(spreads)), 4) if spreads else None,
            "quintile_spread_95ci": [round(spread_ci[0], 4), round(spread_ci[1], 4)] if spread_ci else None,
            "months_with_positive_spread": sum(1 for s in spreads if s > 0),
        }
    return result


def run_universe(label, price_dir, eps_dir, spy, exclude, min_month_n, note):
    rows, used = build_panel(price_dir, eps_dir, spy, exclude)
    block = {
        "label": label, "note": note,
        "tickers": len(used), "samples": len(rows),
        "panel_baseline_excess_return": panel_baseline(rows),
        "valuation_signal": evaluate(rows, "signal_valuation", min_month_n),
        "price_only_control_signal": evaluate(rows, "signal_price_only", min_month_n),
    }
    both = [r for r in rows if "signal_valuation" in r and "signal_price_only" in r]
    if both:
        c, _ = spearmanr([r["signal_valuation"] for r in both], [r["signal_price_only"] for r in both])
        block["rank_corr_valuation_vs_price_only"] = round(float(c), 4)
    return block, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card-price-dir", default=str(ROOT / "data/raw_5y"))
    ap.add_argument("--card-eps-dir", default=str(ROOT / "data/eps_quarterly"))
    ap.add_argument("--control-price-dir", default=str(ROOT / "data/sp500_5y"))
    ap.add_argument("--control-eps-dir", default=str(ROOT / "data/sp500_eps"))
    ap.add_argument("--spy", default=str(ROOT / "data/raw_5y/SPY.json"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    result = {"design": "v4 = v3 signal and inference, on an expanded card universe, a "
                        "price-only control signal, and an unselected S&P 500 control universe",
              "trailing_days": TRAILING_DAYS, "halflife_days": HALFLIFE_DAYS,
              "universes": []}

    cards, card_tickers = run_universe(
        "cards_50", args.card_price_dir, args.card_eps_dir, args.spy, set(), 10,
        "50 of the 54 published cards (GEV/SKHY/SNDK/SPCX excluded: too little listed "
        "history for a 2-year anchor plus a forward window). HAND-PICKED IN 2025-2026, "
        "i.e. selected after the 2023-2026 outcomes were known -- read panel_baseline "
        "before reading any IC from this universe.")
    result["universes"].append(cards)

    control, _ = run_universe(
        "sp500_control", args.control_price_dir, args.control_eps_dir, args.spy,
        CONTROL_OUTLIERS, 20,
        "Current S&P 500 membership from scripts/sp500.json, every name with a usable 5y "
        "price series and >=20 point-in-time TTM EPS observations. Not hand-picked for "
        "this site. Excluded outliers: " + ", ".join(sorted(CONTROL_OUTLIERS)))
    result["universes"].append(control)

    oos, _ = run_universe(
        "sp500_control_minus_cards", args.control_price_dir, args.control_eps_dir, args.spy,
        CONTROL_OUTLIERS | set(card_tickers) | {"BRKB"}, 20,
        "The control universe with every card ticker removed, so no name the site covers "
        "can contribute -- fully out-of-sample.")
    result["universes"].append(oos)

    result["verdict"] = (
        "확대해도 예측력은 확인되지 않는다. 카드 50종목에서는 12개월 FM IC −0.218 (95% CI "
        "[−0.254, −0.166], 23개월 중 22개월 음수, 5분위 +47.7%→+3.0% 단조)로 매우 강해 보이지만, "
        "이 유니버스는 2023~2026년 결과를 알고 고른 목록이다. 같은 패널의 신호 없는 12개월 평균 "
        "SPY 대비 초과수익이 +23%이고(5년 실현 중앙값 카드 +107% vs SPY +75%), 이 조건화 자체가 "
        "'지금 싸다 → 이후 초과수익'이라는 음의 상관을 기계적으로 만든다. 손으로 고르지 않은 "
        "S&P500 463종목에서 같은 신호는 전 구간에서 0과 구별되지 않는다(12개월 FM IC −0.023, "
        "CI [−0.076, +0.017]; 5분위는 단조가 아니라 U자형). 카드 종목을 모두 뺀 완전 표본외에서도 "
        "−0.012, CI [−0.074, +0.036]. 반대로 EPS를 제거한 순수 가격 신호는 같은 통제 유니버스에서 "
        "뚜렷한 양의 IC(12개월 +0.090, CI [+0.049, +0.152])를 보이는데, 이는 잘 알려진 12개월 "
        "가격 모멘텀이고 밸류에이션 규칙과는 반대 방향이다. 따라서 이 백테스트는 밸류에이션 탭에 "
        "점수를 신설할 근거가 되지 못한다.")

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    for u in result["universes"]:
        print(f"\n=== {u['label']}: {u['tickers']} tickers, {u['samples']} samples ===")
        for h, b in u["panel_baseline_excess_return"].items():
            print(f"  baseline {h:4} mean {b['mean_excess']:+.2%} median {b['median_excess']:+.2%} "
                  f"pos {b['pct_positive']:.0%}")
        for sig in ("valuation_signal", "price_only_control_signal"):
            print(f"  -- {sig}")
            for h, r in u[sig].items():
                if "note" in r:
                    continue
                print(f"     {h:4} FM_IC={r['fama_macbeth_mean_ic']:+.4f} CI={r['fama_macbeth_95ci']} "
                      f"Q1-Q5={r['quintile_spread_q1_minus_q5']:+.2%} "
                      f"quintiles={[round(x*100,1) for x in r['quintile_mean_excess']]}")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
