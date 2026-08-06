# Decisions

## 2026-08-04/05: Default branch → master
Repo created with `main` as default; switched to `master` to match
`second-brain` and `misc-projects` convention. Old `main` branch to be deleted
once `master` is confirmed as default everywhere (GitHub UI + local clones).

## Platform candidates evaluated (not yet chosen)

Reviewed public GitHub forex strategy/platform code as a base, prioritizing
fit with existing infra: headless daemon on Mac Mini (primary) + NAS
(failover standby, systemd/launchd), Telegram bot notifications, Python-first
(matches TigerTrading).

Ruled out:
- **MQL5/MT4/MT5 EAs** (`geraked/metatrader5`, `Mo-Khalifa96/Forex-Trading-Bot`) —
  require the MetaTrader terminal running persistently. No real Linux/Synology
  story, breaks the NAS-as-standby-failover pattern TigerTrading relies on.
- **StockSharp** — most active/credible project (10.5k★, dedicated OANDA
  connector) but C#/.NET. None of the existing Python daemon/Telegram/failover
  scripts carry over. Untested here: no .NET SDK in the dev sandbox and the
  dotnet-install host was also network-blocked, so this still needs a real
  eval on the Mac Mini (has both internet + can install the SDK).

Still in contention:
- **FXBot** (`trentstauff/FXBot`, Python + OANDA v20 REST API) — architecture
  matches TigerTrading almost exactly (headless REST-API daemon, no GUI/terminal).
  Vectorized pandas backtest engine. Caveats: `Backtester.acquire_data()` is
  hardwired to OANDA live fetch (no offline/CSV data path — had to monkeypatch
  it for the smoke test below), no published backtest results, "educational
  purposes only" disclaimer, only 116 commits.
- **lumibot** (`Lumiwealth/lumibot`, Python) — actively maintained (1.9k★),
  native `PandasDataBacktesting` + `Asset(asset_type="forex")` support, built-in
  Telegram notification hooks, rich output (CAGR/Sharpe/max DD/vol) out of the
  box. OANDA-specific broker connector unconfirmed — forex is a supported asset
  class but not tied to a documented live forex broker in the docs reviewed.

## Engineering smoke test (2026-08-05, sandboxed dev session — no real market data)

Real forex data (Yahoo/Stooq/OANDA) and a .NET toolchain were unreachable from
the dev sandbox (outbound proxy only allowlists pypi/github-style domains), so
this was **not** a performance/edge test — just a check that each engine
actually runs, on identical synthetic (seeded random-walk) EUR/USD-like data,
same SMA(20,50) crossover logic. Scripts: `research/fxbot_smoke_test.py`,
`research/lumibot_smoke_test.py`.

| | FXBot | lumibot |
|---|---|---|
| Engine | Vectorized (pandas/numpy) | Event-driven (`on_trading_iteration`) |
| Runtime, 732 daily bars | 0.01s | 17.3s (~1700x slower) |
| Offline/CSV data path | None natively (monkeypatched for this test) | Native, worked as documented |
| Hidden network calls in "offline" backtest | None | Yes — silently tried Yahoo Finance for `^IRX` risk-free rate 3x, failed quietly, continued. Harmless with real internet (Mac Mini/NAS), but not truly airgapped. |

Why runtime matters here: TigerTrading's research process leans on large
sweeps (e.g. "~400 backtests" for the Delta v4 follow-ups; `SMABacktest.optimize()`
does a 40x152 grid search in one vectorized pass). At lumibot's per-run cost
that grid would take hours instead of seconds — matters if we want the same
PIT-honest walk-forward discipline (many backtests, not one trusted number)
carried over from TigerTrading.

**Status: undecided.** Next step is a real test with actual historical
EUR/USD data and, ideally, a StockSharp eval — both need to happen on the Mac
Mini (has real internet + can install .NET), not this sandbox.

## Mac Mini environment setup (2026-08-05)

Both prerequisites for a real test are now in place:

- **Real EUR/USD data**: `backtest/fetch_data.py` fetches daily OHLC to
  `backtest/data/eurusd_daily.csv` (gitignored, regenerable). 3016 rows,
  2015-01-01 to 2026-08-04, sourced from yfinance — **Stooq (the intended
  primary source) turned out to be unusable**: `stooq.com/q/d/l/` now serves
  a JS proof-of-work bot-check page with an HTTP 200 (so a status-code-only
  reachability check, which is what the original DECISIONS.md research and
  this repo's initial curl test both did, is silently fooled — the script's
  `raise_for_status()` doesn't catch it, only the missing `Date` column
  does). yfinance is the working path until/unless a browser-capable
  scraper or an official Stooq API key is worth the effort.
- **dotnet SDK 10.0.302** installed via `brew install dotnet` (formula, not
  the `dotnet-sdk` cask) — `/opt/homebrew/bin/dotnet`, already on PATH, no
  `DOTNET_ROOT` export needed for CLI use despite the brew caveat (that
  caveat is for *other* software locating the runtime, not for running
  `dotnet` itself).
- **Landmine**: the Mac Mini's system `python3` (Homebrew, 3.14.5) SIGBUSes
  (exit 138) on `yfinance.download()` — pandas/numpy's compiled wheels
  aren't stable on 3.14 on this Apple Silicon build yet. Fixed by creating
  `~/forex-env` (python3.12 venv, matches TigerTrading's `tigertrading-env`
  pattern) — **use `~/forex-env/bin/python`, not system `python3`, for
  anything touching pandas/numpy/yfinance on the Mac Mini.**

## Real-data run + FXBot/lumibot reconciliation (2026-08-06)

`backtest/runners/runner_fxbot_sma_real.py` / `runner_lumibot_sma_real.py`,
real EUR/USD 2015-01-01 to 2026-08-04, same SMA(20,50):

| | FXBot | lumibot |
|---|---|---|
| CAGR | 0.53% | 1.90% |
| Sharpe | 0.07 | -0.10 |
| Max DD | -19.5% | -39.3% |

**SMA(20,50) alone is not viable** — near-zero/negative Sharpe on both.

The two engines' numbers disagree, but **reconciliation confirmed this is
not a bug**: pulled FXBot's day-by-day position series and lumibot's real
order fills (via its native `trades_file=` param) and compared flip dates
directly — all 68 flips land on the exact same date and direction on both
engines, 11.5 years, zero mismatches. The gap is entirely in P&L
accounting: FXBot compounds an idealized continuous log-return position
(fast, no realistic constraints); lumibot executes real sell-then-buy
orders off actual cash balance each flip (slow, closer to what a live
broker would actually do). Full writeup:
`SecondBrain/Projects/Forex/Experiments.md` (2026-08-06 entry).

**Working conclusion**: use FXBot for fast/wide parameter sweeps (relative
ranking), validate promising candidates in lumibot before considering
live/paper deployment. Don't trust FXBot's absolute Sharpe/CAGR as a
live-trading estimate.

## Broker for live/paper execution (Singapore, MAS-regulated)
Two realistic options, not yet chosen:
- **OANDA Singapore** — MAS-regulated, REST v20 API (what FXBot/tpqoa use),
  headless-friendly, no terminal required.
- **Interactive Brokers Singapore** — MAS-regulated, already have an account
  (used for TigerTrading US stocks) — check whether FX trading permissions can
  just be enabled on the existing account before opening anything new with OANDA.
