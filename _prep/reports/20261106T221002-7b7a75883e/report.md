# Arena experiment 20261106T221002-7b7a75883e

SYNTHETIC / EXAMPLE DATA

Family: market; seed: 7

| Observed metric | Value |
|---|---:|
| best_pnl | 29.28 |
| steps | 300 |
| strategies | 8 |

Source: experiments/20261106T221002-7b7a75883e/result.json
Dataset SHA-256: a2804ccbe944384b3e748d687b713c636655d973db3f2ec2bddf85edaa54265f
Source SHA-256: f9a8d24a2cc9e6683898ae67a9df49c04c31f045c8bfe0d9cfa0d35839cf803a

This run is preparation evidence, not official evaluation or demonstrated trading edge.
Next: test on the official metric, legal data, independent seeds and pessimistic fill assumptions.

## Assumptions and warnings

- Synthetic single-instrument mock exchange; not Qminers scoring or live evidence.
- All strategies receive identical exogenous snapshots and aggressive trade flow.
- One-event order latency; quotes cancelled after one event; partial fills capped by event volume.
- Passive fills assume front-of-queue priority; no real queue information is available.
- Final inventory is marked to mid; liquidation spread/cost is not included.
- Cancellation acknowledgements are fill barriers; actual API ordering must be reconciled.
- Best strategy is selected on this scenario, not an untouched evaluation set.
