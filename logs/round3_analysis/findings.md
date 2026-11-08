# Round 3 public-tape analysis

1. Round 3 is more volatile and thinner than round 2: 1 s RMS returns are 4.48 vs 3.79 ticks; median thinner-side L1 is 210 vs 300 lots.

2. Tail risk matters more than the net move: the mid ends -128 ticks from its initial value, but the worst peak-to-trough decline is 365.5 ticks. The largest 1% of one-second returns contribute 58.6% of squared returns.

3. Spread capture deteriorates quickly after a fill. Historical maker fills mark out at -0.907 ticks per lot after one second. Their fill selection and queue position differ from a newly submitted strategy order.

4. Order-book imbalance and recent aggressive flow have short-lived directional information. The one-second moves do not cover the estimated round-trip spread; they are more plausible quote-skew or inventory inputs than standalone crossing signals.

5. A 30 s move exceeding 5 ticks tends to reverse over the next 10 s in both halves. Held-out fade gross edge is 2.57 ticks and spread-adjusted diagnostic edge is 1.24 ticks (95% block interval -0.45 to 3.20). This is exploratory: overlapping decisions, multiple tested horizons, no queue, depth, inventory, or 5 ms execution simulation.

6. The unchanged adaptive reference earns 83,411, including 50 in penalties; first half 55,157, second half 28,254. This is public-tape evidence, not a private-round score.

7. Spread widening is a useful risk warning: after a last-second average spread of at least 2 ticks, the held-out chance of a >=10-tick one-second move in the next ten seconds is 55.6%, versus 21.7% overall. The warning covers only 4.5% of eligible held-out seconds, so it misses many jumps.

8. Risk sizing drives the adaptive strategy's protection. With inventory biases disabled in both runs, adaptive sizing earns 86,059, while forcing full size loses 457,320. Removing crash/recovery bias while keeping the original fade earns 90,650; treat this as an ablation result, not a newly validated strategy choice.

## Unchanged strategy results

strategy,pnl,first_half_pnl,second_half_pnl,breach_penalty,max_pnl_drawdown
Adaptive reference,83411.0,55157.0,28254.0,50.0,9613.0
Inventory cycler,-431110.0,-193110.0,-238000.0,0.0,436718.0
Two-sided baseline,-511767.0,-223873.0,-287894.0,0.0,517430.0


## Fixed ablations

Variant,PnL,First half,Second half,Max drawdown,Penalty,Volume
Adaptive reference (trace check),83411.0,55157.055845,28253.944154999997,9613.0,50.0,612392
No crash/recovery or fade bias,86059.0,45835.91349499999,40223.08650500001,2784.0,50.0,767928
No 300 s fade bias,73777.0,57082.055845,16694.944154999997,9613.0,50.0,609744
No crash/recovery bias; keep fade,90650.0,38604.91349499999,52045.08650500001,5360.0,50.0,773174
"Full size, no inventory bias",-457320.11,-195390.50650500003,-261929.60349499996,465512.11,2435.1099999999997,1412208


## Method and limitations

Sources: local round1.csv (200 minutes), round2_public.csv and round3_public.csv (100 minutes each). SHA-256 fingerprints are stored in summary.json. All price units are integer ticks; PnL is ticks multiplied by lots, with no currency assumption.

The repository's matching engine replays every insert/cancel in original order. F means immediate-or-cancel; G can match immediately and rests any remainder. Cancels of already-filled IDs are legitimate no-ops, not missing-data errors. No strategy is attached to the market-only reconstruction.

Quantity conservation is checked on every full tape: inserted quantity = twice executed quantity + canceled resting quantity + unfilled IOC quantity + final resting quantity. All three residuals are zero. Two executed legs are counted because both the maker and taker lose that quantity.

Quotes and depths are sampled every 100 ms from events strictly before the grid time. No interpolation or backfill from future events. Depth is visible quantity at the best price; 5-tick depth includes empty ticks. Mean spread is integrated over time, excluding intervals with an empty book side. Charts use one-second samples for readability; extrema and drawdown use all quote changes.

Signals use causal inputs and fixed symmetric thresholds. First half is 0–3000 s; second half is 3000–6000 s. Warmup is 120 s, and targets crossing the split or tape end are excluded. Second-half features may use earlier observed history. These are exploratory time-split checks, not an untouched external validation set.

Signal intervals use 800 moving-block bootstrap resamples, 60 s blocks for horizons up to 30 s and 120 s blocks for the 60 s horizon. Overlapping 100 ms observations are not treated as independent trades. Intervals are pointwise and unadjusted for multiple comparisons. They do not establish repeated-session profitability.

Crossing-cost diagnostic subtracts half the current spread plus half the future spread. This assumes touch execution and omits size impact, 5 ms latency and inventory constraints. Maker markouts instead use actual market-market executions, quantity weighting, and exact as-of future quotes. Empty-side observations and horizons past the tape end are excluded.

Strategy results use the unchanged official engine: 5 ms acceptance delay, ±100 penalty-free inventory, ±1000 potential exposure, and 10,000 per second breach penalty. PnL includes terminal depth liquidation. Ablations use fixed constructor controls; the full-size diagnostic overrides the effective limit after forecasting, retaining the history update. Effects interact and cannot be added as separate profit contributions. The traced original reproduces every result field of the unmodified original.

## Reproduce

Run `.venv/bin/python scripts/analyze_round3.py` from the repository root. Market reconstruction caches require matching tape and engine fingerprints. Missing main strategy benchmarks run automatically; `--refresh` reruns reconstruction and those benchmarks. Fixed ablations are optional: run `.venv/bin/python scripts/round3_diagnostics.py --variant NAME` for adaptive_trace, no_inventory_bias, no_fade, no_crash_bias, and no_risk_or_inventory_bias, then rerun the analyzer. Existing strategies and datasets are unchanged.

The standalone PNG/SVG overview additionally requires matplotlib; it was generated using a temporary installation, with no dependency changes in this repository.
