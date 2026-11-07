# Reproduced failures and corrections

- Global NumPy imports fail on ARM because its extension is Intel; global Matplotlib fails under Intel because its extension is ARM. Reproduced both. Left global environment alone; installed compatible optional dependencies in `.venv`.
- First local package install failed because the sandbox could not resolve the package registry. Retried with approved network access; isolated installation succeeded.
- Independent review reproduced compile-invalid code passing AST-only checks. Preflight now compiles without execution; regression tests cover illegal top-level statements and duplicate args.
- Independent review reproduced a report leaf symlink escaping its output directory. Every report output leaf is now resolved against the project root; regression test first failed, then passed after the fix.
- CSV field-limit errors escaped as tracebacks; JSON exponent overflow bypassed nonfinite checking. New tests reproduced both. CSV errors now become validation errors; JSON floats are checked for finiteness.
- Tournament initially aggregated per-scenario best score only. It now preserves each named method and candidate-minus-reference differences on identical seeds; the selection bias is explicitly labelled.
- Saved validation could be stale after edits. Validation now stores a source/test/configuration fingerprint, and handoff states whether evidence matches current files.

No historical third-party strategy was executed or its performance reproduced. No real contest evaluation has run.

## Final independent readiness pass

- Reproduced one-tick quote widening from float-before-Decimal arithmetic; fixed with a failing-then-passing regression. Old performance figures are version-specific.
- Guarded fixed quotes lower worst drawdown across four root/five reviewer regimes but reduce mean-reverting upside and remain negative under stress. Exposure-matched fixed-cap-five control often does as well or better: no novel alpha or default promotion accepted.
- Reviewer found near-quadratic scans over historical ledger orders. Bounded 300-step sweeps are fine; prolonged live use remains unready.
- Public technical rules/evaluator were still unavailable at the fresh 23:17 Prague check. No adapter invented.
