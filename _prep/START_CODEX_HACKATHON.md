# TONIGHT — START QUANT ARENA LAB

I have NOT started this project before. Treat this as the FIRST Codex session for Qminers 2026 and build it now.

READ `preparation/CODEX_MASTER_PROMPT.md` COMPLETELY AND EXECUTE IT. Also consult `preparation/README_START_HERE.md`, `preparation/ENGLISH_FIELD_GUIDE.md`, and `preparation/SOURCES_SKILLS_AND_SECURITY.md` when relevant. Do not assume the main software exists: the preparation kit contains instructions and source research, not a working engine.

My GitHub preparation repository is `https://github.com/dmytriikorolov/qminers` (private, my account). Inspect its README and links (including Qminers 2024 winner, QH2025, Optiver Ready Trader Go, IMC Prosperity 2024) before choosing architecture. Do not treat its four module names as four confirmed independent tasks. This repo has not been used to build our solution yet.

EXTRA SKILL CONTEXT FROM MY NOVEMBER 6 CHAT: My expanded kit proposes these ten project skills: arena-diagnose, arena-research, arena-strategy, arena-market, arena-ml, arena-benchmark, arena-debug, arena-handoff, arena-submit, arena-report. Minimal copies of their SKILL.md outlines are already supplied under `.agents/skills/`. Implement or improve their underlying working CLI/scripts; DO NOT stop after writing prompts.

DEADLINE: I have a special Codex usage window ending tonight November 6, 2026 at 23:25 Prague time. Prioritize producing demonstrably working, tested foundations BEFORE that time. Do not spend the window writing hundreds of pages or an elaborate visual dashboard. I am cooking dinner, so continue autonomous non-destructive local work without frequent questions.

STRICT ORDER:
1. Read official rules if accessible, identify unknowns; do not assume prewritten code is admissible. Do not install third-party ai-memory or global hooks; SkillSpector scan alone is not security approval.
2. Inspect my four linked repositories *beyond* their READMEs and record what to take vs avoid, including license constraints for Optiver's AGPL components.
3. Set up a minimal Python project with deterministic tests and a working `arena doctor`, `arena inspect`, `arena baseline`, `arena validate` CLI.
4. Implement ONE runnable end-to-end demo for EACH potential task family: market data/trading; tabular ML; resource allocation or adversarial game; coding/automation.
5. Build an experiment evaluation loop, a simple report generator using actual data (PDF where dependency available), and persistent local `memory/handoff.md`.
6. Improve the most promising feature only after all four smoke demos work, then build testable extras.
7. Generate an end-of-run report `TONIGHT_STATUS.md` with: commands actually run, pass/fail tests, generated files, missing requirements, best next step when official specification appears.

Do not push/deploy, access corporate files, purchase APIs, or install system-level third-party hooks. Work only under this local hackathon directory. Local packages in a venv are acceptable. Use Python by default; validate official runtime constraints before claiming submission readiness.

Don't give me a plan and stop. Implement code, test it, and leave a working project. Keep commits small and clearly written if Git is initialized; do not rewrite an existing unrelated history.


ADDITIONAL FILES SUPPLIED IN THIS MEGA KIT: read `00_OPEN_THIS_FIRST.md`, `playbooks/SCENARIOS_ENGLISH.md`, `playbooks/TEAM_AND_AGENTS.md`, `playbooks/ACCEPTANCE_CHECKLIST.md`, `research/SOURCE_MAP.md` and `security/AI_MEMORY_GATE.md`. The `starter_arena/` scaffold is present and runnable: verify with `python3 -m unittest discover -s starter_tests -v` and `python3 -m starter_arena all-demos`; then expand it into the full system. Do not mistake its synthetic fills for an official exchange. If time is very tight, prioritize correct, tested vertical slices for all four modules over paper summaries or optional AI-memory.
