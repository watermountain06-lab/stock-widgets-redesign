#!/usr/bin/env python3
"""Point-in-time backtest v2: at each real quarterly-earnings disclosure date T, compute
a predicted [low, high] PER band using ONLY information available strictly before T --
an exponentially recency-weighted percentile of the trailing N-year daily historical PER
distribution (T's own day excluded) -- then compare against the ACTUAL realized daily PER
PATH over the following period (T to the next checkpoint), evaluated in PER-space using
each day's own point-in-time TTM EPS (not T's frozen EPS). A $-denominated band anchored
at T's own EPS is also reported for display, but the hit/miss VERDICT is decided in
PER-space -- see "why PER-space, not price-space" below.

v2 replaced v1 after a 2026-09-02 three-reviewer team session (two Claude opus agents --
a quant-statistician and a valuation-analyst -- plus an independent Codex cross-check, all
reading the real v1 output and code) converged on the same structural findings. This
docstring records why v1's specific choices were replaced, since the mistakes are easy to
re-make if this file is edited without this context:

1. WHY PER-SPACE EVALUATION, NOT PRICE-SPACE (the "denominator lag" bug):
   v1 froze TTM_EPS(T) for the entire holding period and compared REALIZED PRICE against
   a band anchored at that frozen EPS. But real TTM EPS keeps growing during the holding
   period (NVDA's grew 19x across the 13 checkpoints in the 5y backtest) while trailing
   PER mechanically compresses as EPS catches up to price. Comparing frozen-EPS-anchored
   price bands against realized price systematically overstates the predicted range,
   because the model implicitly assumes EPS stays at T's level the whole time. Fix:
   evaluate the REALIZED DAILY PER PATH -- close(D)/TTM_EPS_asof(D), using each day's own
   point-in-time EPS (already computed correctly via the ttm_eps_asof step function) --
   against the predicted PER band. This removes the mechanical bias at the source and is
   still fully point-in-time (no future information enters the band's inputs; the
   evaluation now also uses only information known as of each evaluation day).

2. WHY EXPONENTIAL RECENCY-WEIGHTING, NOT OUTLIER TRIMMING (the "asymmetric trim" bug):
   v1 used a per-checkpoint MAD-based threshold that dropped UPPER-tail outliers only
   (to exclude a real Jul-Aug 2023 PER spike to 240-250x, caused by price re-rating on an
   AI-demand guidance surprise before trailing EPS had caught up). This was a real
   improvement over an even cruder fixed-5%-top-trim (which a Codex review had already
   correctly flagged as a global fix applied to checkpoints that never had the artifact).
   But the team review found the MAD approach ALSO structurally biased: because only the
   top gets trimmed, the ceiling narrows for spike-affected checkpoints while the floor
   keeps the full pre-2023 high-multiple tail untouched -- so breached_top became
   structurally near-impossible (0/12 in the last full run) while every miss landed on
   breached_bottom. A valuation-analyst reviewer also pointed out a real flaw in HOW that
   trim was chosen: a symmetric trim was tested and rejected specifically because it
   lowered the full_hit count (10->5) -- but "the trim changed the verdict" is not a valid
   reason to reject a trim; the real question is whether the UNTRIMMED verdicts were
   trustworthy in the first place, and a chart whose entire purpose is measuring honest
   hit/miss must not pick the trim that makes the score look best. That is the exact
   selection pressure this backtest exists to detect, not commit.
   Fix: replace outlier trimming entirely with exponential recency-weighting of the
   trailing sample (half-life ~6 months by default). This has no "which % to trim"
   researcher-degree-of-freedom, and it resolves the 2023 spike more honestly: once
   weighted, a 30-40-trading-day regime from ~18-24 months before a later checkpoint is
   naturally down-weighted rather than either fully included (v1 untrimmed) or manually
   excised (v1 MAD-trimmed) -- the sample adapts continuously rather than via a discrete,
   arguable outlier cutoff. It also directly targets the OTHER team finding: NVDA's
   trailing PER is non-stationary (secularly declining as EPS outgrows price), so a flat
   (unweighted) 2-year average is a lagging estimator of a moving target regardless of
   whether outliers are trimmed -- recency-weighting is the correct tool for that, not
   outlier removal.

3. WHY BAND WIDTH IS NOW REPORTED ALONGSIDE EVERY VERDICT:
   v1's real 5y output included checkpoints like 2024-05-29 with predicted_low=$74,
   predicted_high=$364 (a 4.9x-wide band) classified "full_hit" -- technically correct but
   not informative; a band that wide cannot be "missed". Publishing a bare hit-rate badge
   from bands this wide is misleading. Every checkpoint now carries its own band width (as
   a ratio and as a PER range) so a reader/consumer can see when a "hit" isn't evidence of
   anything.

4. REAL CODE BUGS FIXED (found by the quant-statistician reviewer reading v1's code):
   - `percentile()` did `cuts[int(pct) - 1]`, silently truncating non-integer percentile
     arguments (dormant at pct=10/90 exactly, but a real bug for any other value). Fixed:
     the new weighted_percentile() takes any float in [0,100] correctly, no int() cast.
   - `date_to_idx.get(end_date) or next(...)` used `or` as a None-coalesce, which is wrong
     when the lookup legitimately returns index 0 (falsy) -- `0 or X` evaluates to `X`.
     Fixed: explicit `is None` check.
   - v1's MAD trim's `len(kept) < 20` fallback was a cliff (silently returns the FULL
     untrimmed sample instead of degrading gracefully) -- moot now that trimming is
     removed in favor of weighting, which has no such cliff.

5. NOT YET DONE (flagged by the team, real scope for a v3, not attempted here):
   - Switching the anchor from trailing EPS to point-in-time FORWARD consensus EPS (the
     valuation-analyst reviewer's strongest single recommendation, and the same anchor the
     site's own hand-authored Bear/Base/Bull "목표가 밴드" card already uses) would remove
     denominator lag at the source rather than compensating for it in evaluation-space,
     and would make the backtest test the same framework the site actually uses. Not
     implemented: doing this point-in-time requires archived historical consensus
     estimates (not just trailing actuals), which isn't sourced yet.
   - Validating this method on a stable, single-regime ticker (e.g. JNJ, MSFT) before
     trusting its NVDA-specific verdicts, since NVDA's real multi-regime history (gaming
     -> crypto -> AI/datacenter) confounds "is the method broken" with "did NVDA
     re-rate" -- not attempted here, single-ticker scope only.
   - Sample non-independence: consecutive checkpoints share ~87% of their trailing window
     (2yr window, ~3mo between checkpoints) and the ~500 daily observations within a
     window are strongly autocorrelated -- the effective sample size behind any aggregate
     hit-rate stat is closer to 10-20 (regime count) than the nominal checkpoint or day
     count. This is now stated explicitly in the output rather than left implicit.

6. TRIED AND REJECTED (2026-09-02): an automatic "eps_jump_flag" that compared a
   checkpoint's own quarter_eps against its trailing-4-quarter average (flag if >=1.75x),
   meant to caption checkpoints whose TTM EPS -- and therefore predicted_low/high -- is
   inflated by a one-time item (e.g. GOOGL's 2026 Q1/Q2 SpaceX IPO + Anthropic stake
   mark-to-market gains, confirmed against the card's own already-published valuation text).
   Rejected before shipping: re-running it on NVDA flagged five 2023-2024 checkpoints that
   are NOT one-time items -- they're NVDA's real, sustained AI-demand earnings ramp
   (quarter_eps 0.057->0.082->0.248->0.371->0.492->0.598, each beating the last for 5+
   consecutive quarters). A pure EPS-magnitude-of-jump heuristic cannot distinguish "real
   sustained growth" from "one-off non-operating gain" -- that distinction lives in WHY the
   number moved (operating income growth vs an "Other income" mark-to-market line), which
   this script has no access to (it only ever pulls `us-gaap:EarningsPerShareDiluted`, not
   an income-statement breakdown). Shipping the heuristic risked mislabeling NVDA's genuine
   growth story as a caution flag on the already-live NVDA card. If this is revisited, it
   needs an actual operating-income vs net-income signal (or a manually curated per-ticker
   list of known one-time items), not a magnitude-only threshold.

--daily-json expects {"daily": [[date,o,h,l,c,v], ...]} (row-array form).
data/raw_5y/NVDA.json stores daily bars as dicts, not rows -- convert first:

    python3 -c "
import json
d = json.load(open('data/raw_5y/NVDA.json'))
rows = [[b['date'],b['o'],b['h'],b['l'],b['c'],b['v']] for b in d['daily']]
json.dump({'daily': rows}, open('/tmp/NVDA_5y_for_backtest.json','w'))"

Usage:
    python3 compute_earnings_backtest_band.py NVDA \
      --eps data/eps_quarterly/NVDA.json --daily-json /tmp/NVDA_5y_for_backtest.json \
      --trailing-years 2 --per-low-pctile 10 --per-high-pctile 90 --halflife-days 180 \
      --out scripts/NVDA_earnings_backtest.json
"""
import argparse
import json
from datetime import date


def add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def weighted_percentile(pairs, pct):
    """pairs: list of (value, weight), weight > 0. pct in [0,100]. Step-function weighted
    percentile (no interpolation between points) -- simple, auditable, no distributional
    assumption. Correctly handles any float pct (v1's percentile() silently truncated
    non-integer pct via int() -- fixed here by not casting at all)."""
    pairs = sorted(pairs, key=lambda x: x[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    target = max(0.0, min(100.0, pct)) / 100 * total
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= target:
            return v
    return pairs[-1][0]


def recency_weight(obs_date_str, checkpoint_date_str, halflife_days):
    """Exponential decay weight: 1.0 at the checkpoint, 0.5 at halflife_days before it.
    Replaces v1's outlier trimming (see module docstring point 2 for why)."""
    d = date.fromisoformat(obs_date_str)
    t = date.fromisoformat(checkpoint_date_str)
    age_days = (t - d).days
    return 0.5 ** (age_days / halflife_days)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--eps", required=True)
    ap.add_argument("--daily-json", required=True)
    ap.add_argument("--trailing-years", type=int, default=2)
    ap.add_argument("--per-low-pctile", type=float, default=10)
    ap.add_argument("--per-high-pctile", type=float, default=90)
    ap.add_argument("--halflife-days", type=float, default=180,
                     help="exponential recency-weighting half-life for the trailing PER "
                          "sample, in days (default ~6 months; see module docstring point 2)")
    ap.add_argument("--exclude-per-window", nargs=2, metavar=("START", "END"), default=None,
                     help="ISO dates [start,end] (inclusive) to drop from the TRAILING PER "
                          "sample only (never from the realized-PER evaluation path). For a "
                          "manually verified, named non-operating distortion period ONLY -- "
                          "e.g. BRK.B's 2022 GAAP EPS swing near zero from ASU 2016-01 "
                          "equity mark-to-market losses on its public-stock portfolio, a "
                          "real and specifically-known event, not an inferred one. Never "
                          "auto-detect this from output magnitude (band width, EPS-jump "
                          "ratio, etc.) -- see module docstring point 6 for why an earlier "
                          "magnitude-only heuristic was tried and rejected (it flagged 5 of "
                          "NVDA's real consecutive-growth quarters as false positives).")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.eps) as f:
        eps_points = json.load(f)
    with open(args.daily_json) as f:
        daily_data = json.load(f)
    daily = daily_data["daily"]  # ascending; either [date,o,h,l,c,v] tuples or {date,o,h,l,c,v} dicts
    if daily and isinstance(daily[0], dict):
        dates = [row["date"] for row in daily]
        closes = [row["c"] for row in daily]
    else:
        dates = [row[0] for row in daily]
        closes = [row[4] for row in daily]
    price_start = date.fromisoformat(dates[0])

    # ttm_eps_asof(D): step function, most recent quarter with available_date <= D.
    eps_points_sorted = sorted(eps_points, key=lambda e: e["available_date"])
    ttm_asof = []
    ptr = -1
    for d in dates:
        while ptr + 1 < len(eps_points_sorted) and eps_points_sorted[ptr + 1]["available_date"] <= d:
            ptr += 1
        ttm_asof.append(eps_points_sorted[ptr]["ttm_eps"] if ptr >= 0 else None)

    # Daily historical PER series (only where TTM EPS as-of that day is defined and > 0).
    # This is both the input for the trailing sample AND, for the evaluation window, the
    # REALIZED PER path -- point-in-time throughout, in both roles.
    per_series = []  # list of (date, per)
    for i, d in enumerate(dates):
        eps = ttm_asof[i]
        if eps is not None and eps > 0:
            per_series.append((d, closes[i] / eps))

    date_to_idx = {d: i for i, d in enumerate(dates)}
    per_by_date = dict(per_series)

    exclude_start, exclude_end = (args.exclude_per_window if args.exclude_per_window
                                   else (None, None))
    if exclude_start:
        # Validate: real ISO dates, start <= end. Compare as date objects (not raw
        # strings) so unpadded/malformed input fails loudly instead of silently
        # mis-filtering (Codex review, 2026-09-04).
        exclude_start_d = date.fromisoformat(exclude_start)
        exclude_end_d = date.fromisoformat(exclude_end)
        if exclude_start_d > exclude_end_d:
            raise SystemExit(f"--exclude-per-window: start {exclude_start} is after end {exclude_end}")
        exclude_start, exclude_end = exclude_start_d.isoformat(), exclude_end_d.isoformat()

    checkpoints = []
    for e in eps_points_sorted:
        t_str = e["available_date"]
        if t_str < dates[0] or t_str > dates[-1]:
            continue
        if e["ttm_eps"] <= 0:
            continue  # PER undefined for negative/zero TTM EPS -- skip as an anchor
        t = date.fromisoformat(t_str)
        window_start = add_years(t, -args.trailing_years)
        if window_start < price_start:
            continue  # not enough trailing history yet
        sample = [(p, recency_weight(d, t_str, args.halflife_days))
                  for (d, p) in per_series if window_start.isoformat() <= d < t_str
                  and not (exclude_start is not None and exclude_start <= d <= exclude_end)]
        if len(sample) < 100:
            continue
        per_low = weighted_percentile(sample, args.per_low_pctile)
        per_high = weighted_percentile(sample, args.per_high_pctile)
        predicted_low = round(e["ttm_eps"] * per_low, 2)
        predicted_high = round(e["ttm_eps"] * per_high, 2)
        checkpoints.append({
            "checkpoint_date": t_str,
            "quarter_end": e["quarter_end"],
            "ttm_eps": e["ttm_eps"],
            "trailing_sample_size": len(sample),
            "per_low": round(per_low, 2),
            "per_high": round(per_high, 2),
            "band_width_ratio": round(per_high / per_low, 2) if per_low > 0 else None,
            "predicted_low": predicted_low,
            "predicted_high": predicted_high,
            # unrounded thresholds, kept only to classify the zone correctly below --
            # comparing a raw realized PER against a *rounded* per_low/per_high creates a
            # spurious ~0.005 dead zone where a checkpoint the price chart visually shows
            # as "inside the band" gets flagged breached (caught via user visual inspection
            # of AAPL's 2026-01-30 checkpoint, 2026-09-02). Popped before the final dump.
            "_per_low_raw": per_low,
            "_per_high_raw": per_high,
        })

    checkpoints.sort(key=lambda c: c["checkpoint_date"])

    # Realized PER PATH per checkpoint: from this checkpoint's date to the next
    # checkpoint's date (exclusive), or to the end of price data for the last (still-open)
    # checkpoint. Evaluated in PER-space using each day's own point-in-time EPS (per_by_date
    # / per_series), NOT price compared against a frozen-EPS $ band -- see docstring point 1.
    for i, cp in enumerate(checkpoints):
        start_idx = date_to_idx.get(cp["checkpoint_date"])
        if start_idx is None:
            start_idx = next(j for j, d in enumerate(dates) if d >= cp["checkpoint_date"])
        if i + 1 < len(checkpoints):
            end_date = checkpoints[i + 1]["checkpoint_date"]
            end_idx = date_to_idx.get(end_date)
            if end_idx is None:  # v1 bug fix: explicit None-check, not `or` (0 is falsy)
                end_idx = next(j for j, d in enumerate(dates) if d >= end_date)
            is_open = False
        else:
            end_idx = len(dates)
            is_open = True

        window_dates = dates[start_idx:end_idx]
        window_pers = [per_by_date[d] for d in window_dates if d in per_by_date]
        if not window_pers:
            cp["is_open"] = True
            cp["realized_per_low"] = None
            cp["realized_per_high"] = None
            cp["zone"] = "pending"
            cp.pop("_per_low_raw", None); cp.pop("_per_high_raw", None)
            continue

        realized_per_high = max(window_pers)
        realized_per_low = min(window_pers)
        cp["realized_per_high"] = round(realized_per_high, 2)
        cp["realized_per_low"] = round(realized_per_low, 2)
        # For display only: what that realized PER range corresponds to in $ terms, using
        # each day's own EPS (not a single frozen anchor).
        window_prices = [closes[date_to_idx[d]] for d in window_dates]
        cp["realized_price_high"] = max(window_prices)
        cp["realized_price_low"] = min(window_prices)
        cp["period_end_date"] = window_dates[-1]
        cp["is_open"] = is_open

        breached_top = realized_per_high > cp["_per_high_raw"]
        breached_bottom = realized_per_low < cp["_per_low_raw"]
        if breached_top and breached_bottom:
            zone = "breached_both"
        elif breached_top:
            zone = "breached_top"
        elif breached_bottom:
            zone = "breached_bottom"
        else:
            zone = "full_hit"
        cp["zone"] = zone
        del cp["_per_low_raw"], cp["_per_high_raw"]

    resolved = [c for c in checkpoints if not c["is_open"]]
    zone_counts = {"full_hit": 0, "breached_top": 0, "breached_bottom": 0, "breached_both": 0}
    for c in resolved:
        zone_counts[c["zone"]] += 1
    median_width = None
    if resolved:
        widths = sorted(c["band_width_ratio"] for c in resolved if c["band_width_ratio"])
        median_width = widths[len(widths) // 2] if widths else None

    result = {
        "ticker": args.ticker,
        "methodology": (
            f"각 체크포인트는 실제 분기 재무제표 발표일(그 시점까지의 정보만 사용). 예상 밴드(PER 기준) = "
            f"직전 {args.trailing_years}년간의 일별 PER 분포에서 체크포인트에 가까울수록 더 큰 가중치를 주는 "
            f"지수가중 {args.per_low_pctile:.0f}~{args.per_high_pctile:.0f} 백분위수(반감기 {args.halflife_days:.0f}일) "
            f"— 임의로 특정 구간을 잘라내는 대신, 오래된 관측치일수록 자연스럽게 영향력이 줄어드는 방식. "
            f"판정은 가격이 아니라 PER 공간에서 이루어짐: 실현 PER(그날그날 실제 갱신된 EPS 기준)이 예상 PER 밴드 "
            f"안에 있었는지를 다음 체크포인트까지 비교. 발표 당일은 트레일링 표본에서 제외. "
            f"⚠️ 참고: 연속된 체크포인트끼리는 트레일링 구간의 상당 부분을 공유하고 있어 통계적으로 독립적인 "
            f"시행이 아님 — 적중 개수를 신뢰구간처럼 해석하지 말 것."
            + (f" 트레일링 PER 표본에서 {exclude_start}~{exclude_end} 구간은 제외했다(수동 검증된 "
               f"비영업 왜곡 기간 — magnitude 기반 자동 감지 아님)."
               if exclude_start else "")
        ),
        "trailing_years": args.trailing_years,
        "per_low_pctile": args.per_low_pctile,
        "per_high_pctile": args.per_high_pctile,
        "halflife_days": args.halflife_days,
        "exclude_per_window": [exclude_start, exclude_end] if exclude_start else None,
        "checkpoints_total": len(checkpoints),
        "checkpoints_resolved": len(resolved),
        "zone_counts": zone_counts,
        "median_band_width_ratio": median_width,
        "checkpoints": checkpoints,
    }

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)

    print(f"{args.ticker}: {len(checkpoints)} checkpoints ({len(resolved)} resolved), "
          f"zones={zone_counts}, median band width={median_width}x -> {args.out}")


if __name__ == "__main__":
    main()
