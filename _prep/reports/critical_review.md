# Independent critical review

Reviewed source SHA-256: `2445a1115fa8750a33a4d56971e4ade18201a5d8df1de138b3a15a3d6d3a533e`. Reviewer-only seeds: `901,902,903,904,905`; 300 steps per regime; fee 0.01 per filled unit; hard position limit 10; candidate soft cap 5.

**Verdict:** Accounting is supported by fresh tests and an independent execution cash-flow oracle. The guarded policy reduces simulated exposure and tail drawdown versus uncapped fixed quotes, but does not establish profitability or a new trading edge. Most stress improvement is reproduced by a simple position cap. No-op earns 0 with zero drawdown and beats the guarded policy in every stress-regime average below. Do not promote the candidate as a general default.

## Findings

1. **Confirmed and fixed numerical bug.** Quote arithmetic used floating point before directional tick rounding. At bid 100.0 / ask 100.2, fixed quotes were 99.8 / 100.3 instead of 99.9 / 100.3. At 99.7 / 99.9, they were 99.6 / 100.1 instead of 99.6 / 100.0. Current Decimal midpoint/quote arithmetic reproduces both corrected prices. Historical artifacts remain original evidence; their numerical results are superseded for current-code comparisons.

2. **Unresolved session scaling.** `Ledger.submit()` scans all historical orders for own crosses, then `exposure()` scans them again. Terminal orders accumulate indefinitely. Inventory replay took 0.184 s for 1,000 steps / 2,000 orders, 0.630 s for 2,000 / 4,000, and 2.331 s for 4,000 / 8,000. This is near-quadratic total work and an unbounded per-order session cost. It does not invalidate 300-step accounting, but requires redesign before prolonged live use.

3. **Profit credibility remains low.** Passive fills assign all matching flow to our orders without calibrated queues or market impact; final inventory is marked at mid; simulator regimes are invented. These assumptions and path-winner selection bias are already disclosed accurately. Existing tests cannot validate official performance. The candidate still accumulates losing directional inventory under sustained trends.

## Independent holdout and cap-only diagnostic

All candidate paths stayed within five units. The cap-only control uses the unchanged fixed policy with `position_limit=5`; it isolates how much improvement is attributable to halving exposure. It is a diagnostic ablation, not another tuned winner.

| Regime | Fixed mean PnL | Cap-only mean PnL | Guarded mean PnL | Fixed worst drawdown | Cap-only worst drawdown | Guarded worst drawdown |
|---|---:|---:|---:|---:|---:|---:|
| mean_reverting | 17.020 | 12.098 | 14.012 | 21.00 | 10.50 | 7.83 |
| trend | -73.832 | -38.102 | -38.698 | 120.10 | 60.75 | 60.00 |
| trend_down | -42.248 | -21.462 | -21.674 | 103.00 | 52.00 | 51.61 |
| volatile | -78.404 | -39.726 | -44.126 | 173.00 | 86.50 | 85.37 |
| shock | -113.832 | -58.102 | -58.698 | 160.10 | 80.75 | 80.00 |

Guarded mean PnL loses 3.008 versus uncapped fixed in mean reversion, while lowering drawdown. Versus the cap-only control it gains 1.914 in mean reversion, but loses 0.596 in trend/shock, 0.212 in downtrend, and 4.400 in volatility. Closing final positions at the displayed bid/ask plus the same per-unit fee leaves guarded mean PnL at 13.660, -39.248, -22.224, -44.676, -59.248 respectively; these remain mock top-of-book liquidation estimates.

## Accounting and ML evidence

- An independent `Fraction` oracle checked 2,000 random executions against summed signed cash flows and integer positions, after every event. Partial fills, both position flips, fees, rebates, cancellation, duplicate executions after cancellation, and marked PnL identities all passed with 1e-9 tolerance for reported floats.
- Fresh focused commands below passed: 25 trading tests, 28 ML tests, 8 tournament tests; no failures or skips.
- Pending buy and sell quantities reserve independently; cancel requests release no exposure until acknowledgement. Partial fills retain the remaining reservation. Terminal late fills are rejected under the explicit fill-barrier acknowledgement contract. No accounting sign, fee, or partial-fill defect was reproduced.
- ML imputation/scaling fit training rows only, penalty selection uses validation only, and final test features/targets cannot change the model or selected penalty in a fresh adversarial perturbation check. Row-horizon gaps and requested group separation are checked. This does not prove caller-supplied features were available at prediction time; transformed target copies and unknown lookahead remain possible. Repeated user tuning can overfit the same test window.

## Historical strongest/weakest replay

Scanned all 16 saved market experiments. Before the precision fix, each of the following complete results, including equity paths and data fingerprints, reproduced exactly:

| Strategy/extreme | Run | Saved PnL | Current PnL after precision fix |
|---|---|---:|---:|
| fixed worst | `20261106T221006-b0f3354d84` | -129.34 | -129.34 |
| fixed best | `20261106T221004-a2da8608f9` | 39.72 | 38.12 |
| momentum worst | `20261106T221007-6808851379` | -48.83 | -48.83 |
| momentum best | `20261106T221006-b0f3354d84` | 97.72 | 97.72 |

Exact current rows differ because midpoint/tick arithmetic changed; the new ninth policy also changes result metadata. This is expected provenance drift, not evidence that the original saved run was fabricated.

Across 15 unique original regime/seed paths (excluding the duplicated baseline), hindsight-selected winner PnL averaged +27.502; fixed averaged -40.413, inventory -0.489, signal -1.469, momentum +4.065, and no-op 0. These original-code figures quantify winner selection bias and must not be mixed with current-code scores.

## Reproduction

Run from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_trading.py -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_ml.py -q
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_tournament.py -q
PYTHONPATH=src .venv/bin/python - <<'PYCODE'
from arena.trading import mock_scenario, replay
from statistics import mean
for regime in ('mean_reverting', 'trend', 'trend_down', 'volatile', 'shock'):
    for policy, limit in (('fixed', 10), ('fixed', 5), ('guarded_fixed', 10), ('no_op', 10)):
        rows = [replay(mock_scenario(seed, 300, regime), policy, position_limit=limit)
                for seed in range(901, 906)]
        print(regime, policy, limit, mean(x['pnl'] for x in rows),
              max(x['max_drawdown'] for x in rows), max(x['max_abs_position'] for x in rows))
PYCODE
```

Raw per-seed results, liquidation estimates, hashes, historical extremes, and test commands are retained in `reports/critical_review.json`. Only the two review report files were written by this reviewer; no existing implementation was modified.
