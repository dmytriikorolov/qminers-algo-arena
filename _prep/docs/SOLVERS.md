# ML, allocation, games and coding: working scope

All examples below are synthetic. They establish implementation behavior, not
prediction skill on competition data or an advantage against real opponents.
Core modules use only the Python standard library. No third-party strategy code
was copied into these implementations.

## Run

From this lab directory, after installing the package:

```bash
.venv/bin/arena baseline configs/ml.json
.venv/bin/arena optimize configs/games.json
.venv/bin/arena baseline configs/coding.json
```

For direct offline verification without installing it:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_ml.py -v
PYTHONPATH=src python3 -m unittest discover -s tests -p test_games.py -v
PYTHONPATH=src python3 -m unittest discover -s tests -p test_algorithms.py -v
```

## ML: what is implemented

`arena.ml.run_rows` / `run_csv` require `target`, `features`, and `time_column`.
There is no automatic guess about column meaning. Timestamps must increase
strictly; aggregate simultaneous observations deliberately before using this
simple baseline. Both numeric and ISO 8601 times are supported.

The first 60% trains, the next 20% selects the ridge/logistic penalty, and the
last 20% is evaluated after selection. Means for missing-value imputation and
standard deviations are fitted on training observations alone. The baseline
predicts the training target mean (a class probability for classification).

`gap` drops rows before each later split. Set `label_horizon` to the number of
rows a label looks ahead, and `gap >= label_horizon`. For irregular intervals or
variable label durations, this row-based gap is insufficient: implement
timestamp-based purging for the actual statement. If `group_column` is set,
groups must be disjoint across splits; overlap raises an error rather than
silently shuffling dependent observations.

Direct target inclusion, time/group feature inclusion, exact target copies,
nonfinite targets, unordered timestamps, duplicate CSV headers and unknown
parameters are rejected. These checks cannot detect every semantic leak. Check
when each feature became available. Repeatedly inspecting the final test score
can itself cause selection bias.

Example file-backed configuration (adjust filenames and column names):

```json
{
  "family": "ml",
  "seed": 7,
  "dataset": "scenarios/your_legal_data.csv",
  "parameters": {
    "target": "next_return",
    "features": ["spread", "imbalance"],
    "time_column": "timestamp",
    "task": "regression",
    "label_horizon": 1,
    "gap": 1,
    "penalties": [0.001, 0.1, 1.0]
  }
}
```

Regression reports MSE/RMSE/MAE. Binary classification reports log loss, Brier
score, accuracy and five calibration bins. Saved model coefficients, feature
order, imputation means and scales are small JSON values; exporting these into
an actual submission still depends on official permission for prepared files.
The lightweight implementation caps rows/features and is a baseline, not a
replacement for optimized numerical libraries on large data.

## Six game examples

`arena.games.demo(seed=7)` returns each statement, input and solution. The
following rounded values were obtained from that command during development;
saved experiment JSON remains the authoritative source for a reported run.

| Example | Model and answer | Main failure assumption |
|---|---|---|
| Knapsack | Costs `[6,4,5]`, rewards `[11,8,9]`, budget 10. Choose items 0 and 1: reward **19**, matching enumeration. | One copy per item, integer cost, additive reward. |
| Shared reward | Rewards 100/80; ten independent opponents choose with probabilities .9/.1. Expected shares **10.101 / 49.905**; choose B. | Rival choices are assumed independent with known probabilities. |
| First-price auction | Value 10, highest rival bid Uniform(0,10), 2,000 seeded samples. Grid selects **5.1**, estimated utility **2.5872**. Analytic optimum is 5; the discrepancy is Monte Carlo noise. | Highest competing bid is uniform, no reserve or correlated values. |
| Matrix game | Matching pennies `[[1,-1],[-1,1]]`. Fictitious-play value near zero; best-response gap **0.0139972** after 10,000 iterations. | Two players, zero-sum; this is an approximation with bounds. |
| Conversion graph | A→B rate 2, B→C rate 3, C→A rate .2; 1% fee each. Three conversions turn 1 A into **1.1643588 A**. | Fixed rates, no depth/slippage; at most three conversions. |
| Tournament risk | Trailing 90 vs 100 before one round, assumed normal return models. Safe maximizes expected score; aggressive wins most often (**.2782** vs **.0386** safe). | Return distributions and opponent behavior are hypothetical. |

Important distinctions:

- Shared reward computes `E[R/(K+1)]`, not `R/(E[K]+1)`.
- First-price, second-price and all-pay auctions have separate payment rules;
  ties have an explicit win probability.
- The conversion DP allows returning to an asset several times, while respecting
  the edge-count limit. It retains doing nothing when every cycle loses money.
- Tournament policies use the same random draws. The returned sampling standard
  error measures Monte Carlo uncertainty under the assumed model, not uncertainty
  about that model or the competition.

For an LP equilibrium, install an allowed compatible SciPy and explicitly set
`"equilibrium_method": "lp"`. `zero_sum_lp` solves row and column programs
separately and checks their best-response bounds. The default remains the
dependency-free approximation. Development checked optional LP tests using
`PYTHONPATH=src arch -x86_64 python3 -m unittest discover -s tests -p test_games.py -v`
because this machine's global NumPy extension is x86_64. Subsequently, compatible
ARM NumPy/SciPy were installed in the project `.venv`; native `.venv/bin/arena validate`
now runs both LP tests. Nothing changes the system interpreter or packages.

## Coding primitives

`arena.algorithms` includes Dijkstra, Bellman-Ford, BFS, topological sort,
union-find, binary search and prefix sums. Dijkstra validates every edge before
early exit, preserves integer distance precision and rejects floating overflow.
Bellman-Ford rejects negative cycles reachable from the starting vertex.
The tiny simple-path oracle validates Dijkstra on seeded random graphs; the
knapsack oracle similarly validates the faster DP on 100 random small instances.

Not implemented here: ranking ML, tree models, notebook workflows, automated
feature ablation, variable-duration purging, general-sum equilibria, full MDPs,
continuous portfolio optimization or bandits. Select these from the actual task,
after verifying the simple evaluator and baselines.
