# Offline market toolkit

`src/arena/trading.py` is a small learning exchange, not the Qminers adapter.
It uses Python's standard library and never connects to a service. No strategy
has been evaluated on competition data.

Run from this kit's directory:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_trading.py -v
PYTHONPATH=src python3 -c 'from arena.trading import demo; import json; print(json.dumps(demo(seed=7, steps=300)["metrics"], indent=2))'
```

## What works

`Snapshot` validates crossed, empty and invalid books. `MarketFeatures` computes
midprice, spread/ticks/bps, top-level imbalance, microprice, causal rolling mean,
returns and volatility. Duplicate, future and stale snapshots are rejected
before history changes. Its window counts return observations, so it holds up
to `window + 1` midprices. It does not infer order-flow events or queue positions
from snapshots.

`Ledger` checks tick/lot sizes, positive integer quantities, own-order crosses
and worst-case position exposure. Buy and sell orders reserve independently;
they cannot cancel each other's risk because only one side might fill.
Pending orders and cancellation requests retain their reservation. Every fill
has a unique execution ID; exact repeats do nothing and conflicting repeats
raise an error. Executions are incremental quantities, not cumulative status
quantities. Decimal accounting tracks cash, average entry, gross realized PnL,
fees/rebates, unrealized PnL and marked equity. Reported realized PnL subtracts
all fees incurred so far, including fees on still-open positions.

Example: buy four units at 99.5, sell three at 102, mark the last at 101. Gross
realized gain is 7.5, unrealized gain is 1.5, and total gain is 9 before fees.
Every replay is checked against the cash-plus-position accounting identity.

## Mock execution assumptions

- Eight policies share identical seeded exogenous events: no-op, fixed quotes,
  rolling fair-value quotes, inventory-skewed quotes, microprice-skewed quotes,
  momentum, mean reversion and a threshold taker.
- Orders become executable on the next event. Resting quotes receive flow only
  when an external aggressive trade crosses the limit. A partial fill cannot
  exceed event volume. An aggressive order also requires a valid next displayed
  executable price and available displayed depth.
- Passive orders receive all available matching flow as if first in queue.
  This is optimistic; there is no queue estimate or market-impact model.
- Remaining orders are cancelled after that event. Cancellation acknowledgement
  is a **fill barrier**: all earlier fills must be processed before it releases
  exposure. A late acknowledgement cannot revive an order. The ledger accepts
  fills racing a cancel request and rejects unseen fills after terminal state.
  An actual API with different ordering needs explicit reconciliation first.
- Final inventory is marked to midprice, without liquidation costs. Fees can be
  positive costs or negative rebates. No-op starts with zero inventory/cash.
- A selected winner is the best on this synthetic path, not a held-out result.

Use `regime="trend"`, `"shock"` or `"mean_reverting"` and independent seeds to
test whether conclusions survive different paths. The replay does not support
multiple instruments, order-book reconstruction, auctions or live API traffic.

## Next step when the official specification arrives

Run the untouched official baseline. Replace mock execution with the actual
adapter only after documenting callback ordering, cumulative vs incremental
fills, fees/rebates, cancellation semantics, timestamps and exposure rules.
Replay official fills through accounting tests before tuning a strategy.
