# QUANT ARENA LAB — MASTER CODEX BUILD PROMPT

**Copy this entire file into a new Codex session on my personal Mac in the project directory.**

I am preparing for the **Qminers × MFF UK Algo Trade Arena, November 7–8, 2026**. My main Codex weekly allowance resets on **November 5**, and an additional usage window ends on **November 6 at 23:25 Prague time**. Build as much useful, thoroughly tested infrastructure as possible inside that window, with the most important work finished first.

I have not given you any previous prompts about this project. **Start from scratch.** Do not assume that another Codex session has already built anything.

I want an unusually strong **competition preparation toolkit for an unknown problem**, not only a market-making bot. There are four themes in my notes: **(1) Market Understanding, (2) Machine Learning, (3) Game Theory & Strategy, (4) Coding & Automation**. These are themes, **not proof of four separate actual challenges**. The official 2026 competition description emphasizes creating a trading algorithm in a simulated market. Do not invent rules, problem statements, APIs or evaluation details.

My preparation repository: https://github.com/dmytriikorolov/qminers (private; use my existing Git credentials if available; do not ask for secrets or expose them). It currently contains a README with links and study notes. Inspect it before changing anything.

The goal: when the organizers reveal the actual task, I want to select a known problem family, inspect the official contract, plug in a working baseline, run reliable tests, and make improvements. I am still learning the underlying finance/game theory. Explain important choices in straightforward English: what it does, why it might work, when it fails, and how we test it. Avoid dense, performative language.

## EXECUTION RULES — READ FIRST

1. **Build, do not merely plan.** Work autonomously through vertical slices: runnable baseline first, tests second, sophisticated extensions later. If I am away from my computer, continue through the approved local work instead of stopping after an architecture proposal.
2. **Respect contest rules.** Before reusing any pre-written code, package or dataset for the actual submission, read the current official competition rules. Mark each restriction as VERIFIED / UNVERIFIED in `docs/COMPETITION_RULES.md`. Precompetition research tools may be kept separate from submission code. Do not deploy pre-built code into the competition if forbidden.
3. **No fake API.** A mock adapter must be visibly named `mock`. The eventual competition adapter is a stub until the real API is available. A synthetic backtest is never evidence of live profit.
4. **Source-first reuse.** Read the source files, not only the READMEs, of the specified past projects. Extract general ideas and independent tests; keep third-party code and licenses isolated. The Optiver repository includes AGPL-licensed code; do not silently paste it into our own submission.
5. **Stay within my personal project.** You may create/change code and run tests under the current repo, fetch public documents and install reasonable packages in isolated environments. Never inspect unrelated personal, work or corporate files. Never push, deploy, open paid services or install system-wide persistent hooks without explicit approval.
6. **Safety gate for third-party memory.** Do not install or enable `akitaonrails/ai-memory` yet. Its hooks can capture coding-session activity. First pin its commit, scan the appropriate skill files with NVIDIA SkillSpector, inspect installers, hooks, binaries, network and storage, test without credentials in isolation, and prepare a review. A clean SkillSpector finding is insufficient for approval. The scanner is not a full binary audit.
7. **No unnecessary features.** Use plain Python, NumPy, SciPy, pandas/Polars, scikit-learn, pytest, matplotlib, reportlab or equivalent. The target laptop is an Apple Silicon M2 MacBook Air with 8 GB RAM. No CUDA. JAX / Numba only after evidence of benefit, and only if competition dependencies allow. Keep the final submission lightweight.
8. **Evidence over appearance.** Do not call something 'tested' unless commands actually ran. Record test results, benchmark environment, limits and skipped tests. Do not create a huge fake dashboard or dozens of unfinished algorithms.
9. **Protect my time.** Do not ask frequent clarifying questions. If a requirement is unknown, choose a reasonable reversible default, document it and proceed. Ask for approval only when permissions, secrets, destructive actions, or real competition rules require it.
10. **Leave spare capacity.** Make the strongest complete baseline before November 6 at 23:25. It is better to finish 8 robust capabilities than to start 25 and finish none.

## PHASE 0 — RECONNAISSANCE AND RULES

Check these materials and extract actual actionable ideas:

- My repo: https://github.com/dmytriikorolov/qminers
- Qminers 2026 website: https://arena.qminers.com/ and https://arena.qminers.com/rules
- 2024 winner post-mortem: https://github.com/AdamBobocky/qminers-24
- 2025 official starter repo: https://github.com/dmytriikorolov/QH2025
- Optiver Ready Trader Go simulator and autotrader: https://github.com/trietvuive/optiver-ready-trader-go
- IMC Prosperity 2024 strategies: https://github.com/pe049395/IMC-Prosperity-2024
- IMC manual puzzle write-ups: https://github.com/gabsens/IMC-Prosperity-2-Manual and https://github.com/nathanbronson/Prosperity2025
- IMC 2026 student write-up: https://github.com/marcobattiston21/imc-prosperity-4
- Security scanner: https://github.com/NVIDIA/SkillSpector
- Memory system: https://github.com/akitaonrails/ai-memory
- Codex skill guidance: https://github.com/openai/skills

Write `docs/SOURCE_REVIEW.md` with for EACH source: actual examined files, problem solved, reusable components, assumptions that do not transfer, code/license limitations, and one actionable lesson. Do not pretend you examined a file that you could not access.

In `docs/COMPETITION_RULES.md`, use a table: rule, source, exact citation/URL, verified?, practical effect. In particular check permitted languages, use of pre-written code and AI, team size, data restrictions, offline/network, CPU/RAM/time limits, number of submissions, execution mode, scoring and libraries. In my README 'Python only' is a user note, not independent official verification.

Produce `docs/TASK_CLASSIFIER.md`: a decision tree to identify the problem type within the first 15 minutes. Do not hardcode one answer based on marketing language.

## PHASE 1 — SHARED CORE THAT SERVES ALL FOUR MODULES

Create a Python package with a single CLI, tentatively `arena`, supporting subcommands:

```
arena doctor                  # dependencies, tests, environment
arena inspect PATH            # file/schema/quality quick view
arena diagnose PATH           # data patterns and hypotheses
arena baseline CONFIG         # run an appropriate basic solution
arena experiment CONFIG       # reproducible train/evaluate loop
arena tournament CONFIG       # paired multi-strategy comparison
arena optimize CONFIG         # resource/game/portfolio optimization
arena report EXPERIMENT_ID    # HTML/PDF, human-readable interpretation
arena handoff                 # summarize branch, results, next actions
arena validate                # tests plus submission preflight
```

Create these areas, adjusting names only for simplicity:

```
src/arena/{cli,common,data,features,models,trading,execution,risk,
           games,optimization,simulation,evaluation,reports,adapters}/
experiments/  scenarios/  configs/  tests/
docs/  research/  reports/  memory/
.agents/skills/  AGENTS.md  pyproject.toml  uv.lock
```

All runs should have an ID, timestamp, git revision, config, seed, dataset fingerprint, dependencies and metrics. Store small structured results in JSON, larger tables in parquet only if available. Use deterministic smoke tests. The `arena doctor` command must work offline with only minimal dependencies.

Create `docs/SAFE_SUBMISSION.md`: the final competitor code must be separate from research/plotting/agent-memory/PDF components, with no startup hooks, secrets, network calls or writing outside permitted paths unless explicitly allowed by official rules.

## MODULE 01 — MARKET UNDERSTANDING: PLUG-AND-PLAY MARKET PLAYBOOK

Implement a real market data toolkit supporting time-series bars, trades and snapshots; add an event-by-event order book only if the given data actually supports it. Do not hallucinate order-level events from snapshots.

**Features:** midprice, bid-ask spread, spread in ticks/bps, microprice, depth imbalance (top level and top-k), order-flow imbalance when valid events exist, rolling returns, volatility, volume, signed trade flow if observable, liquidity/depth, stale/crossed/locked book checks, market state changes, and causal rolling features.

**Patterns and templates:**
- Stable fair value / mean reversion: rolling mean, EWMA, z-score, inventory-aware market making.
- Trending asset: momentum, trend filter, stop/risk controls; don't keep fading a strong trend.
- Limit order book with actual fills: baseline maker, directional skew, cancellation logic, position-aware quoting.
- Tradeable mispricing: compare expected fair value against executable bid/ask after fees, spread and slippage.
- Two linked assets: hedge ratios, spread residuals, pair trading only with supplied instruments.
- Basket vs components: compute basket fair value and transaction costs, hedge only if allowed.
- Options: Black-Scholes and Greeks where relevant, numerical sanity checks, position/delta limits; do not assume options exist.
- Volatility shock / low liquidity: fewer or wider quotes, smaller position, kill switch.

Create a market simulator with event-driven order lifecycle, position/cash ledger, synthetic scenarios, explicit fill assumptions, optional fees, partial fills, latency and basic queue position approximations. It is a learning/test simulator; never label it identical to Qminers. When the official simulator is released, prioritize matching it over upgrading our synthetic one.

Build 5–8 thoroughly tested trading baselines: no-op, fixed quotes, fair-value maker, inventory-aware maker, signal-skewed maker, simple taker when edge exceeds costs, momentum, mean reversion. Add advanced A–S or queue modeling only after these run.

**Non-negotiable accounting tests:** fill idempotency, partial fills, cash/position signs, pending-order exposure, position limits including open orders, fees, tick/lot rounding, cancel/replace races, stale data and timestamps, delayed acknowledgements, mark-to-market vs realized PnL, no negative/invalid quantities, deterministic replay.

## MODULE 02 — MACHINE LEARNING: FAST TABULAR BASELINES, NOT A DEEP-LEARNING SHOWCASE

Build a reusable, memory-aware baseline pipeline for regression, binary classification, ranking and probabilities. It should auto-detect target/time/group ID only with explicit confirmation or config, report missing values/class balance and check whether the target is accidentally leaked into features.

Models in sensible order:
- Constant/majority/last-value baseline.
- Linear and ridge regression, logistic regression.
- Simple tree ensemble / HistGradientBoosting; optionally XGBoost or LightGBM if allowed and installed.
- Optional small MLP only when a measured baseline warrants it.

Metrics: task-specific error or profit, log loss/Brier/calibration for probabilities, directional accuracy as secondary, realized trading PnL with fees and position constraints for trading signals.

Validation: chronological train/validation/test splits for time series; purged/embargoed split if samples overlap; group separation for entity/player/team data; strict feature computation using information available by prediction time; seeded CV only where legitimate; final untouched holdout.

Implement feature ablation, simple hyperparameter sweeps, confidence intervals or bootstrap where appropriate, and a model comparison report. Allow a pre-trained model to be exported as a small artifact only if official rules permit weights/files.

Make one-command notebooks for: initial EDA, leak tests, supervised baselines, time-series validation, feature importance, probability calibration, experiment comparison.

## MODULE 03 — GAME THEORY AND RESOURCE ALLOCATION: PREPARE FOR MANUAL AND STRATEGIC GAMES

Build reusable exact and approximate solvers, plus short explanations of how to select them.

Problem families and required implementations:

A. **Finite resource allocation / knapsack.** Given budgets, costs and rewards, implement brute force for small instances, DP/knapsack, SciPy MILP/linear programming when suitable, and a clear interpretation of choices and unused budget.
B. **Reward sharing / congestion.** Reward from choosing option i is shared with other participants choosing i. Build expected payoff under a configurable distribution of opponents; optimize one or multiple choices; explore sensitivity when opponent behavior differs. Allow discrete choices and penalties for extra selections.
C. **Auctions and bidding.** First-price, second-price, all-pay and sealed-bid toy games where the statement specifies the rules. Evaluate expected utility over bids and uncertainty in other bids; use Monte Carlo and deterministic grid checks.
D. **Simultaneous-move matrix games.** Zero-sum maximin and equilibrium LP, best responses, exploitability checks, normal-form payoff matrices and mixed strategies. Do not assume all games are zero-sum.
E. **Sequential games and MDPs.** Backward induction for small deterministic trees, dynamic programming for finite horizons, basic value iteration/policy iteration for small MDPs, and Monte Carlo rollouts for larger trees.
F. **Opponent modeling.** Basic empirical frequencies, smoothing, alternate rival types, best response vs robust or mixed strategy, regret benchmarking. Clearly distinguish observations from speculation.
G. **Multi-round tournament strategy.** Objective may be final score, probability of winning, survive a cutoff, or balance risk. Simulate standings and risk levels under plausible opponent models; don't maximize expected profit if winning probability is the real objective.
H. **Exchange-rate arbitrage / path search.** Graph conversion with fees; Bellman-Ford negative cycles when appropriate, bounded-length dynamic programming / recursion when conversion count is limited.
I. **Portfolio/capital allocation.** Linear/quadratic optimization with constraints, scenario analysis, diversification; validate sensitivity to expected-return estimates.
J. **Bandits / exploration vs exploitation.** Epsilon-greedy, UCB1 and Thompson sampling on synthetic Bernoulli cases; demonstrate when collecting information is worth the cost. Only use online learning if allowed.
K. **Probabilistic manual puzzle.** Exact probability enumeration for small sample spaces, Monte Carlo with intervals for bigger ones, sensitivity and sanity bounds.

Build at least **six end-to-end example problems**, each with a problem statement, solver, test, graph, and a one-page answer: knapsack, shared-reward choice, sealed-bid auction, zero-sum matrix game, conversion graph and multi-round risk allocation. Do not claim any are actual Qminers tasks.

## MODULE 04 — CODING AND AUTOMATION: GENERAL PURPOSE CONTEST TOOLKIT

Build a small tested algorithm library (not 300 lines of vague placeholders) covering:
- binary search, prefix sums, two pointers, sorting, heaps and top-k;
- graphs: BFS, DFS, Dijkstra, Bellman-Ford, topological sorting, union-find;
- dynamic programming: knapsack, finite-horizon recursion/memoization;
- combinatorics and safe enumeration for small spaces;
- probability simulation and robust random sampling;
- optimization wrappers: LP, MILP, bounded continuous minimization;
- event-loop/async exchange adapter only if API demands it;
- parsing, schema validation, JSON/CSV/Parquet input and output;
- profiling with `cProfile`/perf_counter and memory checks;
- testing via pytest, parameterized tests, property checks where valuable.

Support one-file submission packaging and a `validate_submission` command: correct function/class signature, all imports available, no banned behavior, strict runtime/memory, no unexpected output, edge-case smoke test and exact file layout. Stub the actual submission contract until organizers supply it.

Favor correct Python over early JAX optimization. Compile/warm up if JAX is used; measure startup cost and respect supported platform/libraries.

## REPORTS AND STUDY MATERIALS — BUILT FOR A HUMAN LEARNING FAST

Create PDF generation from actual saved experiment files, not imagined numbers. Support:
- 1–2 page Quick Insight: problem, data, finding, validation, action, warnings.
- 4–8 page Strategy Report: baseline comparison, PnL/score, risk, execution, uncertainty, failure modes, recommended next test.
- Short live-session Decision Sheet: current best solution, why it wins, what could break.

Add diagrams where they clarify things: order book spread, order lifecycle, strategy architecture, allocation examples, ML leakage timeline, game payoff table, workflow decision tree. Each chart must identify whether it uses example/synthetic data.

Create `docs/ENGLISH_FIELD_GUIDE.md` written for me (a CS/math student not yet fluent in trading): concise definitions, simple numeric examples, 'what it is / when to use / when not to use', a start-to-finish plan per challenge type, and 20 short interview-style questions with answers.

Produce a printable `docs/QUICK_CARDS.pdf`: no more than 12 pages in total, one problem family per card, readable offline. Produce reports with `matplotlib` and `reportlab` or similar only on demand, not on every simulation tick.

## CODEX SKILLS — SMALL, WORKING, CONTEXT-EFFICIENT

Use the official `skill-creator` guidance. Prefer a concise `SKILL.md` and runnable deterministic scripts over long repeated prompts; put reference notes under each skill's `references/`. Implement and test:

- `arena-triage` — inspect official statement + rules and choose task family;
- `arena-market` — examine trading data and identify meaningful signals;
- `arena-ml` — training, validation and leakage checks;
- `arena-game` — formalize a game and select a solver;
- `arena-optimize` — resource/portfolio allocation;
- `arena-experiment` — config-driven reproducible comparisons;
- `arena-report` — generate sourced metrics and readable PDF;
- `arena-debug` — triage failures without inventing a fix;
- `arena-handoff` — summarize decisions, attempts and next steps;
- `arena-submit` — preflight check under official restrictions.

These are workflow skills, not 'magic' problem solvers. The CLI modules must work without any skill activated. Do not automatically install random third-party skills. Reasonable official optional skills: `jupyter-notebook`, `pdf`, `security-best-practices`; confirm actual availability before installing.

## MEMORY AND SESSION HANDOFF

Implement **local-first**, repo-owned and readable memory now: `memory/decisions.md`, `memory/hypotheses.jsonl`, `memory/experiments.jsonl`, `memory/failures.md`, `memory/current_state.md`, `memory/handoff.md`. Include statuses PROPOSED / TESTED / REJECTED for hypotheses and source/time/seed for findings.

A handoff command should say:
- What is finished and tested;
- What branch/commit was used;
- Current top baseline and its actual metrics;
- What failed and why;
- Next three actions;
- Safety/rule restrictions;
- Commands to reproduce results.

The external `akitaonrails/ai-memory` must remain OFF until separate authorization after a proper review. Do not register global Codex hooks as part of the main build.

## TEAM WORKFLOW AND TWO DEVICES

Create `docs/TEAM_OPERATIONS.md` for teams of 2, 3 and 4, with owners for (a) statement/rules and algorithm, (b) data/research/validation, (c) implementation/integration, (d) game/optimization or QA. If only 2 people, merge roles.

Use one Git repo and short-lived branches; one integration owner. Avoid two agents editing the same module. Require tests before merging. Keep stable `main` and a labeled last-known-good submission. If laptop or internet fails, the most recent verified solution and PDFs should remain usable offline.

Do not connect a corporate account/laptop or corporate AI usage to this personal project without explicit organizational permission. Never transfer employer data, proprietary code, personal credentials or account tokens.

## EXECUTION PLAN AND PRIORITIES

**P0 — MUST WORK BEFORE ANYTHING ELSE:** project installs, CLI doctor, rule register, source review, one working trading baseline, one working ML baseline, one working allocation solver, one working game solver, deterministic test run, one actual generated PDF, one-page quick-start and handoff. Run each end to end.

**P1 — STRONG PREP:** Optiver simulator research/practice integration kept separate and license-compliant; event order and risk management, another 4–6 baseline strategies, ML leakage checks, paired tournament, expanded game solvers, extra offline quick cards and team playbook.

**P2 — ONLY IF P0/P1 PASS:** advanced A–S/queue models, contextual bandits, options Greeks, JAX optimization, interactive dashboard, elaborate simulator, third-party plugins. Do not sacrifice stability for P2.

Allocate your time by testable results, not by number of files. Maintain `docs/PROGRESS.md` with PASS / FAIL / BLOCKED, actual run commands and output snippets. If you hit context/usage limits, leave a clean commit and handoff so the next session can continue immediately.

## ACCEPTANCE DEMONSTRATION

Before finishing, demonstrate on clearly labeled synthetic/example data:

1. A simulated trading day with two strategies and correct cash/position/PnL ledger.
2. A time-ordered ML train/test comparison against a trivial baseline.
3. A resource allocation puzzle solved by enumeration and an optimization method with matching answers on small cases.
4. A game-theory puzzle with a stated payoff matrix and verified best response or equilibrium.
5. A generated PDF linked to a real experiment ID, with sourced tables/charts.
6. `arena doctor`, `arena validate`, and an offline handoff.
7. A runnable checklist for adapting to a new official problem in under 30 minutes (not a claim that all unknown tasks can be solved in 30 minutes).

Deliver a final concise report: implemented modules, successful tests, known limitations, risky assumptions, exact run commands, source/license constraints, and what I personally should learn before November 7.

**Your most important design test:** If the contest turns out to be an unexpected optimization game, ML table, market-making simulator, or strict one-file Python task, can I immediately find the relevant code, run a correct baseline and improve it without starting from zero?

BEGIN NOW: inspect the README and links, create the rules/source inventory, establish one runnable vertical slice, then continue implementing and testing. Do not stop at a proposal.
