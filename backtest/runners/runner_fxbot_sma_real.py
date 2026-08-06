#!/usr/bin/env python3
"""Real-data run of FXBot's SMA(20,50) crossover on EUR/USD.

Same monkeypatch approach as research/fxbot_smoke_test.py (FXBot's
Backtester.acquire_data() is hardwired to a live OANDA call via tpqoa), but
loads backtest/data/eurusd_daily.csv (real history, see
backtest/fetch_data.py) instead of a synthetic random walk. This is what
that smoke test's docstring flagged as the actual follow-up: "says nothing
about real strategy edge -- run this on a machine with real data access".

Requires FXBot checked out at backtest/vendor/FXBot (backtesting/ package
importable) and its deps (v20, tpqoa, matplotlib, scikit-learn) installed.
On the Mac Mini: use ~/forex-env/bin/python (see DECISIONS.md -- system
python3 SIGBUSes on pandas/yfinance).

Usage: python3 backtest/runners/runner_fxbot_sma_real.py
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backtest" / "vendor" / "FXBot"))

DATA_PATH = REPO_ROOT / "backtest" / "data" / "eurusd_daily.csv"
RESULTS_ROOT = REPO_ROOT / "backtest" / "results"
LEADERBOARD = REPO_ROOT / "backtest" / "leaderboard.csv"

STRATEGY = "sma_crossover"
ENGINE = "fxbot"
SMAS, SMAL = 20, 50
TRADING_COST = 0.0001


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def real_acquire_data(self):
    df = pd.read_csv(DATA_PATH, index_col="Date", parse_dates=True)
    df = df[["Close"]].rename(columns={"Close": "price"})
    df = df.loc[self._start : self._end]
    df.dropna(inplace=True)
    df["returns"] = np.log(df["price"] / df["price"].shift(1))
    df.dropna(inplace=True)
    return df


def main():
    from backtesting.Backtester import Backtester
    from backtesting.SMABacktest import SMABacktest

    Backtester.acquire_data = real_acquire_data

    start, end = "2015-01-01", "2026-08-04"
    params = {"instrument": "EUR_USD", "start": start, "end": end,
              "smas": SMAS, "smal": SMAL, "granularity": "D", "trading_cost": TRADING_COST}
    params_hash = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]

    bt = SMABacktest("EUR_USD", start, end, smas=SMAS, smal=SMAL,
                      granularity="D", trading_cost=TRADING_COST)
    performance, out_performance = bt.test()
    results_df = bt.get_results()

    trades = int(results_df["trades"].sum())
    n_bars = len(results_df)
    cagr = performance ** (252 / n_bars) - 1 if n_bars > 0 else float("nan")
    daily_strategy_returns = results_df["strategy"]
    sharpe = (daily_strategy_returns.mean() / daily_strategy_returns.std()) * np.sqrt(252) \
        if daily_strategy_returns.std() > 0 else float("nan")
    cum = results_df["cstrategy"]
    max_dd = ((cum / cum.cummax()) - 1).min()

    run_id = f"{STRATEGY}__{ENGINE}__{params_hash}__{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run_manifest.json").write_text(json.dumps({
        "strategy": STRATEGY, "engine": ENGINE, "engine_type": "vectorized",
        "params": params, "params_hash": params_hash,
        "data_source": "yfinance (via backtest/fetch_data.py)", "data_path": str(DATA_PATH),
        "git_commit": git_commit(), "run_at": datetime.now().isoformat(),
    }, indent=2))

    metrics = {
        "total_return_pct": round(performance * 100 - 100, 4),
        "out_performance_pct": round(out_performance * 100, 4),
        "cagr_pct": round(cagr * 100, 4),
        "sharpe": round(float(sharpe), 4) if sharpe == sharpe else None,
        "max_dd_pct": round(float(max_dd) * 100, 4),
        "trades": trades,
        "n_bars": n_bars,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    results_df.to_csv(run_dir / "trades.csv")

    LEADERBOARD.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not LEADERBOARD.exists() or LEADERBOARD.stat().st_size == 0
    with open(LEADERBOARD, "a") as f:
        if header_needed:
            f.write("run_id,date,strategy,engine,params_hash,data_source,date_range,cagr,sharpe,max_dd,trades,git_commit,verdict\n")
        f.write(f"{run_id},{datetime.now().date()},{STRATEGY},{ENGINE},{params_hash},yfinance,"
                f"{start}:{end},{metrics['cagr_pct']},{metrics['sharpe']},{metrics['max_dd_pct']},"
                f"{trades},{git_commit()},\n")

    print(f"\n--- FXBot SMA({SMAS},{SMAL}) on real EUR/USD ({start} to {end}) ---")
    print(json.dumps(metrics, indent=2))
    print(f"Results written to {run_dir}")


if __name__ == "__main__":
    main()
