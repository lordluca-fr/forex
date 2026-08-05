"""
Engineering smoke test for FXBot's backtesting engine.

FXBot's Backtester.acquire_data() is hard-wired to call tpqoa -> OANDA's live
API for historical candles. The dev sandbox this was first run in had no
network path to OANDA, so acquire_data() is monkeypatched here to hand it a
synthetic (non-real) price series instead. This proves the vectorized
test()/optimize() engine actually runs and says nothing about real strategy
edge -- that's the point of this being a "smoke test" and not a "performance
test". Run this on a machine with real OANDA/oanda.cfg access (Mac Mini) and
swap in real get_history() data for an actual read.

Usage: place this file inside a checkout of https://github.com/trentstauff/FXBot
(needs FXBot's own `backtesting` package importable) and run:
    pip install pandas numpy matplotlib scikit-learn v20
    pip install git+https://github.com/yhilpisch/tpqoa.git
    python fxbot_smoke_test.py
"""
import time
import numpy as np
import pandas as pd

from backtesting.Backtester import Backtester
from backtesting.SMABacktest import SMABacktest


def make_synthetic_series(start, end, seed=42, mu=0.0, sigma=0.006):
    """Reproducible GBM-like daily 'price' series, same shape FXBot expects."""
    dates = pd.bdate_range(start=start, end=end)
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(loc=mu, scale=sigma, size=len(dates))
    price = 1.10 * np.exp(np.cumsum(log_returns))  # start near a plausible EURUSD level
    df = pd.DataFrame({"price": price}, index=dates)
    df["returns"] = np.log(df["price"] / df["price"].shift(1))
    df.dropna(inplace=True)
    return df


def synthetic_acquire_data(self):
    return make_synthetic_series(self._start, self._end)


def main():
    Backtester.acquire_data = synthetic_acquire_data  # patch out the OANDA call

    t0 = time.perf_counter()
    bt = SMABacktest("EUR_USD (SYNTHETIC)", "2021-01-01", "2024-01-01", smas=20, smal=50,
                      granularity="D", trading_cost=0.0001)
    performance, out_performance = bt.test()
    elapsed = time.perf_counter() - t0

    trades = int(bt.get_results()["trades"].sum())
    n_bars = len(bt.get_results())

    print("\n--- FXBot (SMABacktest) smoke test result ---")
    print(f"engine runtime: {elapsed:.4f}s for {n_bars} bars")
    print(f"total return: {round(performance * 100 - 100, 2)}%")
    print(f"out-performance vs buy&hold: {round(out_performance * 100, 2)}%")
    print(f"trades: {trades}")
    print("NOTE: synthetic random-walk data, not real EUR/USD -- signal-free by construction.")


if __name__ == "__main__":
    main()
