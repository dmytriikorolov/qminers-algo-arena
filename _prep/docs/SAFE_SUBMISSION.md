# Preparing the final submission

`src/arena` is a preparation library. Reports, experiment storage, Git metadata and local memory belong to development. No official submission contract has been verified yet; a local preflight cannot establish organiser acceptance.

`arena package SOURCE.py --contract CONTRACT.json --output submissions/CANDIDATE.py` makes a byte-exact copy of an already self-contained file after static checks, plus an adjacent `.manifest.json`. It never overwrites, executes, resolves transitive dependencies or submits. Both source and manifest are preserved if an unrelated write error interrupts packaging; use a new output name. `submission_ready` always remains false until an official evaluator is run and reviewed separately.

When Technical Rules arrive:

1. Save their version and fill every unknown in `COMPETITION_RULES.md`.
2. Start from the official sample and preserve its exact class/function signature and schema.
3. Select the smallest algorithm needed. Package only permitted imports and artifacts. Keep plots, PDFs, agent tools and handoff code out of execution.
4. Check allowed filesystem, networking, processes, package versions, threads, RAM and wall-clock. Use explicit seeded randomness if permitted. Avoid hidden downloads and startup hooks.
5. Run the official evaluator on the untouched sample and the packaged candidate. Validate empty/malformed inputs, boundary budgets/positions, fees, stale data and duplicate callbacks as relevant.
6. Save the exact submitted file, its SHA-256, environment, evaluator command, result and rollback candidate. Ensure no unexpected stdout or credentials enter the artifact.
7. Reproduce from a fresh local environment and confirm the website accepted the intended artifact before calling it submitted.

**Third-party sources:** the reviewed Optiver simulator contains AGPL-3.0-or-later headers. Other reviewed strategy repos had no root licence in the inspected tree. Reading public source does not grant unrestricted reuse. Keep implementations independent; document any permitted dependencies and provenance. See `SOURCE_REVIEW.md`.

**Memory:** external ai-memory remains disabled. No global hooks or daemon are required. Repo-owned `memory/handoff.md` is enough for continuation.
