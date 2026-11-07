# QMINERS 2026 — HACKATHON-ONLY LAUNCH

**This is my first Codex session for this project. This archive contains the full preparation prompt, ten project-local skill outlines, runnable Python starter demos, research notes, and the original study PDF.**

## Exact launch workflow
1. Extract the ZIP into a NEW personal directory, such as `~/me/qminers-arena`. The project now lives directly in this repository root.
2. Open this extracted project folder in Codex.
3. Paste the complete text of `START_CODEX_HACKATHON.md` into Codex. The prompt points to `preparation/CODEX_MASTER_PROMPT.md` and all supplementary instructions.
4. Codex should run starter tests, inspect the linked repositories, implement the missing components, and write `TONIGHT_STATUS.md` with commands, test results and remaining limitations.
5. Review Codex's real test results. Running a prompt is not proof that the engine is finished or competition-ready.

## Quick check before or after Codex

```bash
# Run inside the extracted top-level folder
python3 -m unittest discover -s starter_tests -v
python3 -m starter_arena doctor
python3 -m starter_arena all-demos
```

The starter is a small offline Python scaffold; it is not an official contest submission and has no demonstrated trading edge.

## Included
- `preparation/`: original master prompt, study PDF and Markdown, source and security research.
- `.agents/skills/`: ten project-local instructions (not automatically executing tools).
- `starter_arena/`, `starter_tests/`: runnable basic demos and deterministic tests.
- `playbooks/`: scenarios, team roles, acceptance criteria and emergency plans.
- `research/`: source index and provenance.
- `security/`: AI-memory evaluation checklist (not a completed security scan).

## Repositories
- https://github.com/dmytriikorolov/qminers
- https://github.com/AdamBobocky/qminers-24
- https://github.com/dmytriikorolov/QH2025
- https://github.com/trietvuive/optiver-ready-trader-go
- https://github.com/pe049395/IMC-Prosperity-2024
- https://github.com/akitaonrails/ai-memory
- https://github.com/NVIDIA/SkillSpector

The official rules outrank all assumptions; the four modules are described themes, not four guaranteed independent rounds.
