# Quant Arena Lab

Working offline preparation tools for an unknown competition problem. The original launch kit is preserved in `preparation/`, `starter_arena/` and `playbooks/`.

## Start here

From this directory, no install is needed for the core:

```bash
python3 arena doctor
python3 arena validate
python3 arena baseline configs/market.json
python3 arena baseline configs/ml.json
python3 arena optimize configs/games.json
python3 arena baseline configs/coding.json
```

For PDFs and the optional exact matrix-game LP, use the isolated environment already created:

```bash
.venv/bin/arena doctor --tests
.venv/bin/arena tournament configs/market.json --seeds 7,11,19
.venv/bin/arena report EXPERIMENT_ID --pdf
.venv/bin/arena quick-cards
.venv/bin/arena handoff
```

Every baseline/experiment writes its run ID, config, seed, source hash, dataset fingerprint, dependency versions and actual metrics into `experiments/ID/`. Reports read those saved files. `tournament` compares named methods on paired seeds; a per-scenario best score is not a fixed strategy's test performance.

## Recreate the environment

Python 3.10+ for the standard-library core; Python 3.12.6 on ARM macOS was tested locally.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[reports,optimization]'
.venv/bin/python -m pip check
.venv/bin/arena validate
```

`requirements-local.lock` pins the optional dependencies actually verified on this machine. It is a local environment snapshot, not a cross-platform lock. `pip install -r requirements-local.lock` followed by `pip install -e .` can reproduce it where compatible. Neither PDF tooling nor SciPy is required in the strategy loop. Use the venv: global scientific packages on this machine have mixed ARM/Intel binaries.

## Use your data explicitly

```bash
.venv/bin/arena inspect path/inside/project.csv
.venv/bin/arena diagnose path/inside/project.csv
```

To fit CSV data, configure `family: "ml"`, `dataset: "path/inside/project.csv"`, and `parameters` with `target`, `features`, `time_column`, and optionally `task: "classification"`, `gap`, `label_horizon`, `group_column`. See [adaptation rehearsal](docs/ADAPTATION_REHEARSAL.md). No target or time meaning is guessed. Rows must already be ordered, and preprocessing uses training rows only.

## What works, and where to look

| Area | Implementation | Evidence/limits |
|---|---|---|
| Market | `src/arena/trading.py` | Nine mock strategies including guarded fixed quotes, Decimal ledger and lifecycle tests; optimistic fills |
| ML | `src/arena/ml.py` | Mean/ridge and constant/logistic, chronological holdout, purging/group guards, probability metrics |
| Games | `src/arena/games.py` | Knapsack DP/oracle, congestion, auctions, matrix-game bounds/optional LP, conversion DP, risk scenarios |
| Coding | `src/arena/algorithms.py` | Graph search, shortest paths, topo sort, union-find, prefix sums, binary search, tiny oracle |
| Experiments/reports | `src/arena/experiments.py`, `reporting.py` | Saved provenance, paired seeds, HTML/Markdown/PDF; readable local memory |
| Submission preparation | `src/arena/preflight.py` | Configured function/import/compile checks only; no runtime certification |

Use `arena validate-submission candidate.py --contract configs/submission_contract.example.json` only as a static rehearsal. The example signature and limits are invented examples, explicitly unverified. The official API, resource limits, scoring and Technical Rules remain the first integration task.

`arena package scenarios/one_file_example.py --contract configs/submission_contract.example.json --output submissions/rehearsal.py` copies a statically checked self-contained file and writes a source/contract hash manifest. It refuses overwrites and does not bundle dependencies, execute code, enforce resource limits, or submit anything.

Read [rule register](docs/COMPETITION_RULES.md), [source review](docs/SOURCE_REVIEW.md), [task classifier](docs/TASK_CLASSIFIER.md), [market assumptions](docs/MARKET.md), and [safe submission](docs/SAFE_SUBMISSION.md). The supplied [field guide](preparation/ENGLISH_FIELD_GUIDE.pdf) and generated `docs/QUICK_CARDS.pdf` are offline study material.

Synthetic results establish functioning code, not competitive edge or real profits. Third-party ai-memory remains OFF. Nothing has been submitted, pushed or deployed.

Latest readiness pass: `MORNING_HANDOFF.md`. Reproduce the four-regime risk comparison with `.venv/bin/python scripts/validate_trend_guard.py`. `guarded_fixed` limits inventory to five and avoids quotes remaining far from the market; it sacrifices upside and is not a universally best strategy. Historical reports predate a corrected floating-point tick-rounding bug; use the new comparison for current results.


## Basic info 
- Date: 7.11 and 8.11
- Website: https://arena.qminers.com/
- Rules: https://arena.qminers.com/rules

### Competition structure

#### Modules:
**MODULE_01**
*Market Understanding*
Read price action, order flow, and market microstructure.

**MODULE_02**
*Machine Learning*
Pattern recognition, prediction models, and adaptive strategies.

**MODULE_03**
*Game Theory & Strategy*
Anticipate competitors, optimize for edge, manage risk.

**MODULE_04**
*Coding & Automation*
Build robust, fast, and reliable execution systems.

### Previous realizations
- https://github.com/AdamBobocky/qminers-24
- https://github.com/dmytriikorolov/QH2025

## Technical info
- Only Python solutions allowed 
    - Use NumPy by default, consider JAX if benchmarks show it helps - vectorize large array operations where useful
    - ML frameworks built on top of these ok - lets analyze later

## Study guide
### Market and modeling 
- Limit order book
- Bid-ask spread
- Order queue priority (FIFO if supported) - replacing orders may reset queue priority
- Order-flow imbalance - and order spoofing
- Tracking market volatility - rolling metric of volatility to protect against violent market changes in one direction
- Adverse selection
- Market vs limit orders 
- Invetory-aware quoting / invetory risk management
- Kelly criterion 
- Avellaneda-Stoikov model 

### Systems/execution speed 
- Numpy and JAX best practices 
    - JAX uses Just-In-Time (JIT) compilation. Initial compilation can be slow; warm up JIT functions before time-critical execution if JAX is used.
- asyncio, aihttp, websockets 
- Numpy arrays as circular buffers for fixed-size data - benchmark before optimizing append
- line_profiler - profiling python code - we need to optimize for speed after model done

## Further preparation
1. Reverse-Engineering Past Repos
    - Extract the API Wrapper: Look for useful evaluation patterns in past repos; don't assume the 2026 exchange API is the same.
    - Analyze the Winners vs. Losers: Look at the commit history. What did the winning team (if known) do differently?

2. Read papers about all the stuff above, come to hackathon with foundation in algorithmci trading

3. Bot Architecture (The 4 Pillars)
Standardize what you are actually going to code so the team can work in parallel without merge conflicts. Add this structure:
    - Data Ingestion: how to ingest and parse data, async only if required by the API
    - Signal Generator (Alpha): generates signals from the ingested data
    - Risk Engine: takes signals, current invemntory and outputs safe bids, etc
    - Execution (async if needed): tracks current open orders in queue, submits orders, updates, cancels, etc.

## Preparation specialities

## Papers and competition examples
- [The Micro-Price: A High Frequency Estimator of Future Prices](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694)
- [High-frequency Trading in a Limit Order Book](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf)
- [Enhancing Trading Strategies with Order Book Signals](https://ora.ox.ac.uk/objects/uuid%3A006addde-3a03-4d75-89c1-04b59026e1c0)
- [Optiver Ready Trader Go](https://github.com/trietvuive/optiver-ready-trader-go)
- [IMC Prosperity 2024](https://github.com/pe049395/IMC-Prosperity-2024)
