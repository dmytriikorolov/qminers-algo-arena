# Source Repositories, Useful Skills, and Security Gates

Prepared November 3, 2026. This is a reading and implementation priority map, not an endorsement of external software.

## A. What to study and copy as an *idea*, not as unquestioned code

| Source | Files actually inspected in preparation | Transferable lesson | Don't transfer | Priority |
|---|---|---|---|---|
| [Qminers 2024 winner](https://github.com/AdamBobocky/qminers-24) | `README.md`, `COMPETITION_README.md`, repository layout | Combine simple submodels, local evaluation, calibrate risk for tournament rules, preserve submission interface | NBA modeling and 2024 API as 2026 facts | HIGH |
| [Qminers 2025](https://github.com/dmytriikorolov/QH2025) | `README.md`, `src/model.py` excerpt, `src/evaluate.py` | Exact interface and environment first; model only after local evaluator works; baseline/ensemble structure | Hockey features, outdated environment, old betting API | HIGH |
| [Optiver Ready Trader Go archive](https://github.com/trietvuive/optiver-ready-trader-go) | `Readme.md`, `autotrader.py`, root structure | Run actual exchange simulator, handle fill/status callbacks, message rate limits, position, replay and scores | Fixed ETF/future rules; blocking sleeps in async handlers; automatic code copying (AGPL) | VERY HIGH for a live book |
| [IMC Prosperity 2024](https://github.com/pe049395/IMC-Prosperity-2024) | `README.md`, `submissions/round5.py` excerpt, root structure | Fair-value trading, order book signals, inventory, basket/option cases, compressed single-file data/state logging | Hardcoded assets, prices, product limits, undocumented format assumptions | VERY HIGH |
| [IMC Prosperity 2024 manual solutions](https://github.com/gabsens/IMC-Prosperity-2-Manual) | Public README and described notebooks | Probability, exact enumeration, optimization, clear mathematical writeups | Treating a 2024 game as a 2026 problem | HIGH if manual/game |
| [IMC Prosperity 2025 manual solutions](https://github.com/nathanbronson/Prosperity2025) | Public README and described solution types | Currency conversion graph, reward-sharing congestion game, portfolio allocation | Assumption that all rivals are rational | VERY HIGH if game |
| [IMC Prosperity 2026 student report](https://github.com/marcobattiston21/imc-prosperity-4) | Public README | Auction, capital allocation, options, sequential rounds, product-specific strategies | Hardcoded simulation quirks and unstated rules | HIGH |
| [Optiver how-to-play](https://readytradergo.optiver.com/how-to-play/) | Official page | Trade at fair prices, manage risk, inspect exchange logs and market conditions | One contest's detailed exchange rules | HIGH |

**How Codex should research these:** use a clean `research/third_party` directory or source links; examine implementations and dependencies one by one; record license requirements; do not vendor entire repos into our submission. Run external simulators only when their license and local environment make it reasonable. Preserve provenance and compare code to tests.

## B. Skills worth having on the personal Mac

A skill is a small repeatable workflow, often with a `SKILL.md` and helper scripts; it is not a substitute for actual command-line tools. Keep references on demand rather than loading thousands of words into every prompt.

### Official/curated — shortlist

- **`skill-creator`** ([source](https://github.com/openai/skills/tree/main/skills/.system/skill-creator)): creates/validates well-structured task skills. Usually shipped as a system skill; check your current Codex before attempting installation. **Top choice.**
- **`jupyter-notebook`** ([source](https://github.com/openai/skills/tree/main/skills/.curated/jupyter-notebook)): reproducible experimentation and tutorial notebooks. **Top choice.**
- **`pdf`** ([source](https://github.com/openai/skills/tree/main/skills/.curated/pdf)): PDF creation/extraction checks. **Good for report output**, but actual chart/metric generation must be deterministic Python.
- **`security-best-practices`** ([source](https://github.com/openai/skills/tree/main/skills/.curated/security-best-practices)): useful for reviewing Python code and third-party integrations when explicitly requested. **Useful for security reviews**, but not a substitute for supply-chain auditing.
- **`gh-fix-ci`** ([source](https://github.com/openai/skills/tree/main/skills/.curated/gh-fix-ci)): only if GitHub Actions starts failing. **Optional.**
- **`playwright`** ([source](https://github.com/openai/skills/tree/main/skills/.curated/playwright)): only if the organizer provides a web UI worth testing. **Optional, not for normal analysis.**

Install curated skills by documented Codex skill-installer methods, after inspecting the exact source and only if you actually need them. Check if they are already installed. Do not stack many unrelated external skills; every extra integration is a maintenance/security cost.

### Custom skills — much more valuable for this event

- `arena-triage`: read official task, rules and decide which family applies.
- `arena-market`: inspect book, fair value, costs and possible signals.
- `arena-ml`: split safely, fit simple baselines, inspect leakage.
- `arena-game`: model payoffs, opponents and game rules.
- `arena-optimize`: exact small oracle then DP/LP/MILP.
- `arena-experiment`: test on identical data and seeds, record outcomes.
- `arena-report`: create 1–2 page PDF from experiment files.
- `arena-debug`: inspect failing cases and accounting invariants.
- `arena-handoff`: current strategy + commit + failed attempts.
- `arena-submit`: exact preflight under official restrictions.

A custom skill is successful only when its attached command/test works without a model call.

## C. `akitaonrails/ai-memory`: how I would decide whether to use it

The README describes a Rust service, local Git-backed Markdown wiki, MCP integration, lifecycle hooks for Codex and many other agents, multi-machine memory, and optional LLM consolidation. Those are attractive features, but the hooks can observe and record prompts/tool activity.

**Status as of this preparation:** architecture and security documentation have been inspected; **no complete SkillSpector report or independent audit of the release binary was executed**. Do NOT label it safe or globally enable it yet.

### Security gate

1. Freeze the exact source commit and release version; record SHA-256 and provenance. Avoid floating `latest` at the moment of approval.
2. Download the source for inspection, but do not install the hook or start the server.
3. Run NVIDIA SkillSpector against actual skill directories (e.g. the Codex plugin skills); save JSON/Markdown reports, check scan coverage and findings. Note that SkillSpector is for **agent skill content**, not a guarantee of safety for Rust crates, shell installers or released binaries.
4. Inspect `install.sh`, `INSTALL_FOR_AGENTS.md`, `hooks/codex`, shared hook libraries, Rust capture-policy code, handling of secrets, update mechanism and outbound requests. Search for hidden process/remote exfiltration concerns.
5. Check third-party dependencies, advisory reports and GitHub Actions provenance. Compare release hashes with published manifests; a matching hash alone does not mean the source is safe.
6. Test in a sandbox with a separate HOME, dummy repo, fake credentials and outbound network restrictions. Capture what files it reads and connections it makes.
7. Assess whether stored memory includes full prompts, tool arguments, paths or API credentials and whether redaction can fail.
8. If enabled later, install only for personal Codex, bind server to loopback with authentication, disable optional LLM/dream processing, restrict captured project paths, verify purge behavior, and keep backup/export controls.
9. Do not connect employer repositories, corporate laptop, corporate subscriptions or privileged agents to the same personal memory server.
10. Re-scan when version, hooks, dependencies or permissions change. Record explicit human approval.

### Expected value vs effort

- For **two days of hackathon preparation** alone, repo files (`memory/handoff.md`, `experiments.jsonl`, `decisions.md`) already solve 70–80% of the *workflow problem* (a qualitative judgment, not a benchmark), with very little complexity.
- For **many future multi-agent projects**, ai-memory could save real context transfer time if the security review and integration prove clean.
- If setup or debugging takes a substantial fraction of the preparation window, defer it until after the event; first finish working baselines.

## D. What NOT to install now

Random 'quant genius' skills, unknown exchange connectors, paid data feeds, frameworks that force remote LLM calls for every market tick, giant model checkpoints, large vector databases, complex microservice stacks or unverified MCP servers. None should be a prerequisite for producing a valid Qminers submission.

## E. Reading on paper vs reading code

**Paper, after baseline:** Avellaneda–Stoikov for inventory-aware quotes; Cont/Kukanov/Stoikov for order-flow imbalance; microprice estimators for short-horizon fair value. Keep notes about assumptions and what input data the equation needs.

**Code, before paper:** Optiver exchange replay, IMC `round5.py`, Qminers local evaluator, exact/DP game solver. They make execution mistakes and scoring constraints visible.

**Professional standards, for discipline:** [FIA guide to automated trading systems](https://www.fia.org/sites/default/files/2019-09/FIA-Guide-to-the-Development-and-Operation-of-Automated-Trading-Systems_1.pdf), [Optiver technology](https://www.optiver.com/what-we-do/technology/), [Jane Street overview](https://www.janestreet.com/what-we-do/overview/). Focus on stale-data checks, order limits, risk and clear ownership.

## F. Nov 5–6 usage plan

**Before weekly reset (Nov 3–4):** personally read the field guide, check competition eligibility/rules, set up private repo, Python/uv and basic git access. Do not waste intensive Codex usage on random tutorials. Confirm when on Nov 5 the reset actually occurs.

**Nov 5 after reset:** run the master prompt. P0: source/rules inventory, basic CLI, small trading/ML/game/allocation baselines, tests, first PDF. Make a clean commit/handoff. Give the agent autonomy only inside the project.

**Nov 6 daytime:** deepen the strongest areas, exercise Optiver simulator separately, develop at least one integration rehearsal, generate offline quick cards, test on independent scenarios. Check actual official task announcements if any.

**Nov 6 before 23:25 Prague:** freeze a stable version and a reproducible environment. Finish PDFs and handoff. Do not begin a risky new framework install just before the usage window expires. Keep some weekly quota for actual hackathon surprises if possible.

**Nov 7–8:** official rules and task override everything prepared. Select the closest template and submit a baseline early. Use competition data only where allowed. Keep last-known-good submission and coordinate team work.

**Two-device note:** use work hardware or employer-paid AI accounts only with explicit permission and within company policy; otherwise keep the project on the personal Mac. Personal Git worktrees provide safe parallel branches without workplace involvement.
