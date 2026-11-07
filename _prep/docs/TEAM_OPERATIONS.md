# Team operations

Published rules require an accepted team of 2–4 and in-person participation. Teams must work independently; during the event do not publicly post task questions or seek advice from specific outside people. Use organisers for clarifications; Technical Rules can add restrictions.

| Team size | Ownership |
| --- | --- |
| 2 | Person A: rules, strategy and data. Person B: official adapter, integration and validation. Cross-review each other's result. |
| 3 | Person A: rules/strategy. Person B: data/experiments. Person C: integration/official evaluator/submission. |
| 4 | Person A: rules/algorithm. Person B: data/research. Person C: implementation/integration. Person D: game/optimisation or independent QA. |

One integrator owns the official contract and final artifact. Helpers get named modules and clear interfaces; two agents should not edit the same file concurrently. Use short-lived branches/worktrees when practical. Merge only after relevant tests and a reproducible score; preserve stable `main` and an explicit known-good submission checkpoint.

Each experiment records seed, configuration, input fingerprint, code revision and metric. Compare changes on identical cases first, then new seeds/windows. Reuse one quiet baseline while research runs separately. No model call, report rendering, network fetch or unbounded search belongs in a time-critical market callback.

Every 60–90 minutes each owner states the latest finding, actual best score, largest unverified assumption, next action and known-good artifact. Stop speculative refactoring near the deadline. Run the full official-contract check and allow time for submission retries.

For a handoff run the local CLI and read `memory/handoff.md`: include exact commands/results, changed files, failed attempts, unknowns and next three actions. Keep PDFs and the stable baseline usable offline. Use only authorised personal equipment/accounts and project data.
