# Morning integration: 7 November 2026

**Gate:** official integration remains blocked on the organisers' Technical Rules, sample and evaluator. The public check at **2026-11-06 23:17:40 Europe/Prague** found the same Official Rules, not a published runtime contract. Python, conditional AI/research permission and teams of 2–4 are verified; runtime/API/scoring remain unknown. Evidence URLs, hashes and rule sections are in [COMPETITION_RULES.md](COMPETITION_RULES.md).

One integrator owns the official sample/adapter; one teammate records rules and checks accounting. Complete this sheet before treating preparation results as contest evidence. Use only organiser-authorised access.

| Check | Record or verify from official materials |
| --- | --- |
| Rules and version | Source URL/file, retrieval time, version/hash; technical clarifications; pre-event code/weights, AI, external data and licence permissions. |
| Signature and state | Exact file/class/function name, arguments, field types, units and return schema; callback order; process reset boundaries; state persistence/serialisation; deterministic seeding. Preserve the sample interface. |
| Environment | Python and dependency versions; import rules; OS/architecture if relevant; network/files/subprocess permissions; exact launch command. |
| Resource limits | CPU/threads, RAM, wall-clock and per-callback limits; startup budget; timeout/error handling. Measure the packaged artifact under those limits. |
| Data timing | Event time versus availability time; ordering/ties; snapshot versus incremental updates; warm-up/history windows; label reveal times; permitted training/test data. Never use future information. |
| Orders and fills | Supported actions, tick/lot/minimum size; acknowledgement latency; matching/queue rules; partial fills, duplicate IDs and rejected orders; distinguish submitted, accepted and filled quantities. |
| Cancellation | When cancellation becomes effective; whether replacement is atomic; fill/cancel races; whether old and replacement orders can coexist. |
| Fees and accounting | Maker/taker fee or rebate signs and units; cash and inventory updates; funding/borrow/other costs if present. Hand-check one tiny round trip against evaluator output. |
| Risk and scoring | Position/cash/leverage/order limits including pending exposure; rejection versus penalty; terminal liquidation/marking; exact objective, aggregation, hidden evaluation and ties. Hand-check one scored case. |
| Submission and output | Accepted layout/size, allowed artifacts, deadline/timezone, attempt limits and final-selection action; stdout/stderr/serialization rules, non-finite values and empty actions. Do not infer active settings from UI strings. |

Apply market-specific rows only if the actual task uses orders. For another task, record its corresponding action, cost, constraints and terminal payoff; do not invent an exchange adapter.

1. Run the untouched official sample with the organisers' exact evaluator command. Save environment/version, stdout/stderr and result. Resolve failures before strategy work.
2. Connect the smallest legal baseline through the verified contract. Compare a hand-computed case and boundary/no-action cases; for trading include partial/duplicate fills, cancellation races, pending exposure and terminal valuation.
3. Run the official evaluator on the exact packaged candidate, repeat if determinism is required, and compare with the untouched sample. Local mock replay and static preflight are preparation checks only.
4. Save artifact SHA-256, config/seed, evaluator command, score, peak resources and known-good rollback file. Record website acceptance/final selection separately from local evaluation; submit only through the authorised flow.

Evidence record to fill locally:

```text
Technical Rules source/version/hash + retrieval time:
Official sample/evaluator source/version/hash:
Exact environment and evaluator command:
Baseline artifact SHA-256 + official result + resource use:
Candidate artifact SHA-256 + official result + resource use:
Accepted submission ID/final selection + deadline/timezone:
Remaining organiser clarification:
```
