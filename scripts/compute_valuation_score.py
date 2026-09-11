#!/usr/bin/env python3
"""Combine self-history relative valuation (PER/PBR vs this ticker's own 5-year
average) with the analyst target-price gap into a single 1-5 stage per metric,
using the same stage scale already baked into every widget's CSS
(stage-1..stage-5, val-fill widths 19/38/57/76/95%).

Inputs (all produced by other scripts in this repo):
  --price     output of fetch_price.py --range 5y   (needs 5y of daily bars)
  --financials output of fetch_financials.py --years 5
  --target    output of fetch_target_price.py (optional - degrades gracefully)

Output: one JSON record (see compute_signal()) written to --out, or appended
into a combined data/valuation_signals.json by the caller.

Scope note: only PER and PBR are computed here (both derivable purely from
SEC XBRL data - EPS and equity/shares - with no manual input). Forward P/E,
EV/EBITDA and PSR stay hand-authored in the widgets because their inputs
(management guidance, D&A, doesn't exist as a fetched field) aren't reliably
available from an unattended pipeline - see the project plan for why this is
an intentional v1 scope cut, not an oversight.
"""
import argparse
import json
import sys


def nearest_price_on_or_before(daily_bars, target_date):
    """daily_bars sorted ascending by date; return the closing price of the
    latest bar on or before target_date, or None if target_date predates all
    bars."""
    best = None
    for b in daily_bars:
        if b["date"] <= target_date:
            best = b
        else:
            break
    return best["c"] if best else None


def stage_from_gap_pct(gap_pct, thresholds=(-20, -5, 5, 20)):
    """gap_pct > 0 means "more expensive than the reference" -> higher stage
    (more overvalued). thresholds are the boundaries between stage 1..5."""
    lo1, lo2, hi2, hi1 = thresholds
    if gap_pct < lo1:
        return 1
    if gap_pct < lo2:
        return 2
    if gap_pct <= hi2:
        return 3
    if gap_pct <= hi1:
        return 4
    return 5


def stage_from_upside_pct(upside_pct):
    """upside_pct > 0 means target price is ABOVE current price (cheap vs
    target) -> LOWER stage (undervalued), inverse of stage_from_gap_pct."""
    if upside_pct > 15:
        return 1
    if upside_pct > 5:
        return 2
    if upside_pct >= -5:
        return 3
    if upside_pct >= -15:
        return 4
    return 5


STAGE_LABELS = {1: "매우낮음", 2: "낮음", 3: "적정", 4: "높음", 5: "매우높음"}


def compute_multiple_series(price_daily, annual_per_share):
    """For each (end_date, per_share_value) in annual_per_share, look up the
    price on/near that date and compute multiple = price/per_share_value.
    Returns list of (end_date, multiple)."""
    out = []
    for end_date, per_share in annual_per_share:
        if not per_share or per_share <= 0:
            continue
        px = nearest_price_on_or_before(price_daily, end_date)
        if px is None:
            continue
        out.append((end_date, px / per_share))
    return out


def pair_by_nearest_date(series_a, series_b, tolerance_days=120):
    """Pair each (date, value) in series_a with the nearest (date, value) in
    series_b within tolerance_days; entries with no match inside the window
    are dropped. Returns [(date_a, value_a, value_b), ...].

    equity and shares-outstanding are fetched as independent XBRL concepts
    with different end-date conventions (fiscal-year-end vs filing
    cover-page date), so they can't just be zipped by list position - on V
    (Visa), SEC's non-dimensional sharesOutstanding facts only go back to a
    single stale 2009 entry (Visa reports shares per-class from 2010 on, and
    XBRL companyfacts drops dimensional facts), so a position-based zip
    silently paired 2025 equity with 2009 share count, inflating BVPS ~4x
    and understating PBR by the same factor. Matching by proximity instead
    means a year with no shares data anywhere nearby is simply skipped."""
    from datetime import date as _date

    def parse(d):
        return _date.fromisoformat(d)

    pairs = []
    for date_a, value_a in series_a:
        best = None
        for date_b, value_b in series_b:
            delta = abs((parse(date_a) - parse(date_b)).days)
            if delta <= tolerance_days and (best is None or delta < best[0]):
                best = (delta, value_b)
        if best:
            pairs.append((date_a, value_a, best[1]))
    return pairs


MIN_HISTORY_YEARS = 3  # below this, a "5-year average" is more noise than signal


def compute_signal(ticker, price_data, financials_data, target_data=None,
                    weight_component_a=0.6, weight_component_b=0.4):
    current_price = price_data["current"]
    daily = sorted(price_data["daily"], key=lambda b: b["date"])

    eps_annual = [(a["end"], a["val"]) for a in financials_data["epsDiluted"]["annual"]]
    equity_annual = [(a["end"], a["val"]) for a in financials_data["equityAttributableToParent"]["annual"]]
    shares_annual = [(a["end"], a["val"]) for a in financials_data["sharesOutstanding"]["annual"]]
    bvps_annual = [(d, eq / sh) for d, eq, sh in pair_by_nearest_date(equity_annual, shares_annual)
                   if sh]

    result = {"ticker": ticker, "asOf": price_data["asOf"], "currentPrice": current_price,
              "dataQuality": {}}

    # --- PER ---
    if eps_annual and eps_annual[-1][1] and eps_annual[-1][1] > 0:
        latest_eps = eps_annual[-1][1]
        current_per = round(current_price / latest_eps, 2)
        per_series = compute_multiple_series(daily, eps_annual)
        if len(per_series) >= MIN_HISTORY_YEARS:
            hist_avg_per = sum(m for _, m in per_series) / len(per_series)
            per_gap_pct = round((current_per - hist_avg_per) / hist_avg_per * 100, 1)
            result["per"] = {
                "current": current_per, "historicalAvg5y": round(hist_avg_per, 2),
                "gapPct": per_gap_pct, "stage": stage_from_gap_pct(per_gap_pct),
                "sampleYears": len(per_series),
            }
    if "per" not in result:
        result["dataQuality"]["per"] = "missing (no positive EPS history, or fewer than 3 usable years)"

    # --- PBR ---
    if bvps_annual and bvps_annual[-1][1] and bvps_annual[-1][1] > 0:
        latest_bvps = bvps_annual[-1][1]
        current_pbr = round(current_price / latest_bvps, 2)
        pbr_series = compute_multiple_series(daily, bvps_annual)
        if len(pbr_series) >= MIN_HISTORY_YEARS:
            hist_avg_pbr = sum(m for _, m in pbr_series) / len(pbr_series)
            pbr_gap_pct = round((current_pbr - hist_avg_pbr) / hist_avg_pbr * 100, 1)
            result["pbr"] = {
                "current": current_pbr, "historicalAvg5y": round(hist_avg_pbr, 2),
                "gapPct": pbr_gap_pct, "stage": stage_from_gap_pct(pbr_gap_pct),
                "sampleYears": len(pbr_series),
            }
    if "pbr" not in result:
        result["dataQuality"]["pbr"] = "missing (no positive equity/shares history within date tolerance, or fewer than 3 matched years)"

    # --- target price (component B) ---
    if target_data and target_data.get("targetMeanPrice"):
        target_mean = target_data["targetMeanPrice"]
        upside_pct = round((target_mean - current_price) / current_price * 100, 1)
        result["targetPrice"] = {
            "mean": target_mean, "high": target_data.get("targetHighPrice"),
            "low": target_data.get("targetLowPrice"), "upsidePct": upside_pct,
            "stage": stage_from_upside_pct(upside_pct),
            "numAnalysts": target_data.get("numberOfAnalystOpinions"),
            "recommendationKey": target_data.get("recommendationKey"),
        }
    else:
        result["dataQuality"]["targetPrice"] = "missing (fetch_target_price.py failed or no coverage)"

    # --- combined stage ---
    component_a_stages = [v["stage"] for k, v in result.items() if k in ("per", "pbr") and isinstance(v, dict)]
    if component_a_stages:
        component_a = sum(component_a_stages) / len(component_a_stages)
        if "targetPrice" in result:
            combined = component_a * weight_component_a + result["targetPrice"]["stage"] * weight_component_b
        else:
            combined = component_a
        combined_stage = max(1, min(5, round(combined)))
        result["combinedStage"] = combined_stage
        result["combinedLabel"] = STAGE_LABELS[combined_stage]
    else:
        result["dataQuality"]["combined"] = "missing (neither PER nor PBR computable)"

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--price", required=True, help="fetch_price.py --range 5y output")
    ap.add_argument("--financials", required=True, help="fetch_financials.py --years 5 output")
    ap.add_argument("--target", default=None, help="fetch_target_price.py output (optional)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.price) as f:
        price_data = json.load(f)
    with open(args.financials) as f:
        financials_data = json.load(f)
    target_data = None
    if args.target:
        try:
            with open(args.target) as f:
                target_data = json.load(f)
        except FileNotFoundError:
            print(f"warning: {args.target} not found, proceeding without target price", file=sys.stderr)

    result = compute_signal(args.ticker.upper(), price_data, financials_data, target_data)

    out_path = args.out or f"{args.ticker.upper()}_valuation_signal.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    dq = result.get("dataQuality") or {}
    print(f"Wrote {out_path} - combinedStage={result.get('combinedStage', 'N/A')} dataQuality issues: {list(dq.keys()) or 'none'}")


if __name__ == "__main__":
    main()
