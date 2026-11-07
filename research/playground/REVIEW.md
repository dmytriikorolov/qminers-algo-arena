# Independent adversarial review

Reviewed `README.md`, official simulator models/base strategy/matching engine/CLI,
`strategies/trend_follower.py`, both Playground candidates, the experiment harness,
selection record, and recorded results. No official simulator or strategy files
were changed by this reviewer.

## Verdict

No blocking state-management or risk defect found in either candidate. The frozen
flow candidate is supported for the supplied synthetic Playground dataset only.
The evidence does not establish profitability on recorded market rounds.

The original example has a concrete failure: its canceled/rejected IOC never
clears `_order_in_flight`, permanently preventing further orders. An independent
seven-row official-engine reproduction confirmed this. The new flow candidate
handles those terminal events and accounts for each actual partial fill.

## Independent verification

Run from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p test_playground_review.py -v
.venv/bin/python -m simulator.main --strategy strategies/playground_flow.py --backtest data/sample.csv --log-dir /private/tmp/qminers-review-cli --no-logs
```

Observed: all six integration tests pass. Tests cover an IOC miss followed by a
retry, partial-fill/cancel inventory, a quote fill beating its cancel followed by
a cancel rejection, capacity reserved before acceptance, activation during a
sparse tape, and eight bounded randomized runs. Every private callback checks the
position cap; quote snapshots also check both sides' outstanding exposure.
Final strategy inventory agrees with the official engine. These are mechanics
tests, not profitability tests.

The independent CLI result exactly matches `candidate_full.json`: PnL 21,434;
cash 61,586; final inventory -4; liquidation mark 10,038; traded volume 3,430;
301 filled order IDs; breach penalty zero. Source/data SHA-256 hashes also match.
The arithmetic is `61,586 + (-4 * 10,038) = 21,434`.

Recomputed from the independent CLI's `pnl.csv`: chronological 20-minute PnL
increments are 7,951 / 8,484 / 4,999, totaling 21,434. The 2400-second continuous
mark is 16,435, identical to the development-prefix EOF result: boundary
flush difference is zero here. Maximum drawdown on the recorded one-second PnL
samples is 554. This does not measure every intrasecond drawdown.

## Traps checked

- An action activates at its scheduled ready time against the preceding book,
  before the next eligible market event. The sparse-tape test confirms a request
  sent at 1 ms fills at 6 ms even when the next event is at 1 second.
- IOC acceptance is followed by per-match partial/full updates and potentially a
  cancel carrying an unfilled residual. Inventory uses actual filled quantity.
- A rejected cancel can follow an already-filled order. It must not resurrect
  that order or remove another live reservation. Quote canceling quantity stays
  reserved until a terminal update.
- Public books contain user quotes and public trades contain user fills. The
  candidates filter market orders; flow also filters market-vs-market trades.
- The CLI hard rejection limit is 1000 potential units; the costly inventory
  threshold is 100. Direct-engine tests explicitly use CLI limits and penalty,
  rather than the engine's unrestricted defaults. The selected strategy caps
  its own exposure at 20.
- Final inventory is liquidated against market book depth, not marked at mid.
  `fills` counts distinct filled order IDs, not individual matches. `pnl_se`
  summarizes sampled PnL variation; it does not correct for strategy selection.

## Limits of the selection evidence

The supplied sample is deliberately generated with directional continuation
after trades, as its README explains. The organizer-confirmed Playground dataset
being that same sample makes this a relevant local optimization target, but does
not make it representative recorded market data. Flow sizing 1/5/10/20 scales a
shared signal; it is not four independent discoveries. Quote ablations do not
independently validate that signal.

The selection record freezes LOT=20, LIMIT=20, MAX_SPREAD=4 before evaluating the
full-size candidate. However, full-sample baseline and LOT=1 flow performance had
already been observed. The final 20 minutes are therefore a post-freeze sizing
check, not wholly unseen data at the strategy-family level. The blocks also
share one synthetic generator and continuous inventory; they are not independent
replications. No further tuning based on the final block is justified by this
review. No real-market holdout, external submission, or sandbox-runtime execution
was performed by this reviewer.
