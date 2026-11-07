# Team and Agent Workflow

## People
- **Integrator / submission owner:** one person owns the official API adapter, final merge and final submit.
- **Researcher:** data quality, signals, statistical tests, controlled experiments.
- **Strategy builder:** baseline and one improvement at a time, in a separate branch.
- **Validation owner:** reproduces scores, tests the actual scoring function, checks for leakage and runtime failures.
Roles can be combined with a small team. Decide roles based on strengths, not titles.

## Agent roles (Codex sessions, not autonomous authority)
- Coordinator: tracks plan and ownership, never edits every branch at once.
- Research: reads provided data, proposes falsifiable tests, logs findings.
- Engineer: makes isolated, test-backed changes.
- Validator: runs clean-room evaluation, compares scores, checks contracts.

## Git rules
- Only one protected integration branch.
- Separate branches or worktrees for different tasks.
- Every experiment has an ID, input fingerprint, seed, metric and Git commit.
- Merge only after tests pass and the integrator understands the change.
- Keep a known-good submission checkpoint.
- Never place credentials or confidential work data in repository or shared agent memory.

## What I say every hour (plain English)
1. What did we learn from the latest data?
2. What is the best tested strategy **right now**?
3. What is the riskiest unverified assumption?
4. What will each person work on next?
5. Which code version could we submit immediately?

## Before asking another agent to continue
Run `$arena-handoff`. The handoff must state the task owner, files, actual test commands and results, unresolved questions and next steps. Handoff text is not a substitute for Git commits.

## Work laptop
Use employer laptop, AI subscriptions and sync only if company explicitly permits personal competition work and access to this repository. Do not mix personal competition code with employer data or ChatGPT Business workspace. Avoid treating usage from separate subscriptions as one automatic shared pool.
