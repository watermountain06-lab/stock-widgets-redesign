#!/usr/bin/env python3
"""Pull 1-year daily price history for a US ticker from Yahoo Finance
(free, no API key). Computes MA5/20/60/120, 52-week high/low, LC/HC%, and
monthly OHLC aggregation for the "구간별 분석" narrative.

Usage: python3 fetch_price.py TICKER [--out out.json]

Ticker note: Yahoo Finance uses '-' where the official ticker has '.'
(e.g. BRK.B -> BRK-B). This script normalizes automatically.
"""
import argparse
import json
import statistics
import sys
import urllib.request
from datetime import datetime, timezone

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range}&interval=1d"


def yahoo_ticker(ticker):
    return ticker.replace(".", "-")


def fetch_chart(ticker, range_="1y"):
    url = CHART_URL.format(ticker=yahoo_ticker(ticker), range=range_)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    result = data["chart"]["result"]
    if not result:
        raise ValueError(f"no chart data for {ticker}: {data['chart'].get('error')}")
    return result[0]


def build_bars(chart):
    ts = chart["timestamp"]
    q = chart["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue  # market holiday / bad tick
        bars.append({
            "date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"),
            "o": round(o, 2), "h": round(h, 2), "l": round(l, 2), "c": round(c, 2),
            "v": int(v) if v else 0,
        })
    return bars


def drop_stale_last_bar(bars, min_volume_ratio=0.15):
    """If today's bar has abnormally low volume (intraday snapshot before
    market close), drop it so all reports share a consistent as-of date."""
    if len(bars) < 21:
        return bars
    recent_avg = statistics.mean(b["v"] for b in bars[-21:-1])
    if recent_avg > 0 and bars[-1]["v"] < recent_avg * min_volume_ratio:
        return bars[:-1]
    return bars


def moving_average(bars, n):
    closes = [b["c"] for b in bars]
    if len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 2)


def monthly_ohlc(bars):
    months = {}
    for b in bars:
        key = b["date"][:7]  # YYYY-MM
        m = months.setdefault(key, {"month": key, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]})
        m["h"] = max(m["h"], b["h"])
        m["l"] = min(m["l"], b["l"])
        m["c"] = b["c"]  # last bar in iteration order wins (bars are chronological)
    return list(months.values())


def summarize(ticker, bars):
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    cur = closes[-1]
    hi_52w, hi_date = max(zip(highs, (b["date"] for b in bars)))
    lo_52w, lo_date = min(zip(lows, (b["date"] for b in bars)))
    return {
        "ticker": ticker,
        "asOf": bars[-1]["date"],
        "current": cur,
        "high52w": hi_52w,
        "high52wDate": hi_date,
        "low52w": lo_52w,
        "low52wDate": lo_date,
        "lcPct": round((cur - lo_52w) / lo_52w * 100, 2),   # gain off the low
        "hcPct": round((cur - hi_52w) / hi_52w * 100, 2),   # (negative) drop from the high
        "ma5": moving_average(bars, 5),
        "ma20": moving_average(bars, 20),
        "ma60": moving_average(bars, 60),
        "ma120": moving_average(bars, 120),
        "monthly": monthly_ohlc(bars),
        "daily": bars,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--out", default=None)
    ap.add_argument("--range", dest="range_", default="1y", help="Yahoo chart range, e.g. 1y (default), 5y for historical-multiple averaging")
    args = ap.parse_args()

    chart = fetch_chart(args.ticker, range_=args.range_)
    bars = build_bars(chart)
    bars = drop_stale_last_bar(bars)
    if not bars:
        print(f"error: no usable bars for {args.ticker}", file=sys.stderr)
        sys.exit(1)

    out = summarize(args.ticker.upper(), bars)
    out_path = args.out or f"{args.ticker.upper()}_price.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {out_path} ({len(bars)} bars, as-of {out['asOf']})")


if __name__ == "__main__":
    main()
