"""
Engineering smoke test for lumibot's backtesting engine (PandasDataBacktesting).

Same synthetic (non-real) EUR/USD-like price series as fxbot_smoke_test.py,
same SMA(20,50) crossover logic, so the two engines are exercised on
identical data. This tests that lumibot's event-driven backtester actually
runs end-to-end for a forex pair -- it says nothing about real strategy edge.

Usage:
    pip install lumibot
    python lumibot_smoke_test.py
"""
import time
import datetime
import numpy as np
import pandas as pd

from lumibot.backtesting import PandasDataBacktesting
from lumibot.entities import Asset, Data, Order
from lumibot.strategies.strategy import Strategy


def make_synthetic_ohlcv(start, end, seed=42, mu=0.0, sigma=0.006):
    """Same generator as fxbot_smoke_test.py so both engines see identical data."""
    dates = pd.bdate_range(start=start, end=end)
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(loc=mu, scale=sigma, size=len(dates))
    close = 1.10 * np.exp(np.cumsum(log_returns))
    df = pd.DataFrame(index=dates)
    df.index.name = "datetime"
    df["close"] = close
    df["open"] = df["close"].shift(1).fillna(df["close"].iloc[0])
    df["high"] = df[["open", "close"]].max(axis=1) * 1.0005
    df["low"] = df[["open", "close"]].min(axis=1) * 0.9995
    df["volume"] = 0
    return df[["open", "high", "low", "close", "volume"]]


class SmaCross(Strategy):
    parameters = {"smas": 20, "smal": 50}

    def initialize(self):
        self.sleeptime = "1D"
        self.set_market("24/7")
        self.base = Asset(symbol="EUR", asset_type="forex")
        self.quote = Asset(symbol="USD", asset_type="forex")
        self.position_state = 0  # -1 short, 0 flat, +1 long
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

        # flatten existing exposure before flipping
        if self.position_state != 0:
            side = Order.OrderSide.SELL if self.position_state == 1 else Order.OrderSide.BUY
            self.submit_order(self.create_order(self.base, qty, side=side, quote=self.quote))

        side = Order.OrderSide.BUY if signal == 1 else Order.OrderSide.SELL
        self.submit_order(self.create_order(self.base, qty, side=side, quote=self.quote))
        self.position_state = signal
        self.trade_count += 1


def main():
    start = datetime.datetime(2021, 1, 1)
    end = datetime.datetime(2024, 1, 1)
    ohlcv = make_synthetic_ohlcv("2021-01-01", "2024-01-01")

    base = Asset(symbol="EUR", asset_type="forex")
    quote = Asset(symbol="USD", asset_type="forex")
    data = Data(base, ohlcv, date_start=start, date_end=end, timestep="day", quote=quote)

    t0 = time.perf_counter()
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
        name="SmaCross-Synthetic",
    )
    elapsed = time.perf_counter() - t0

    print("\n--- lumibot (PandasDataBacktesting, SMA 20/50) smoke test result ---")
    print(f"engine runtime: {elapsed:.2f}s")
    if result:
        for k in ("cagr", "total_return", "sharpe", "max_drawdown", "volatility"):
            if k in result:
                print(f"{k}: {result[k]}")
    print("NOTE: synthetic random-walk data, not real EUR/USD -- signal-free by construction.")


if __name__ == "__main__":
    main()
