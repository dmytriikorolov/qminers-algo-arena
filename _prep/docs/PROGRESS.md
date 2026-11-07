# Progress and evidence

| Capability | Status | Evidence and limit |
|---|---|---|
| Original material read/preserved | PASS | All supplied Markdown, skills, starter code/tests and 10-page PDF read; original kit commit `8df55fa` |
| Source/rules inventory | PASS / TECHNICAL BLOCKED | `SOURCE_REVIEW.md`, `COMPETITION_RULES.md`; exact runtime/API rules pending opening |
| Local tests | PASS | Latest validate: 176 tests, no failures/skips; `memory/validation.json` |
| Dependency-light core | PASS | `PYTHONPATH=src python3 -S -m unittest discover -s tests -q`: 165 tests OK, 5 optional skips |
| Four vertical slices | PASS | Six saved baseline runs (including classifier and LP variants), `reports/index.json` |
| Market stress comparisons | PASS / SYNTHETIC | 8 named policies x 5 paired seeds x 3 regimes; no official edge claim |
| CSV feature analysis | PASS | Snapshot, bar, trade CLI checks; causal/unknown-side tests |
| PDF reports | PASS | Six experiment PDFs (1–7 pages), six-page cards; pypdf checks and representative visual renders |
| One-file preparation | PASS / STATIC ONLY | 12 packaging tests; example manifest, no execution or official certification |
| Local handoff/skills | PASS | Fingerprint freshness checked; ten skill validations |
| Environment | PASS | Isolated native ARM optional dependencies; pip check clean; global packages unchanged |
| Official competition evaluation | BLOCKED | No released contract/evaluator verified |
| CI | CONFIGURED, NOT RUN REMOTELY | `.github/workflows/tests.yml`; no push performed |

See `../TONIGHT_STATUS.md` for exact commands, observed metrics, changed file groups and remaining work.
