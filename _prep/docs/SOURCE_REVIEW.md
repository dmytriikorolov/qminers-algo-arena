# Source review and implementation decisions

Reviewed 2026-11-06. External sources were read through the connected GitHub service and public HTTPS, **not executed**. This is targeted inspection of named files/functions, not an audit of every line or a reproduction of historical results. No external trading code was copied into `src/arena`.

## Decisions that follow from the review

1. Establish the actual interface and evaluator before adding models. The 2025 user fork has evolved beyond its original starter; even its local evaluation script makes dataset assumptions.
2. Keep signal, risk and accounting separate. Reserve worst-case pending exposure, and interpret incremental fills separately from cumulative order status.
3. Learn from simple, causal submodels and compare them on chronological data. Historical product names, price levels, limits and probability tweaks are not transferable parameters.
4. Build exact small-case oracles for games. Optimise the stated objective and test several opponent models instead of assuming everyone behaves rationally.
5. Keep simulation assumptions visible. A correct cash ledger does not establish realistic fills, and a good synthetic score does not establish trading edge.

## Primary sources

### Local preparation repository

Source: [dmytriikorolov/qminers](https://github.com/dmytriikorolov/qminers). Examined the local root `README.md`, complete launch/master instructions, playbooks, source/security notes, local skill outlines, starter code/tests and Markdown field guide. The checked-out Git revision is recorded by experiment metadata; the supplied launch directory was untracked at session start.

**Problem:** organising preparation for an unknown contest. **Take:** Python preference, minimal memory footprint, four task families and source-first validation. **Avoid:** assuming marketing modules are four independent rounds or treating notes as official rules. **Licence:** no root licence was present in the initial file inventory. **Action:** preserve the original preparation material and build tested CLI slices alongside it.

### Official 2026 competition pages

Sources: [home](https://arena.qminers.com/), [rules](https://arena.qminers.com/rules), and the [public asset actually read](https://arena.qminers.com/assets/index-D86aCFqk.js). Examined both published rule translations and submission/leaderboard UI strings. Exact asset hash and verified/unknown rules are in `COMPETITION_RULES.md`.

**Problem:** legal participation and technical-rule precedence. **Take:** Python final submission; AI/public sources permitted for development subject to Technical Rules; 2–4-person independent teams. **Avoid:** inferring execution limits or scoring details from UI strings. **Rights:** source was inspected for rules, not reused as application code. **Action:** obtain the opening Technical Rules before writing the official adapter.

### Qminers 2024 winner

Pinned commit: [`3c1147bd8a7e5ca313f5c478be81c26cf34c9657`](https://github.com/AdamBobocky/qminers-24/tree/3c1147bd8a7e5ca313f5c478be81c26cf34c9657).

Examined [README](https://github.com/AdamBobocky/qminers-24/blob/3c1147bd8a7e5ca313f5c478be81c26cf34c9657/README.md), [`src/submit_model/model.py`](https://github.com/AdamBobocky/qminers-24/blob/3c1147bd8a7e5ca313f5c478be81c26cf34c9657/src/submit_model/model.py) (`Model`, data-increment order and ensemble/bet logic), [`risk_model/main.py`](https://github.com/AdamBobocky/qminers-24/blob/3c1147bd8a7e5ca313f5c478be81c26cf34c9657/risk_model/main.py), and [`risk_model/boostrap_optimizer.py`](https://github.com/AdamBobocky/qminers-24/blob/3c1147bd8a7e5ca313f5c478be81c26cf34c9657/risk_model/boostrap_optimizer.py).

**Problem:** NBA betting predictions, ensembles and tournament risk. **Take:** generate features before consuming newly finished games; compare probability models; distinguish expected wealth from winning probability. **Avoid:** NBA fields, year thresholds, odds adjustments and historical bet limits. **Static concerns:** `main.py`'s grid search never returns a result before caller unpacking; randomness is unseeded. These are observed code issues, not runtime test results. **Licence:** GitHub metadata reported none and no root licence appeared in the inspected tree; no permission for unrestricted copying assumed. **Action:** independent seeded tournament example with explicit objective and oracle tests.

### Qminers 2025 user fork

Pinned commit: [`78ceeafa857915b02bce970f6a0bfe6a90f887c7`](https://github.com/dmytriikorolov/QH2025/tree/78ceeafa857915b02bce970f6a0bfe6a90f887c7).

Examined [`src/environment.py`](https://github.com/dmytriikorolov/QH2025/blob/78ceeafa857915b02bce970f6a0bfe6a90f887c7/src/environment.py), [`src/evaluate.py`](https://github.com/dmytriikorolov/QH2025/blob/78ceeafa857915b02bce970f6a0bfe6a90f887c7/src/evaluate.py), and [`src/model.py`](https://github.com/dmytriikorolov/QH2025/blob/78ceeafa857915b02bce970f6a0bfe6a90f887c7/src/model.py) (imports, feature-state updates and final `Model` implementation), plus root/source listings.

**Problem:** three-outcome hockey betting. **Take:** evaluate only revealed historical results, preserve state between increments, validate opportunities and budget before placing bets. **Avoid:** calling this current fork an untouched official starter: evaluation imports `meta_model`, filters post-2015 rows and loads a specific round dataset. The bundled model uses a prefit calibration wrapper without visibly fitting its base estimator first; dependency-specific behaviour needs reproduction before reuse. **Licence:** none in metadata/root listing. **Action:** use its historical contract as a checklist, not the 2026 API; build train-only preprocessing and explicit class labels independently.

### Optiver Ready Trader Go archive

Pinned commit: [`8eefbf0be4e3e2d958dcb224a466c7889d859d53`](https://github.com/trietvuive/optiver-ready-trader-go/tree/8eefbf0be4e3e2d958dcb224a466c7889d859d53).

Examined [`autotrader.py`](https://github.com/trietvuive/optiver-ready-trader-go/blob/8eefbf0be4e3e2d958dcb224a466c7889d859d53/autotrader.py) (order management/callbacks), [`ready_trader_go/account.py`](https://github.com/trietvuive/optiver-ready-trader-go/blob/8eefbf0be4e3e2d958dcb224a466c7889d859d53/ready_trader_go/account.py), [`competitor.py`](https://github.com/trietvuive/optiver-ready-trader-go/blob/8eefbf0be4e3e2d958dcb224a466c7889d859d53/ready_trader_go/competitor.py) (insert validation), and [`COPYING.txt`](https://github.com/trietvuive/optiver-ready-trader-go/blob/8eefbf0be4e3e2d958dcb224a466c7889d859d53/COPYING.txt) header.

**Problem:** event-driven ETF/future market simulation. **Take:** incremental fill vs cumulative status distinction, signed fee/rebate handling, tick validation, unique order IDs, limits and self-cross checks. **Avoid:** hardcoded instruments/ticks, cross-instrument sequence assumptions, `time.sleep` in callback paths and treating its special final valuation clamp as universal. **Licence:** file headers specify AGPL-3.0-or-later; root COPYING contains AGPL v3. Keep simulator practice isolated; no copied source in our package. **Action:** independently test accounting and pending-order/cancel races. Simulator was not installed or run. Official [how-to-play](https://readytradergo.optiver.com/how-to-play/) returned HTTP 502 via browser fetch; no claims depend on its unread contents.

### IMC Prosperity 2024 strategy

Pinned commit: [`fc0d53ba92f318479e66a95849c224fb83254e8e`](https://github.com/pe049395/IMC-Prosperity-2024/tree/fc0d53ba92f318479e66a95849c224fb83254e8e).

Examined [`submissions/round5.py`](https://github.com/pe049395/IMC-Prosperity-2024/blob/fc0d53ba92f318479e66a95849c224fb83254e8e/submissions/round5.py): `Status`, book/history/position properties, market-making/arbitrage methods, option utilities and `Trader.run`.

**Problem:** multiple simulated products, baskets, conversion and options. **Take:** separate product state, cap order quantities, compare executable prices with fair value and conversion costs. **Avoid:** hardcoded product limits/ratios, historical participant signals and empirically fixed fill probabilities. **Static concerns:** empty-book `best_bid` and `best_ask` fallbacks call each other recursively; `Trade.gift_basket` refers to `Strategy.informed_trading`, while inspected strategy defines `insider_trading`. Not executed. **Licence:** no root licence in listing or repository metadata. **Action:** use independent book tests for empty/single-sided books and separate optional product families from the core.

## Additional preparation sources

### IMC 2024 manual puzzles

Pinned [`6b98149cb853e7a9a7a567745238f752cc5fb0a9`](https://github.com/gabsens/IMC-Prosperity-2-Manual/tree/6b98149cb853e7a9a7a567745238f752cc5fb0a9). Examined `README.md` and [`Round2.ipynb`](https://github.com/gabsens/IMC-Prosperity-2-Manual/blob/6b98149cb853e7a9a7a567745238f752cc5fb0a9/Round2.ipynb) Markdown/code cells, without executing outputs or retrieving embedded image statements. **Problem:** bounded conversion search. **Take:** enumerate all short paths and compare near-tied floating results carefully. **Avoid:** transferring particular rate matrices and five-trade limits. **Licence:** no root licence in inspected listing. **Action:** use tiny exhaustive conversion paths as a DP oracle; verify the actual statement's move count.

### IMC 2025 manual puzzles

Pinned [`dd0bcece2891e5d9cbe9861050de0e2c05af4890`](https://github.com/nathanbronson/Prosperity2025/tree/dd0bcece2891e5d9cbe9861050de0e2c05af4890). Examined README, LICENSE and all code cells of [`Round1.ipynb`](https://github.com/nathanbronson/Prosperity2025/blob/dd0bcece2891e5d9cbe9861050de0e2c05af4890/Round1.ipynb). Other notebook implementations were not inspected. **Problem:** recursive conversion search; README discusses shared rewards, auctions and capital allocation. **Take:** exact short-horizon enumeration and opponent sensitivity; author reports losses from assuming rational bidding. **Avoid:** treating a fixed point or guessed sentiment as established rival behaviour. **Licence:** MIT, retain required notices if material is reused. **Action:** compare several rival distributions and report sensitivity rather than a single presumed equilibrium.

### IMC 2026 student write-up

Pinned [`65cd9cbc1d861a43f7f23f211a4cc7a6b51fd587`](https://github.com/marcobattiston21/imc-prosperity-4/tree/65cd9cbc1d861a43f7f23f211a4cc7a6b51fd587). Examined README architecture/early-round sections, `pyproject.toml` and [`prosperity4/round1/Trader.py`](https://github.com/marcobattiston21/imc-prosperity-4/blob/65cd9cbc1d861a43f7f23f211a4cc7a6b51fd587/prosperity4/round1/Trader.py) base trader and early strategy functions. **Problem:** per-product quoting with serialised state, stationary and trending products. **Take:** isolate state and decrement remaining capacity when emitting orders. **Avoid:** fixed trend slopes and assuming an aggressive order necessarily fills its entire requested amount. **Static concern:** a one-sided book can leave a `None` best price used in a numerical comparison. **Licence:** no root licence in examined listing. **Action:** test absent sides and partial first-entry fills; record state based on execution rather than intention.

### NVIDIA SkillSpector

Pinned [`3fb77b4cc9a97724481a6745157efcbfb20e2f32`](https://github.com/NVIDIA/SkillSpector/tree/3fb77b4cc9a97724481a6745157efcbfb20e2f32). Examined `pyproject.toml`, `SECURITY.md`, source listing and [`src/skillspector/cli_entry.py`](https://github.com/NVIDIA/SkillSpector/blob/3fb77b4cc9a97724481a6745157efcbfb20e2f32/src/skillspector/cli_entry.py). **Problem:** security analysis of agent skill bundles. **Take:** scanner coverage/dependency inspection must be explicit; CLI entry defers heavy scanner loading. **Avoid:** treating a skill scan as a release-binary audit, or assuming the pinned preparation example command still matches current flags. **Licence:** source entry carries Apache-2.0 identifier. **Action:** only install/run in an isolated reviewed environment for a real security task. No scan was run tonight.

### Optional ai-memory

Pinned [`e67880f83fccb98075422ebe2bce4869c2e89f28`](https://github.com/akitaonrails/ai-memory/tree/e67880f83fccb98075422ebe2bce4869c2e89f28). Examined [`INSTALL_FOR_AGENTS.md`](https://github.com/akitaonrails/ai-memory/blob/e67880f83fccb98075422ebe2bce4869c2e89f28/INSTALL_FOR_AGENTS.md), [`install.sh`](https://github.com/akitaonrails/ai-memory/blob/e67880f83fccb98075422ebe2bce4869c2e89f28/install.sh), `DATA_HANDLING.md` and hook directory listing. **Problem:** durable agent context through service/hooks. **Take:** readable project-local memory is sufficient for this event. **Avoid:** running installer instructions as part of source review. Install documentation describes persistent service, MCP and lifecycle hooks; data-handling claims need code verification. **Licence/security:** root licence exists but full binary/dependency/hook audit was not performed. **Action:** leave OFF; exact future review gate is `security/AI_MEMORY_GATE.md`. No release binary downloaded, setup executed, daemon started or global hook installed.

### OpenAI skill examples

Pinned [`49f948faa9258a0c61caceaf225e179651397431`](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431). Examined [`README.md`](https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/README.md) and root listing. It marks this repository deprecated and points to `openai/plugins`. **Problem:** reusable task workflows. **Take:** concise local skill instructions that call actual tested tools. **Avoid:** installing a stale bundle or treating prompt outlines as working algorithms. **Licence:** README says to inspect each skill's own licence. **Action:** use the already supplied local skill guidance; no external skills were installed for this review.

## Theory and explicitly incomplete reading

Read the introduction and model sections of [Avellaneda–Stoikov](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf), including driftless Brownian midprice, inventory-sensitive valuation, Poisson execution intensity and quote-distance calibration. Practical lesson: inventory skew is useful, but the assumed price/execution processes need testing against the actual simulator; do not transplant parameter values or advertise optimality under unknown dynamics. No derivation was implemented from the paper tonight.

[Microprice SSRN link](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694) returned HTTP 403; full paper not read. Other theory/professional links in the preparation materials (Cont/Kukanov/Stoikov, Oxford LOB overview, FIA, Jane Street and Optiver overview) were not fully reviewed in this session. They remain optional follow-up reading after official contract integration. Historical README performance claims and stored notebook outputs were not independently reproduced.
