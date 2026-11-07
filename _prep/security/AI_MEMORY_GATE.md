# AI-memory: NOT APPROVED for installation yet

Repository: https://github.com/akitaonrails/ai-memory
Scanner: https://github.com/NVIDIA/SkillSpector

The repo provides a Rust service, Codex hooks, durable Markdown storage, handoffs and optional networked synchronization. Useful, but hooks can observe user prompts/tool activity. A clean scan of `SKILL.md` alone does NOT audit installer, binary, native hooks, dependencies or network behavior.

## Safe review process
1. Pin the exact Git commit and release digest. Inspect README, LICENSE, INSTALL_FOR_AGENTS.md, docs/security.md and security-boundaries.md.
2. Clone to an isolated directory, do not run setup. Read install.sh, Codex hooks, binary download/checksum verification, server configuration, outbound requests and capture policy.
3. Install SkillSpector in an isolated virtual environment after reviewing its own installation path. Static-scan the relevant agent-skills paths, not only the README. Example command *after scanner installation*:
   `skillspector scan ./candidate-ai-memory/plugins/codex/skills --recursive --max-skills 32 --no-llm --fail-on-incomplete --format json --output memory-skill-scan.json`
4. Review all findings and skipped files. Scanner verdict isn't a comprehensive binary safety verdict. Separately examine dependency CVEs and whether the check made external requests.
5. Test in a sandbox with fictitious data and no credentials. Monitor file access and network access. Measure memory overhead and unwanted capture.
6. Produce a signed-off recommendation: approved for local Codex only / reject / deferred.
7. Never install hooks, start daemon, or share memory server without explicit user approval.

For tonight: use `memory/handoff.md` and Git instead. This costs no tokens and does not grant persistent capture privileges.
