# AGENTS.md — Quant Arena local development
- Work within this repository only. No company data, personal files, secrets, or external deployments.
- Evaluate actual competition rules and runtime before treating code as submission-ready.
- Every serious change: deterministic command, test, metric, and a concise explanation for a learner.
- Separate `src/arena` (algorithm), `experiments` (results), `reports` (presentation), `memory` (handoff), `.agents/skills` (agent directions).
- Actual code and test evidence outrank quantity of features. Prefer verified baselines; flag synthetic data honestly.
- Do not enable third-party ai-memory or global hooks. Save human-readable `memory/handoff.md` locally.
- Never block the live strategy on a model call, report generation, or unbounded operation.
- On each handoff: state exact commands run, results, changed files and remaining work.
- Default to one implementation agent; isolated helper workstreams only when interfaces and ownership are clear.
