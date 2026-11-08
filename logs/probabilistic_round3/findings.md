# New round 3-only strategies

Models use only already-observed round 3 events and no pretrained weights. The HMM has fixed transition probabilities, hand-set Gaussian priors, and online posterior-weighted emission updates. Bayesian labels mature before training.

| Variant | PnL | First half | Second half | Max drawdown |
|---|---:|---:|---:|---:|
| hmm_gate10 | 41,019 | 22,871 | 18,148 | 13,518 |
| hmm_gate30 | 40,612 | 21,977 | 18,635 | 13,717 |
| hmm | 37,998 | 19,931 | 18,067 | 13,877 |
| fade30 | 18,974 | 6,687 | 12,287 | 9,200 |
| fade10 | -3,664 | 2,387 | -6,051 | 14,112 |
| bayes10 | -6,794 | -10,131 | 3,337 | 17,852 |
| bayes5 | -24,882 | -25,104 | 222 | 32,120 |

Official latency, inventory limits, and terminal liquidation apply. Every run has zero breach penalties. Temporal halves are diagnostics, not untouched holdouts after comparison. Best new PnL remains below the previously verified 90,650 round 3 run. Reproduce with: .venv/bin/python scripts/test_probabilistic_round3.py hmm_gate10
