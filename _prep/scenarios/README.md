# Example data only

All `*_example.csv` files in this directory are hand-written synthetic teaching examples, not observed market data or Qminers inputs. `market-features` treats their values as caller-supplied observations for feature calculation; it does not independently establish origin or simulate our executions.

```bash
.venv/bin/arena market-features scenarios/snapshots_example.csv --kind snapshots
.venv/bin/arena market-features scenarios/bars_example.csv --kind bars
.venv/bin/arena market-features scenarios/trades_example.csv --kind trades --window 2
```

The blank trade side is deliberately unknown. Signed flow must remain unavailable for any window containing it. See `docs/MARKET_DATA.md` for exact schemas and limits.
