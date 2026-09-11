#!/usr/bin/env python3
"""Pull analyst target-price consensus for a US ticker from Yahoo Finance's
quoteSummary endpoint (free, no API key, but requires a session cookie +
crumb handshake as of 2025 - see fetch_crumb()).

Usage: python3 fetch_target_price.py TICKER [--out out.json]

If Yahoo blocks the request (e.g. from a datacenter IP) or the ticker has no
analyst coverage, this exits non-zero so callers can skip the target-price
component and fall back to historical-multiple-only scoring for that ticker.
"""
import argparse
import http.cookiejar
import json
import sys
import urllib.request

CRUMB_URL = "https://query2.finance.yahoo.com/v1/test/getcrumb"
COOKIE_SEED_URL = "https://fc.yahoo.com"
QUOTE_SUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=financialData&crumb={crumb}"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def yahoo_ticker(ticker):
    return ticker.replace(".", "-")


def build_opener():
    jar = http.cookiejar.CookieJar()
    return jar, urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def fetch_crumb(opener):
    # Seed request just to receive Yahoo's session cookie; a non-200 here is
    # expected and fine as long as a cookie was set.
    try:
        opener.open(urllib.request.Request(COOKIE_SEED_URL, headers=HEADERS), timeout=15)
    except urllib.error.HTTPError:
        pass
    with opener.open(urllib.request.Request(CRUMB_URL, headers=HEADERS), timeout=15) as resp:
        crumb = resp.read().decode("utf-8").strip()
    if not crumb or "{" in crumb:
        raise RuntimeError(f"failed to obtain Yahoo crumb: {crumb!r}")
    return crumb


def fetch_target_data(ticker):
    """Standalone single-ticker fetch: does its own crumb handshake. For
    looping over many tickers in one run, do the handshake once and call
    fetch_target_data_with_crumb() per ticker instead (see daily_update.py)
    - Yahoo's crumb endpoint is a session-scoped resource, not per-ticker."""
    jar, opener = build_opener()
    crumb = fetch_crumb(opener)
    return fetch_target_data_with_crumb(opener, crumb, ticker)


def fetch_target_data_with_crumb(opener, crumb, ticker):
    url = QUOTE_SUMMARY_URL.format(ticker=yahoo_ticker(ticker), crumb=crumb)
    with opener.open(urllib.request.Request(url, headers=HEADERS), timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    results = data.get("quoteSummary", {}).get("result")
    if not results:
        raise ValueError(f"no financialData for {ticker}: {data.get('quoteSummary', {}).get('error')}")
    fd = results[0].get("financialData", {})

    def raw(key):
        v = fd.get(key)
        return v.get("raw") if isinstance(v, dict) else None

    return {
        "ticker": ticker.upper(),
        "currentPrice": raw("currentPrice"),
        "targetHighPrice": raw("targetHighPrice"),
        "targetLowPrice": raw("targetLowPrice"),
        "targetMeanPrice": raw("targetMeanPrice"),
        "targetMedianPrice": raw("targetMedianPrice"),
        "recommendationKey": fd.get("recommendationKey"),
        "recommendationMean": raw("recommendationMean"),
        "numberOfAnalystOpinions": raw("numberOfAnalystOpinions"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    try:
        out = fetch_target_data(args.ticker)
    except Exception as e:
        print(f"error: could not fetch target price for {args.ticker}: {e}", file=sys.stderr)
        sys.exit(1)

    if out["targetMeanPrice"] is None:
        print(f"error: no analyst target price available for {args.ticker}", file=sys.stderr)
        sys.exit(1)

    out_path = args.out or f"{args.ticker.upper()}_target.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {out_path} (target mean ${out['targetMeanPrice']}, {out['numberOfAnalystOpinions']} analysts)")


if __name__ == "__main__":
    main()
