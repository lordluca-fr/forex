# Backtest folder convention

Mirrors TigerTrading's split (code tracked in git, raw results are not —
`backtest/results*.json` is gitignored there too) but organizes each run
into its own folder instead of flat files at the results root, and adds a
tracked leaderboard so run history survives without committing raw
artifacts.

```
backtest/
  engines/      Adapter/wrapper code per platform (fxbot_adapter.py, lumibot_adapter.py, ...). Tracked.
  runners/      One entrypoint script per experiment (e.g. runner_sma_crossover.py). Tracked.
  data/         Cached historical OHLCV (CSV/parquet/pickle). Gitignored — large, regenerable from the broker/source.
  results/      Raw per-run output, one folder per run (see below). Gitignored — backed up to the NAS instead, not to git.
  leaderboard.csv   One row per run. Tracked — this is the small, durable record git keeps even though results/ isn't.
```

## Per-run folder

Each run writes to `results/<strategy>__<params-hash>__<YYYYMMDD-HHMMSS>/`:

- `run_manifest.json` — exact params, git commit hash, data range/source, engine+version. Reproducibility: given this file alone, the run can be redone.
- `metrics.json` — CAGR, Sharpe, max drawdown, volatility, trade count, out-performance vs buy&hold.
- `trades.csv` — trade-level log.
- `equity_curve.csv` — optional, for plotting.

## leaderboard.csv

Every run appends one row (strategy, params-hash, date range, key metrics,
folder name, git commit, verdict). This is what makes `git log` on this repo
show the shape of the search over time even though the heavy per-run
artifacts live only on the Mac Mini (primary) and NAS (backup via
`scripts/sync_results_to_nas.sh`, 5-min rsync mirror), not in git.

**Settled verdicts** (not just raw numbers) go to the Second Brain vault:
`SecondBrain/Projects/Forex/Experiments.md` — append there when a run
answers "is this strategy/platform suitable," so no one re-runs a
question that's already been decided. Raw numbers stay here; the "so what"
goes there.
