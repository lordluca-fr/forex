#!/usr/bin/env python3
"""Real-data run of lumibot's SMA(20,50) crossover on EUR/USD.

Same strategy logic as research/lumibot_smoke_test.py, but backed by
backtest/data/eurusd_daily.csv (real history) instead of a synthetic random
walk. Written as a separate runner (not editing the smoke test) so the
smoke test stays as the historical "does the engine even run" record.

On the Mac Mini: use ~/forex-env/bin/python (see DECISIONS.md -- system
python3 SIGBUSes on pandas/yfinance).

Usage: python3 backtest/runners/runner_lumibot_sma_real.py
"""
import hashlib
import json
import subprocess
import sys
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from lumibot.backtesting import PandasDataBacktesting
from lumibot.entities import Asset, Data, Order
from lumibot.strategies.strategy import Strategy

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PATH = REPO_ROOT / "backtest" / "data" / "eurusd_daily.csv"
RESULTS_ROOT = REPO_ROOT / "backtest" / "results"
LEADERBOARD = REPO_ROOT / "backtest" / "leaderboard.csv"

STRATEGY = "sma_crossover"
ENGINE = "lumibot"
SMAS, SMAL = 20, 50


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def load_real_ohlcv(start, end):
    df = pd.read_csv(DATA_PATH, index_col="Date", parse_dates=True)
    df = df.loc[start:end]
    df = df.rename(columns={"Close": "close", "Open": "open", "High": "high",
                             "Low": "low", "Volume": "volume"})
    df.index.name = "datetime"
    return df[["open", "high", "low", "close", "volume"]]


class SmaCross(Strategy):
    parameters = {"smas": SMAS, "smal": SMAL}

    def initialize(self):
        self.sleeptime = "1D"
        self.set_market("24/7")
        self.base = Asset(symbol="EUR", asset_type="forex")
        self.quote = Asset(symbol="USD", asset_type="forex")
        self.position_state = 0
        self.trade_count = 0

    def on_trading_iteration(self):
        smas, smal = self.parameters["smas"], self.parameters["smal"]
        bars = self.get_historical_prices(self.base, smal + 1, "day", quote=self.quote)
        if bars is None:
            return
        close = bars.df["close"]
        if len(close) < smal:
            return

        signal = 1 if close.rolling(smas).mean().iloc[-1] > close.rolling(smal).mean().iloc[-1] else -1
        if signal == self.position_state:
            return

        last_price = self.get_last_price(self.base, quote=self.quote)
        cash = self.get_cash()
        qty = round(abs(cash) / last_price, 0) if last_price else 0
        if qty <= 0:
            return

        if self.position_state != 0:
            side = Order.OrderSide.SELL if self.position_state == 1 else Order.OrderSide.BUY
            self.submit_order(self.create_order(self.base, qty, side=side, quote=self.quote))

        side = Order.OrderSide.BUY if signal == 1 else Order.OrderSide.SELL
        self.submit_order(self.create_order(self.base, qty, side=side, quote=self.quote))
        self.position_state = signal
        self.trade_count += 1


def main():
    start = datetime.datetime(2015, 1, 1)
    end = datetime.datetime(2026, 8, 4)
    params = {"instrument": "EUR_USD", "start": start.isoformat(), "end": end.isoformat(),
              "smas": SMAS, "smal": SMAL}
    params_hash = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]

    ohlcv = load_real_ohlcv(start, end)
    base = Asset(symbol="EUR", asset_type="forex")
    quote = Asset(symbol="USD", asset_type="forex")
    data = Data(base, ohlcv, date_start=start, date_end=end, timestep="day", quote=quote)

    result = SmaCross.backtest(
        datasource_class=PandasDataBacktesting,
        backtesting_start=start,
        backtesting_end=end,
        pandas_data=[data],
        quote_asset=quote,
        budget=10000,
        benchmark_asset=None,
        show_plot=False,
        show_tearsheet=False,
        save_tearsheet=False,
        show_indicators=False,
        save_logfile=False,
        show_progress_bar=False,
        quiet_logs=True,
        name="SmaCross-EURUSD-real",
    )

    run_id = f"{STRATEGY}__{ENGINE}__{params_hash}__{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run_manifest.json").write_text(json.dumps({
        "strategy": STRATEGY, "engine": ENGINE, "engine_type": "event_driven",
        "params": params, "params_hash": params_hash,
        "data_source": "yfinance (via backtest/fetch_data.py)", "data_path": str(DATA_PATH),
        "git_commit": git_commit(), "run_at": datetime.datetime.now().isoformat(),
    }, indent=2, default=str))

    # lumibot's result dict mixes raw fractions (cagr, total_return, volatility)
    # with a dict for max_drawdown ({'drawdown': <positive fraction>, 'date': ...})
    # -- normalize everything here to percentage floats matching FXBot's
    # metrics.json convention (cagr_pct, max_dd_pct as a *negative* number),
    # so the leaderboard is comparing like units, not raw dict reprs.
    raw_max_dd = result.get("max_drawdown") if result else None
    max_dd_pct = None
    if isinstance(raw_max_dd, dict) and "drawdown" in raw_max_dd:
        max_dd_pct = -float(raw_max_dd["drawdown"]) * 100
    elif isinstance(raw_max_dd, (int, float, np.floating)):
        max_dd_pct = -abs(float(raw_max_dd)) * 100

    def pct(key):
        v = result.get(key) if result else None
        return round(float(v) * 100, 4) if isinstance(v, (int, float, np.floating)) else None

    metrics = {
        "cagr_pct": pct("cagr"),
        "total_return_pct": pct("total_return"),
        "sharpe": round(float(result["sharpe"]), 4) if result and isinstance(result.get("sharpe"), (int, float, np.floating)) else None,
        "max_dd_pct": round(max_dd_pct, 4) if max_dd_pct is not None else None,
        "volatility_pct": pct("volatility"),
        "max_drawdown_date": raw_max_dd.get("date").isoformat() if isinstance(raw_max_dd, dict) and hasattr(raw_max_dd.get("date"), "isoformat") else None,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    LEADERBOARD.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not LEADERBOARD.exists() or LEADERBOARD.stat().st_size == 0
    with open(LEADERBOARD, "a") as f:
        if header_needed:
            f.write("run_id,date,strategy,engine,params_hash,data_source,date_range,cagr,sharpe,max_dd,trades,git_commit,verdict\n")
        f.write(f"{run_id},{datetime.datetime.now().date()},{STRATEGY},{ENGINE},{params_hash},yfinance,"
                f"{start.date()}:{end.date()},{metrics.get('cagr_pct','')},{metrics.get('sharpe','')},"
                f"{metrics.get('max_dd_pct','')},,{git_commit()},\n")

    print(f"\n--- lumibot SMA({SMAS},{SMAL}) on real EUR/USD ({start.date()} to {end.date()}) ---")
    print(json.dumps(metrics, indent=2))
    print(f"Results written to {run_dir}")


if __name__ == "__main__":
    main()
