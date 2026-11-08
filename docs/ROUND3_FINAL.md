# Round 3 final attempt

The **180,000 target was not reached**. The supplied `baseline.py` freshly
reproduces **71,080** on the local round 3 tape with the official rules.
Twenty-four candidate configurations were tested. These are public-data selection
results; neither temporal half is an untouched holdout after comparing variants.

## Delivered strategy

`strategies/round3_adaptive_maker.py` is standalone apart from the simulator API.
The existing baseline and simulator were not edited. It adds a bounded passive
reversal target and changes the volatility sizing ramp from 1.4/2.2 to 2.0/3.0.
Only completed seconds feed the reversal signal:

```text
move = sum(last 30 one-second returns)
center = round(clip(-8 * move, -40, 40) * min(1, 2 / max(0.1, volatility_forecast)))
```

The center shifts the existing market maker's inventory range. Positions build
through passive quotes; the signal does not trigger spread-crossing entries.
Quote capacity is clipped against actual inventory, independently of the center.
The inherited imbalance gates, separated target-seeking and overshoot quantities,
shock response, queue-preserving quantity reductions, and rescue IOC logic remain.
During a shock the strategy can still move toward the bounded center; it does not
necessarily flatten to zero. No round 3 timestamps, future rows, runtime data-file
reads, or fitted round 3 coefficients enter the strategy.

| Configuration | Round 3 PnL | First half | Second half | Max sampled drawdown | Round 2 PnL |
|---|---:|---:|---:|---:|---:|
| Existing baseline | 71,080 | 38,392 | 32,688 | 2,336 | 158,426 |
| Shipped balanced | 93,741 | 45,139 | 48,602 | 3,586 | 152,744 |
| Aggressive experiment | 99,429 | 40,658 | 58,771 | 12,554 | 79,148 |

The shipped strategy improves the local round 3 baseline by **31.9%**, but loses
**3.6%** versus it on round 2. The inherited volatility weights were fitted on
round 2, so that replay is a historical stress comparison, not independent
validation.

The aggressive experiment uses `fade_strength=20, fade_limit=100, fade_risk=10`.
Its extra 5,688 on round 3 comes with 3.5 times the balanced strategy's sampled
drawdown and approximately half the original baseline's round 2 PnL. It is not
the default. Lowering the target cap was more useful than keeping more complex
features solely because they sounded sophisticated.

Balanced round 3 has zero breach penalties and observed maximum inventory 100.
Balanced round 2 incurs 50 in penalties. Fast requoting retains the baseline's
cancel-race exposure: zero penalties on one tape is not a guarantee. Set
`strict_exposure=True` to reserve pending cancels until acknowledged. The balanced
strict experiment earns 86,247 on round 3 and 142,474 on round 2, with zero
penalties on both. Race-induced excess is handled by rescue IOC orders; passive
quote size never expands beyond twice the inventory limit.

## Theory and rejected additions

[Avellaneda–Stoikov](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf)
motivates inventory-sensitive quote placement. This is a heuristic inventory-target
extension, not a solution of that paper's control problem.
[Cont–Kukanov–Stoikov](https://arxiv.org/abs/1011.6402) motivates testing book-pressure
filters. The existing round 3 report's reversal observation motivates the passive
fade. None of these sources establishes profitability in this simulator.

Online recursive least-squares volatility updates with delayed labels, stronger
book-pressure filters, smaller quotes, additional queue hysteresis, earlier spread
improvement, and faster passive exits were tested. They did not improve the
selected configuration and remain in the research harness rather than the
standalone submission.

## Reproduce

```bash
.venv/bin/python -m simulator.main --strategy strategies/round3_adaptive_maker.py --backtest data/round3_public.csv --log-dir logs/round3_final/recheck --no-logs
.venv/bin/python -m unittest discover -s tests -p 'test_round3_adaptive_maker.py' -v
.venv/bin/python scripts/research_round3_final.py fade_large fade_full fade_strict
.venv/bin/python scripts/research_round3_final.py baseline fade_large --tape round2_public
```

The harness uses the existing `strategies/baseline.py`; the standalone submission
does not import another strategy. Nine tests cover loader selection, causal
warmup and risk scaling, physical quote-size bounds, pending cancels, pending
reductions, rescue accounting, race-time passive sizing, invalid parameters, and
baseline equivalence on the tracked sample tape when new behavior is disabled.

All replays use 5 ms latency, public depth 20, ±100 penalty-free inventory,
±1000 potential exposure, and 10,000/second breach penalties. Scores include
terminal liquidation. Drawdowns use one-second PnL samples and can miss worse
intrasecond losses. Results, PnL curves, parameters, and source/tape fingerprints
are stored in `logs/round3_final/`. Public selection scores are not estimates of
private-round PnL.

## All round 3 experiments

Variant names map to arguments in `scripts/research_round3_final.py`.

| Variant | PnL | First half | Second half | Max sampled drawdown | Penalty |
|---|---:|---:|---:|---:|---:|
| fade_full | 99,429.00 | 40,658 | 58,771 | 12,554 | 0.00 |
| fade_risk | 96,502.00 | 41,195 | 55,307 | 9,541 | 0.00 |
| fade_capacity | 94,733.00 | 43,356 | 51,377 | 6,138 | 0.00 |
| fade_large | 93,741.00 | 45,139 | 48,602 | 3,586 | 0.00 |
| fade_ramp | 92,560.00 | 44,834 | 47,726 | 4,131 | 50.00 |
| fade | 87,350.00 | 43,000 | 44,350 | 3,593 | 50.00 |
| ramp | 87,112.00 | 45,380 | 41,732 | 4,610 | 50.00 |
| simple | 86,780.00 | 45,258 | 41,522 | 3,846 | 50.00 |
| fade_strict | 86,247.00 | 41,751 | 44,496 | 3,653 | 0.00 |
| queue1 | 83,105.00 | 42,623 | 40,482 | 4,563 | 0.00 |
| queue5 | 82,795.00 | 43,113 | 39,682 | 4,577 | 0.00 |
| queue2 | 81,799.00 | 42,488 | 39,311 | 4,577 | 0.00 |
| online500 | 81,397.00 | 43,021 | 38,376 | 3,464 | 50.00 |
| skew | 80,714.00 | 42,660 | 38,054 | 4,636 | 50.00 |
| fade_full_capped | 79,141.00 | 28,899 | 50,242 | 12,274 | 0.00 |
| ungated | 78,556.00 | 39,082 | 39,474 | 4,724 | 50.00 |
| online50 | 77,168.00 | 40,409 | 36,759 | 3,666 | 50.00 |
| broad_ramp | 75,893.00 | 37,652 | 38,241 | 4,518 | 50.00 |
| exit | 66,459.00 | 35,229 | 31,230 | 4,020 | 50.00 |
| clip80 | 56,990.00 | 29,975 | 27,015 | 4,632 | 50.00 |
| clip40 | 32,854.00 | 18,741 | 14,113 | 4,623 | 50.00 |
| pressure | -880.00 | 2,923 | -3,803 | 7,115 | 0.00 |
| inside | -10,959.81 | -4,491 | -6,469 | 11,385 | 203.81 |
| inside_ramp | -23,827.81 | -11,632 | -12,196 | 23,828 | 253.81 |

Final standalone replays match every SimulationResult field of their research
counterparts on both rounds 2 and 3. The race-size regression was demonstrated
failing before the fix and passing afterward.
