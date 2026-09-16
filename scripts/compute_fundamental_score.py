#!/usr/bin/env python3
"""Fundamental score v1.0.0 (frozen 2026-08-25) - descriptive snapshot, not a return predictor.

Combines three equally-weighted-ish axes (33/33/34) into one 0-100 number per
ticker, mirroring compute_technical_score.py's bucket-table design but with a
different validation philosophy: this score summarizes "is this company cheap
/ healthy / growing right now," and is sanity-checked for outliers across the
40-ticker universe, not backtested against forward returns (see project memory
for why - the axes span different time horizons and a single predictive target
would obscure more than it reveals for a fundamentals snapshot).

Design decisions from the 2026-08-25 Codex review round (see project memory):
  - Banks (config's bank_exclude_tickers) are excluded entirely, not scored
    with a degraded model - their balance sheet/income statement shape is
    structurally different from a normal industrial/tech company.
  - A ticker missing SEC XBRL's operatingIncome tag but with pretaxIncome
    present gets an *estimated* operating income (pretaxIncome +
    interestExpense), flagged via operatingIncomeEstimated, applied
    consistently across every year used so CAGR stays internally consistent.
  - Negative equity forces debtToEquity to the worst bucket (a status of
    "negative_equity", not "missing") - the negative equity itself is the
    risk signal, so dropping the ratio would hide it rather than score it.
  - CAGR handles sign changes explicitly (loss-to-profit / profit-to-loss /
    persistent loss) instead of silently returning None whenever either
    endpoint isn't positive.
  - A ticker whose axis coverage falls under coverage_gate's thresholds is
    still scored (for internal comparison) but flagged coverageStatus:
    "partial" - a real score built from few data points isn't the same claim
    as a real score built from all of them, even though today's formula
    can't otherwise tell them apart.

Inputs:
  --financials  a fetch_financials.py --years 5 output (this repo's own copy,
                fetched into scripts/fundamental_data/)
  --valuation   scripts/valuation_signals.json (regenerate with compute_valuation_score.py;
                each entry carries its own asOf, echoed into the output as valuationAsOf)
                (has per.stage/pbr.stage/targetPrice.stage per ticker)
  --config      fundamental_score_config_v1.json

Output: one JSON record written to --out, or printed if omitted.
"""
import argparse
import json
from datetime import date


def latest_instant(entries):
    """entries: list of {"end": ..., "val": ...} (instant/balance-sheet concepts).
    Return the val with the latest end date, or None."""
    usable = [e for e in entries if e.get("val") is not None]
    if not usable:
        return None
    return max(usable, key=lambda e: e["end"])["val"]


def latest_duration(entries):
    """entries: list of {"end": ..., "val": ...} (income-statement concepts,
    annual periods). Return the val with the latest end date, or None."""
    return latest_instant(entries)


def instant_pair(entries_a, entries_b):
    """Return (val_a, val_b, end_date) from the latest end date both concepts
    share, or (None, None, None) if no end date has both. Two balance-sheet
    concepts each independently picking their own "latest" can silently pair
    values from different fiscal periods if one concept's tag is missing for
    a given year (Codex round-2 finding) - this pins both to a shared
    reporting date."""
    by_end_a = {e["end"]: e["val"] for e in entries_a if e.get("val") is not None}
    by_end_b = {e["end"]: e["val"] for e in entries_b if e.get("val") is not None}
    shared = sorted(set(by_end_a) & set(by_end_b))
    if not shared:
        return None, None, None
    end = shared[-1]
    return by_end_a[end], by_end_b[end], end


def value_at(entries, end_date):
    """Value of an instant concept at an exact end date, or None if that
    concept has no entry there (distinct from the concept having no data at
    all - callers decide how to treat each case)."""
    for e in entries:
        if e.get("end") == end_date and e.get("val") is not None:
            return e["val"]
    return None


def resolve_operating_income_series(fin):
    """Return (annual_entries, estimated) for operatingIncome. Falls back to
    pretaxIncome + interestExpense (paired by matching end date) when SEC XBRL's
    OperatingIncomeLoss tag is entirely absent for this filer - real for
    LLY/MRK/XOM in the 40-ticker set, a single-tag concept with no fallback in
    fetch_financials.py (unlike every other concept there)."""
    op_annual = fin["operatingIncome"]["annual"]
    if op_annual:
        return op_annual, False

    pretax = fin.get("pretaxIncome", {}).get("annual", [])
    if not pretax:
        return [], False
    interest_by_end = {e["end"]: e["val"] for e in fin.get("interestExpense", {}).get("annual", [])
                        if e.get("val") is not None}
    estimated = []
    for e in pretax:
        if e.get("val") is None:
            continue
        # A year with no matching interestExpense entry is excluded rather than
        # assumed to have zero interest expense (Codex round-2 finding) - we
        # can't tell "this company had no interest expense that year" apart
        # from "the tag just wasn't fetched for that year" from here.
        if e["end"] not in interest_by_end:
            continue
        estimated.append({"end": e["end"], "val": e["val"] + abs(interest_by_end[e["end"]])})
    return estimated, True


def find_cagr_pair(entries, target_years):
    usable = [e for e in entries if e.get("val") is not None]
    if len(usable) < 2:
        return None
    usable = sorted(usable, key=lambda e: e["end"])
    latest = usable[-1]
    latest_end = date.fromisoformat(latest["end"])
    target_days = target_years * 365.25

    best, best_diff = None, None
    for e in usable[:-1]:
        days_back = (latest_end - date.fromisoformat(e["end"])).days
        if days_back <= 0:
            continue
        diff = abs(days_back - target_days)
        if best_diff is None or diff < best_diff:
            best, best_diff = e, diff

    if best is None:
        return None
    years_elapsed = (latest_end - date.fromisoformat(best["end"])).days / 365.25
    if years_elapsed <= 0:
        return None
    return best, latest, years_elapsed


def score_growth_metric(entries, target_years, buckets):
    """Score a growth CAGR, handling sign changes explicitly rather than
    returning None whenever either endpoint isn't positive: loss-to-profit and
    profit-to-loss are real, opposite-direction signals, not just "can't
    compute" - so they get fixed points instead of a numeric CAGR."""
    pair = find_cagr_pair(entries, target_years)
    if pair is None:
        return None
    base, latest, years_elapsed = pair
    base_v, latest_v = base["val"], latest["val"]

    if base_v > 0 and latest_v > 0:
        cagr_pct = round(((latest_v / base_v) ** (1 / years_elapsed) - 1) * 100, 1)
        return {"value": cagr_pct, "points": bucket_points(cagr_pct, buckets)}
    if base_v <= 0 < latest_v:
        return {"value": None, "points": 4, "note": "적자(또는 0)에서 흑자로 전환 - CAGR 수치화 불가, 흑자전환으로 4점 처리"}
    if latest_v <= 0 < base_v:
        return {"value": None, "points": 1, "note": "흑자에서 적자(또는 0)로 전환 - 1점 처리"}
    return {"value": None, "points": 1, "note": "적자(또는 0) 지속 - CAGR 수치화 불가, 1점 처리"}


def bucket_points(value, buckets):
    if value is None:
        return None
    for b in buckets:
        if b["upper_exclusive"] is None or value < b["upper_exclusive"]:
            return b["points"]
    return buckets[-1]["points"]


def compute_health_axis(fin, config, op_income_annual, op_income_estimated):
    h = config["health"]["ratios"]
    out = {"dataQuality": {}}
    raw_points = []

    # 유동비율/당좌비율 - currentAssets/currentLiabilities를 같은 결산일 값으로 매칭
    # (각자 독립적으로 "최신값"을 뽑으면 태그 결측 연도가 다를 때 서로 다른 회계기간이 섞일 수 있음 - Codex 2라운드 지적)
    current_assets, current_liabilities, ca_end = instant_pair(
        fin["currentAssets"]["annual"], fin["currentLiabilities"]["annual"])

    if current_assets is not None and current_liabilities:
        v = round(current_assets / current_liabilities * 100, 1)
        out["currentRatio"] = {"value": v, "points": bucket_points(v, h["currentRatio"]["buckets"])}
        raw_points.append(out["currentRatio"]["points"])
    else:
        out["dataQuality"]["currentRatio"] = "missing"

    if current_assets is not None and current_liabilities:
        inventory = value_at(fin.get("inventory", {}).get("annual", []), ca_end) or 0
        v = round((current_assets - inventory) / current_liabilities * 100, 1)
        out["quickRatio"] = {"value": v, "points": bucket_points(v, h["quickRatio"]["buckets"])}
        raw_points.append(out["quickRatio"]["points"])
    else:
        out["dataQuality"]["quickRatio"] = "missing"

    # 차입금의존도 - 단기+장기차입금 태그가 둘 다 아예 없으면(값이 0이 아니라 데이터 자체가 없음)
    # "무차입"과 "결측"을 구분할 수 없으므로 missing 처리 (Codex 2라운드 지적: 이전엔 둘 다 0으로
    # 대체해서 차입금의존도 0%=5점을 줬음)
    short_debt_entries = fin.get("shortTermDebt", {}).get("annual", [])
    long_debt_entries = fin.get("longTermDebt", {}).get("annual", [])
    assets = latest_instant(fin["assets"]["annual"])
    if not short_debt_entries and not long_debt_entries:
        out["dataQuality"]["debtDependency"] = "missing (차입금 태그 데이터 자체가 없어 무차입과 결측을 구분 불가)"
    elif assets:
        short_debt = latest_instant(short_debt_entries) or 0
        long_debt = latest_instant(long_debt_entries) or 0
        v = round((short_debt + long_debt) / assets * 100, 1)
        out["debtDependency"] = {"value": v, "points": bucket_points(v, h["debtDependency"]["buckets"])}
        raw_points.append(out["debtDependency"]["points"])
    else:
        out["dataQuality"]["debtDependency"] = "missing (총자산 데이터 없음)"

    # 이자보상배율 - 영업이익 적자면 무조건 1점. 이자비용 태그가 아예 없으면(연도 상관없이 한 번도
    # 안 잡힘) 무차입으로 간주해 5점(원래 의도한 케이스). 태그는 있는데 해당 연도만 결측이면
    # 0으로 추정하지 않고 missing 처리 (Codex 2라운드 지적: 결측을 0으로 뭉뚱그려 최고점을 줬음)
    op_entries = op_income_annual
    op_entry = max((e for e in op_entries if e.get("val") is not None), key=lambda e: e["end"], default=None)
    interest_entries = fin.get("interestExpense", {}).get("annual", [])
    if op_entry is not None:
        op_income = op_entry["val"]
        if op_income <= 0:
            iv = value_at(interest_entries, op_entry["end"])
            v = round(op_income / abs(iv), 1) if iv else None
            out["interestCoverage"] = {"value": v, "points": 1, "note": "영업이익 적자(또는 0) - 무조건 1점"}
            raw_points.append(1)
        elif not interest_entries:
            out["interestCoverage"] = {"value": None, "points": 5, "note": "이자비용 태그 자체 없음(사실상 무차입) + 영업이익 흑자"}
            raw_points.append(5)
        else:
            iv = value_at(interest_entries, op_entry["end"])
            if iv is None:
                out["dataQuality"]["interestCoverage"] = "missing (해당 연도 이자비용 결측 - 다른 연도엔 태그 존재)"
            elif iv == 0:
                out["interestCoverage"] = {"value": None, "points": 5, "note": "이자비용 0으로 명시 보고 + 영업이익 흑자"}
                raw_points.append(5)
            else:
                v = round(op_income / abs(iv), 1)
                out["interestCoverage"] = {"value": v, "points": bucket_points(v, h["interestCoverage"]["buckets"])}
                raw_points.append(out["interestCoverage"]["points"])
    else:
        out["dataQuality"]["interestCoverage"] = "missing"

    # 부채비율 - total_liabilities가 결측이면 assets-equity 회계항등식으로 역산(같은 결산일 매칭),
    # 음수 자기자본은 missing이 아니라 최저점 + negative_equity 플래그
    # (그 자체가 재무위험 신호라, missing으로 빼면 오히려 신호가 사라짐 - Codex 1라운드 지적)
    total_liabilities, equity, _ = instant_pair(fin["totalLiabilities"]["annual"], fin["equityAttributableToParent"]["annual"])
    if total_liabilities is None:
        assets_v, equity_v, _ = instant_pair(fin["assets"]["annual"], fin["equityAttributableToParent"]["annual"])
        if assets_v is not None and equity_v is not None:
            total_liabilities, equity = assets_v - equity_v, equity_v

    if total_liabilities is not None and equity is not None:
        if equity <= 0:
            out["debtToEquity"] = {
                "value": None, "points": 1, "status": "negative_equity",
                "note": f"자기자본 음수(${equity / 1e9:.2f}B) - 비율 계산 대신 재무위험 신호로 최저점 처리",
            }
            raw_points.append(1)
        else:
            v = round(total_liabilities / equity * 100, 1)
            out["debtToEquity"] = {"value": v, "points": bucket_points(v, h["debtToEquity"]["buckets"])}
            raw_points.append(out["debtToEquity"]["points"])
    else:
        out["dataQuality"]["debtToEquity"] = "missing (데이터 없음)"

    if op_income_estimated:
        out["operatingIncomeEstimated"] = True

    if raw_points:
        # scale to the 33-point axis proportionally to how many sub-ratios were actually usable
        axis_points_raw = sum(raw_points) / (5 * len(raw_points)) * config["axis_weights"]["health"]
        out["axisPoints"] = round(axis_points_raw, 1)
        out["axisPointsRaw"] = axis_points_raw
        out["ratiosUsed"] = len(raw_points)
    else:
        out["axisPoints"] = None
        out["axisPointsRaw"] = None

    return out


def compute_growth_profit_axis(fin, config, op_income_annual, op_income_estimated):
    g = config["growth_profit"]["metrics"]
    out = {"dataQuality": {}}
    raw_points = []
    target_years = config["growth_profit"]["cagr_lookback_years_target"]

    revenue_annual = fin["revenue"]["annual"]
    net_income_annual = fin.get("netIncomeAttributableToParent", {}).get("annual") or fin["netIncome"]["annual"]

    latest_revenue = latest_duration(revenue_annual)
    latest_net_income = latest_duration(net_income_annual)
    # Same defect instant_pair() was written for, on the income statement instead of the
    # balance sheet, and it went unfixed because the lesson was applied only where it was
    # found. OperatingIncomeLoss is a tag many filers abandon: KLA's stops at FY2014, GE's
    # and Berkshire's at FY2012, J&J's at FY2014 - while revenue runs to the current year.
    # Dividing one by the other across that gap printed an operating margin of 5.7% for KLA
    # (real: about 40%), 49.9% for GE, and a plausible-looking 22.9% for J&J that was FY2014
    # income over FY2025 revenue. Nothing flagged it, on four live cards.
    op_end = latest_instant(op_income_annual) and max(
        (e["end"] for e in op_income_annual if e.get("val") is not None), default=None)
    rev_end = max((e["end"] for e in revenue_annual if e.get("val") is not None), default=None)
    latest_op_income = latest_duration(op_income_annual) if op_end == rev_end else None
    if op_end is not None and rev_end is not None and op_end != rev_end:
        out["dataQuality"]["opMargin"] = (
            f"missing (operatingIncome ends {op_end}, revenue ends {rev_end} - "
            "the filer stopped tagging OperatingIncomeLoss)")

    rev = score_growth_metric(revenue_annual, target_years, g["revenueCagr"]["buckets"])
    if rev is not None:
        out["revenueCagr"] = rev
        raw_points.append(rev["points"])
    else:
        out["dataQuality"]["revenueCagr"] = "missing (이력 부족)"

    # The CAGR is internally consistent - both endpoints come from the same series - but on
    # a series that stopped years ago it describes a window that ended then, printed beside
    # current-year metrics. KLA's "영업이익 CAGR -12.7%" measures a period ending FY2014.
    op = (score_growth_metric(op_income_annual, target_years, g["opIncomeCagr"]["buckets"])
          if op_end == rev_end else None)
    if op is None and op_end is not None and rev_end is not None and op_end != rev_end:
        out["dataQuality"]["opIncomeCagr"] = f"missing (series ends {op_end}, revenue ends {rev_end})"
    if op is not None:
        out["opIncomeCagr"] = op
        raw_points.append(op["points"])
    elif "opIncomeCagr" not in out["dataQuality"]:
        out["dataQuality"]["opIncomeCagr"] = "missing (이력 부족)"

    if latest_revenue and latest_op_income is not None:
        v = round(latest_op_income / latest_revenue * 100, 1)
        out["opMargin"] = {"value": v, "points": bucket_points(v, g["opMargin"]["buckets"])}
        raw_points.append(out["opMargin"]["points"])
    elif "opMargin" not in out["dataQuality"]:
        out["dataQuality"]["opMargin"] = "missing"

    if latest_revenue and latest_net_income is not None:
        v = round(latest_net_income / latest_revenue * 100, 1)
        out["netMargin"] = {"value": v, "points": bucket_points(v, g["netMargin"]["buckets"])}
        raw_points.append(out["netMargin"]["points"])
    else:
        out["dataQuality"]["netMargin"] = "missing"

    if op_income_estimated:
        out["operatingIncomeEstimated"] = True

    if raw_points:
        axis_points_raw = sum(raw_points) / (5 * len(raw_points)) * config["axis_weights"]["growth_profit"]
        out["axisPoints"] = round(axis_points_raw, 1)
        out["axisPointsRaw"] = axis_points_raw
        out["metricsUsed"] = len(raw_points)
    else:
        out["axisPoints"] = None
        out["axisPointsRaw"] = None

    return out


def SNAPSHOT_REF(config):
    """The date financial freshness is measured against: the run's own snapshot."""
    return config.get("snapshot_date")


def age_months(as_of, ref):
    if not as_of or not ref:
        return None
    a = date.fromisoformat(as_of)
    r = date.fromisoformat(ref)
    return round((r - a).days / 30.44, 1)


def staleness_check(financials_as_of, ticker, config):
    """v1.0.1 - flag financials too old to sit next to a same-day price.

    The threshold is derived, not tuned to a ticker: an annual filer is
    expected to report once every `annual_report_cycle_months` and needs
    `filing_grace_months` to file and be collected, so anything older than
    their sum is genuinely behind schedule rather than merely not-yet-updated.
    A foreign private issuer gets `foreign_issuer_extra_months` on top because
    the 20-F deadline is longer than a 10-K's. Sensitivity at 12/15/18 months
    is recorded in the config note so the choice can be argued rather than
    assumed.
    """
    st = config.get("staleness")
    if not st:
        return None
    months = age_months(financials_as_of, SNAPSHOT_REF(config))
    if months is None:
        return None
    limit = st["annual_report_cycle_months"] + st["filing_grace_months"]
    if ticker in set(st.get("foreign_issuers", [])):
        limit += st.get("foreign_issuer_extra_months", 0)
    if months > limit:
        return {"ageMonths": months, "limitMonths": limit}
    return None


def compute_valuation_axis(valuation_signal, config):
    if not valuation_signal:
        return {"axisPoints": None, "axisPointsRaw": None, "dataQuality": "no valuation_signals.json entry for this ticker"}

    stages = []
    weights = []
    if "per" in valuation_signal and "pbr" in valuation_signal:
        stages.append((valuation_signal["per"]["stage"] + valuation_signal["pbr"]["stage"]) / 2)
        weights.append(config["valuation"]["weight_per_pbr"])
    elif "per" in valuation_signal:
        stages.append(valuation_signal["per"]["stage"])
        weights.append(config["valuation"]["weight_per_pbr"])
    elif "pbr" in valuation_signal:
        stages.append(valuation_signal["pbr"]["stage"])
        weights.append(config["valuation"]["weight_per_pbr"])

    if "targetPrice" in valuation_signal:
        stages.append(valuation_signal["targetPrice"]["stage"])
        weights.append(config["valuation"]["weight_target"])

    # v1.0.1 - report coverage by BLOCK, not by input count. The axis has two
    # blocks that measure different things: the self-history block (PER/PBR,
    # which the formula already collapses under one weight) and the street
    # block (targetPrice). A missing self-history block does not degrade the
    # axis, it changes what the axis measures - and because targetPrice is
    # observed only in stages 1-3 across the universe while PER/PBR are modally
    # stage 5, dropping the self-history block RAISES the score. See the config
    # note; the arithmetic is unchanged here on purpose.
    coverage = {
        "historicalMultipleCoverage": sum(1 for k in ("per", "pbr") if k in valuation_signal),
        "targetPriceAvailable": "targetPrice" in valuation_signal,
    }

    if not stages:
        return {"axisPoints": None, "axisPointsRaw": None,
                "dataQuality": "no per/pbr/targetPrice stage available", **coverage}

    total_weight = sum(weights)
    combined_stage = sum(s * w for s, w in zip(stages, weights)) / total_weight
    axis_points_raw = config["axis_weights"]["valuation"] * (5 - combined_stage) / 4
    return {"combinedStage": round(combined_stage, 2), "axisPoints": round(axis_points_raw, 1),
            "axisPointsRaw": axis_points_raw, **coverage}


def grade_from_score(score, cuts):
    for label, cut in sorted(cuts.items(), key=lambda kv: -kv[1]):
        if score >= cut:
            return label
    return list(cuts.keys())[-1]


def compute_signal(ticker, fin, valuation_signal, config):
    if ticker in config.get("bank_exclude_tickers", []):
        return {
            "ticker": ticker,
            "status": "은행업 미지원 - v1 범위 밖. 유동비율/차입금의존도/영업이익 등 일반기업식 지표가 은행 사업구조와 맞지 않아 제외(2026-08-25 확정, Codex 1라운드).",
            "totalScore": None,
            "grade": None,
        }

    op_income_annual, op_income_estimated = resolve_operating_income_series(fin)

    valuation = compute_valuation_axis(valuation_signal, config)
    health = compute_health_axis(fin, config, op_income_annual, op_income_estimated)
    growth_profit = compute_growth_profit_axis(fin, config, op_income_annual, op_income_estimated)

    # 등급 판정은 각 축의 반올림 전 원값(axisPointsRaw) 합계로 - 이미 소수 첫째자리로 반올림된
    # axisPoints를 다시 더하면 경계값 근처에서 최대 0.1~0.2점 오차가 등급을 바꿀 수 있음
    # (Codex 2라운드 지적). 화면 표시용 totalScore만 마지막에 반올림.
    axes = (valuation, health, growth_profit)
    axis_points_raw = [a["axisPointsRaw"] for a in axes if a.get("axisPointsRaw") is not None]
    total_raw = sum(axis_points_raw) if axis_points_raw else None
    total_display = round(total_raw, 1) if total_raw is not None else None

    gate = config["coverage_gate"]
    valuation_ok = valuation.get("axisPoints") is not None
    health_ok = health.get("ratiosUsed", 0) >= gate["min_health_ratios"]
    growth_ok = growth_profit.get("metricsUsed", 0) >= gate["min_growth_profit_metrics"]

    revenue_annual = [e for e in fin["revenue"]["annual"] if e.get("val") is not None]
    financials_as_of = max((e["end"] for e in revenue_annual), default=None)

    # v1.0.1 - qualityFlags is deliberately SEPARATE from coverageStatus.
    # coverageStatus stays exactly what the frozen v1.0.0 gate decided, so it
    # remains comparable with earlier runs; these flags are additional data
    # concerns the gate does not model (staleness is not a coverage question,
    # and a target-only valuation axis passes the gate by design). A list, not
    # one flag, because a ticker can be target-only AND stale at once - TSM is.
    reasons = []
    if not valuation_ok:
        reasons.append("valuation_axis_missing")
    elif valuation.get("historicalMultipleCoverage") == 0:
        reasons.append("valuation_target_only")
    if not health_ok:
        reasons.append("health_ratios_below_gate")
    if not growth_ok:
        reasons.append("growth_metrics_below_gate")
    if len(revenue_annual) < 3:
        reasons.append("insufficient_annual_history")
    if health.get("debtToEquity", {}).get("status") == "negative_equity":
        reasons.append("negative_equity")

    stale = staleness_check(financials_as_of, ticker, config)
    if stale:
        reasons.append("stale_financials")

    coverage_status = "full" if (valuation_ok and health_ok and growth_ok) else "partial"

    # UI가 매번 health/growthProfit 안을 파고들지 않고 한 곳만 보고 데이터 상태를 표시할 수 있도록,
    # 세 가지 성격이 다른 신호(완전성/추정출처/실제재무위험)를 이름 붙여 그대로 노출.
    # 하나의 "이상신호"로 뭉치지 말라는 게 Codex 지적 - 소비자(UI)가 원하면 뭉칠 수도 있지만
    # 여기서는 성격을 보존한 채로 넘긴다.
    data_status = {
        "coverageStatus": coverage_status,
        "qualityFlags": reasons,
        "operatingIncomeEstimated": bool(health.get("operatingIncomeEstimated") or growth_profit.get("operatingIncomeEstimated")),
        "negativeEquity": health.get("debtToEquity", {}).get("status") == "negative_equity",
    }

    result = {
        "ticker": ticker,
        "financialsAsOf": financials_as_of,
        # the as-of date of the valuation signal this score was actually priced
        # off, so nothing downstream has to hardcode it (it used to be a
        # constant in preview's extract_tiers_scores.py and went stale silently
        # the moment the signals were regenerated)
        "valuationAsOf": (valuation_signal or {}).get("asOf"),
        "valuation": valuation,
        "health": health,
        "growthProfit": growth_profit,
        "totalScore": total_display,
        "grade": (grade_from_score(total_raw, config["grade_cuts"]) if total_raw is not None else None),
        "axesUsed": len(axis_points_raw),
        "coverageStatus": coverage_status,
        "qualityFlags": reasons,
        "financialsAgeMonths": age_months(financials_as_of, SNAPSHOT_REF(config)),
        "dataStatus": data_status,
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--financials", required=True)
    ap.add_argument("--valuation", required=True, help="scripts/valuation_signals.json")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.financials) as f:
        fin = json.load(f)
    with open(args.valuation) as f:
        valuation_all = json.load(f)
    with open(args.config) as f:
        config = json.load(f)

    ticker = args.ticker.upper()
    valuation_signal = valuation_all.get(ticker)

    result = compute_signal(ticker, fin, valuation_signal, config)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Wrote {args.out} - totalScore={result.get('totalScore')} grade={result.get('grade')} "
              f"status={result.get('status', result.get('coverageStatus'))}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
