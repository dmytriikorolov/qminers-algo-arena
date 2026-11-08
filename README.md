# Trading research sandbox

Replay strategies against recorded market events with the exchange simulator, then inspect runs with the backtest explorer. Python 3.13 is required.

```bash
uv sync --locked
uv run exchange-simulator --strategy strategies/adaptive_ml_regime.py --backtest data/round2_public.csv --log-dir logs/adaptive_ml_regime --no-logs
```

Choose another file from `strategies/` to run an alternative. The simulator reads uncompressed CSV files.

## Retained strategies

| File | Purpose and existing evidence |
|---|---|
| `adaptive_ml_regime.py` | Final Round 2 reference: two-sided quoting, embedded ridge risk forecast, crash/recovery inventory centers and passive fades. Verified public 6,000-second PnL: **198,279**. |
| `capacity_inventory_cycler.py` | Different approach: one-sided inventory cycling with queue preservation and no return/risk predictor. Recorded full Round 1 PnL: **301,402**; Round 2: **-236,525**. |
| `full_two_sided.py` | Compact baseline: full inventory-adjusted capacity on both sides with a simple imbalance gate. Historical source notes report approximately **458k on Round 1**; not rebenchmarked during cleanup. |

Scores from different tapes or durations are not directly comparable. The ridge weights were fitted on public Round 2 data; its public score is not an independent holdout. The final reference also has a known fast-requote race: its verified public replay incurred a **50-unit inventory-breach penalty**. Retained strategy code is unchanged.

Historical source, results and research are recoverable from local pre-cleanup Git commit `c98e28d`.

## Inspect a run

Create a run with full logs, then launch the explorer:

```bash
uv run exchange-simulator --strategy strategies/full_two_sided.py --backtest data/sample.csv --log-dir logs/explorer-demo
uv run backtest-explorer --log-dir logs/explorer-demo
```

Open http://127.0.0.1:8050. Runs made with `--no-logs` retain `result.json`, `metadata.json` and the one-second `pnl.csv`, but lack the detailed logs the explorer needs.

## Market mechanics

- Prices are integer ticks; matching uses price-time FIFO priority.
- Orders, cancels and quantity reductions take effect after **5 ms**. Pending exposure still matters.
- Snapshots include our orders; use `owner == 'market'` for market-owned quotes.
- Inventory beyond **±100** incurs a penalty of 10,000 per second. Order acceptance allows potential exposure up to ±1,000; that is not the penalty-free limit.
- PnL includes cash, terminal inventory liquidation against market depth, and breach penalties. There are no fees.

A strategy file defines one `BaseStrategy` subclass with `on_order_book_change` and `on_private_order_update`; see `simulator/strategy.py` and the retained examples. Callbacks occur on market events, including during liquidity changes; silence does not create callbacks.

## Layout

```text
data/        Original round1.csv, round2_public.csv, sample.csv, sample.csv.gz, sample_v2.csv
strategies/  Three retained standalone strategies
simulator/   Replay, matching engine, strategy interface and CLI
explorer/    Backtest dashboard and assets
pyproject.toml, uv.lock, .python-version, .gitignore, README.md
```

Original datasets stay local; generated runs belong in Git-ignored `logs/`. The original `sample.csv.gz` is tracked, and `sample.csv` contains the same uncompressed data.
