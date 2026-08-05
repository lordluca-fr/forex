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

## Broker for live/paper execution (Singapore, MAS-regulated)
Two realistic options, not yet chosen:
- **OANDA Singapore** — MAS-regulated, REST v20 API (what FXBot/tpqoa use),
  headless-friendly, no terminal required.
- **Interactive Brokers Singapore** — MAS-regulated, already have an account
  (used for TigerTrading US stocks) — check whether FX trading permissions can
  just be enabled on the existing account before opening anything new with OANDA.
