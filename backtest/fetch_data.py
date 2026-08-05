#!/usr/bin/env python3
"""Fetch daily EUR/USD OHLC history for real (non-synthetic) backtesting.

Stooq is the primary source (free, no auth/API key, no rate limiting seen
in practice). yfinance is a fallback -- Yahoo's endpoints have been
increasingly rate-limited/bot-gated, so it's not the default. Writes
backtest/data/eurusd_daily.csv, which is gitignored (regenerable, not
committed) -- re-run anytime to refresh.

Usage: python3 backtest/fetch_data.py [--start 2015-01-01] [--end 2026-08-05]

On the Mac Mini, use ~/forex-env/bin/python (a python3.12 venv), not system
python3 -- Homebrew's python3.14 there SIGBUSes inside yfinance.download(),
a pandas/numpy wheel-compatibility issue, not a bug in this script.
"""
import argparse
import datetime as dt
import io
import sys
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "backtest" / "data" / "eurusd_daily.csv"


def fetch_stooq(start: str, end: str) -> pd.DataFrame:
    url = "https://stooq.com/q/d/l/?s=eurusd&i=d"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    if df.empty or "Date" not in df.columns:
        raise ValueError(f"Stooq returned no usable data: {resp.text[:200]}")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df.loc[start:end]


def fetch_yfinance(start: str, end: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download("EURUSD=X", start=start, end=end, progress=False)
    if df.empty:
        raise ValueError("yfinance returned no data")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=dt.date.today().isoformat())
    args = parser.parse_args()

    try:
        df = fetch_stooq(args.start, args.end)
        source = "stooq"
    except Exception as e:
        print(f"Stooq fetch failed ({e}), falling back to yfinance...", file=sys.stderr)
        df = fetch_yfinance(args.start, args.end)
        source = "yfinance"

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH)
    print(f"Wrote {len(df)} rows ({df.index.min().date()} to {df.index.max().date()}) "
          f"from {source} -> {OUT_PATH}")


if __name__ == "__main__":
    main()
