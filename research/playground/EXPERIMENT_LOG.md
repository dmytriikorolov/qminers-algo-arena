# Playground experiment log — 2026-11-07

Official simulator is unchanged. Python 3.13; 5 ms order/cancel/modify latency,
public depth 20 ticks, hard potential-position limit 1000, penalty threshold 100,
penalty 10,000/second. No fees. JSON records include data/source hashes,
parameters, official results, lifecycle counts, maximum inventory and reserved
position, minimum fill latency, and sampled drawdown. `provenance.json` records
the simulator hashes and installed dependency versions.

## Initial compatibility runs

Whole supplied sample: untouched example and new flow LOT1 both PnL 1878;
quotes LOT2/cap10 PnL 8, volume 84, final inventory 0. These initial full-tape
results were inspected before the sizing sweep. Thus the later block is a
post-freeze sizing check, not entirely unseen strategy-family validation.
Original CLI artifacts: `logs/playground/{example,flow,quotes}/result.json`.

## Development sweep (original stream through 2400 s)

The same market rows and official configuration are used for every policy.
Do not repeat these failed quoting variants unless a new dataset or a specific
execution hypothesis justifies doing so.

| Run / change | PnL | Filled orders | Volume | Max abs inventory | Sampled drawdown | Penalty |
|---|---:|---:|---:|---:|---:|---:|
| Untouched official example | 1259 | 195 | 195 | 1 | 16 | 0 |
| No-op control | 0 | 0 | 0 | 0 | 0 | 0 |
| Flow LOT1, corrected state | 1259 | 195 | 195 | 1 | 16 | 0 |
| Flow LOT5 | 6115 | 195 | 967 | 8 | 240 | 0 |
| Flow LOT10 | 11187 | 195 | 1713 | 20 | 554 | 0 |
| Flow LOT20 | 16435 | 193 | 2232 | 20 | 554 | 0 |
| Quotes: microprice/volatility/skew, LOT2/cap10 | 48 | 28 | 56 | 2 | 154 | 0 |
| Quotes: no microprice signal | 68 | 43 | 86 | 4 | 240 | 0 |
| Quotes: no volatility widening | 48 | 28 | 56 | 2 | 154 | 0 |
| Quotes: cap5 | 48 | 28 | 56 | 2 | 154 | 0 |

Selection: LOT20 flow, still cap20, frozen in `SELECTION.md` before its final
20-minute evaluation. It beats LOT10 in both development blocks with the same
observed maximum exposure and drawdown. This is sizing of the same flow signal;
it is not a risk-normalized comparison or evidence of distinct alpha. Quotes
send roughly 8,700 orders on the prefix for little gain; no-signal improves their
result, and volatility/cap ablations add no observed benefit. Keep the code for
later recorded-data research; do not submit it on this evidence.

## Frozen full replay

| Policy | 0–20m PnL | 20–40m PnL | Final 20m PnL | Total PnL |
|---|---:|---:|---:|---:|
| Official | 644 | 615 | 619 | 1878 |
| No-op | 0 | 0 | 0 | 0 |
| Flow LOT20/cap20 | 7951 | 8484 | 4999 | 21434 |

Blocks are changes in the official liquidatable-inventory PnL of a continuous
full replay; orders and inventory are not reset at boundaries. Prefix EOF
drains pending actions; the selected candidate's prefix score and the full
replay's 2400s mark are identical (16435), so this causes no measured split
discrepancy here. Full candidate sampled drawdown 554; baseline 16.

Candidate: 301 accepted, 243 partial fill events, 58 fully filled orders, 243
IOC residual cancellations, no rejects. 301 distinct orders received fills,
3430 units traded, final inventory -4. Minimum send-to-fill latency 5000us.
Maximum observed absolute inventory and pending-inclusive potential position
both 20; time above the penalty threshold is zero. Time-weighted abs inventory
q50/q68/q95/q99.7 = 8/12/20/20. No LIMIT residuals/cancel requests are used by
this candidate. Cash 61586 minus liquidation liability 40152 = 21434.

All totals reproduced with the official CLI, both with and without full logs.
Full logs for inspection: `logs/playground/candidate_full_logs/`.
`pnl_se=1719.13` is the simulator's increment-based statistic; it does not
measure selection bias, independent sample uncertainty, or real-market edge.

## Reproduction

```bash
.venv/bin/python -m scripts.playground_experiments --stage development
.venv/bin/python -m scripts.playground_experiments --stage frozen
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.check_playground_submission strategies/playground_flow.py strategies/playground_quotes.py
```

The research harness uses engine internals only to measure execution, never in
submitted files. It sets the exact CLI risk/latency configuration explicitly;
bare `SimulationConfig()` would disable the limits/penalty and is not a valid
competition backtest. Deterministic reruns are reproduction, not new evidence.
