# Optional local sweep — prepared, scheduling disabled

This is synthetic sensitivity checking, not official scoring or evidence of live
profitability. No cron, launchd, hook, background job, or external service is
installed or enabled. Start a process manually only after freezing the source.

From the project root, run once immediately with a fresh UTC run ID:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/overnight_sweep.py --run-key 20261106T223000Z
```

Optional tomorrow, **7 November 2026 at 02:00 Europe/Prague**: the following
manually started process waits once, runs once, then exits. This command has not
been started. Keep the terminal open and the computer awake if choosing to use it.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/overnight_sweep.py --run-key 20261107T010000Z --start-at 2026-11-07T02:00:00+01:00
```

The default cap is four fixed regimes (`mean_reverting`, `trend`, `trend_down`,
`volatile`) × seeds 0–19 × three fixed strategies (`fixed`, `inventory`,
`guarded_fixed`) × 300 steps: 240 replays and 72,000 replay steps. The generator
also supplies the initial snapshot. This is a small single-process CPU job, not
an estimate of hours of useful work. Lower budgets are allowed; higher budgets
are rejected. Active evaluation has a hard 20-minute alarm. Waiting mode also
stops before 07:00 Prague time on its scheduled day; waiting is limited to the
next 24 hours. Ctrl-C stops the process.

Only `overnight_runs/<UTC ID>/result.json` is written. It contains configuration,
paired seeds, compact metrics without equity curves, git revision, source hash,
and final status. The ignored output directory is exclusively reserved before
waiting; the same key is never overwritten, even after interruption or failure.
A directory lock prevents concurrent sweep processes. Source edits before or
during evaluation abort the run. Results do not change strategy code or select
a production strategy. No model calls, network, submissions, or tracked-memory
writes occur; the helper does not call `experiments.run`.

Tiny manual check (use a fresh key):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/overnight_sweep.py --run-key 20261106T223001Z --seeds 2 --steps 30
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_overnight_sweep.py
```
