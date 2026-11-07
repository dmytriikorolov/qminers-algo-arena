# Sources: what to read, take, and avoid

- Qminers 2024 winner: https://github.com/AdamBobocky/qminers-24 — take baselines, backtesting, ensembles and tournament-risk simulation. Avoid NBA-specific inputs and assuming the same scoring.
- Qminers 2025 starter: https://github.com/dmytriikorolov/QH2025 — take exact evaluation-contract testing and environment reproduction. Avoid copying a sports betting `place_bets()` contract into 2026.
- Optiver Ready Trader Go: https://github.com/trietvuive/optiver-ready-trader-go — take ideas from `Readme.md`, `autotrader.py`, `rtg.py`, and exchange simulator: callbacks, partial fills, risk/message limits, local replay. Avoid copying old instrument assumptions, blocking sleeps in an event loop, or AGPL code into submission without legal review.
- IMC Prosperity 2024: https://github.com/pe049395/IMC-Prosperity-2024 — take fair-value estimation, liquidity analysis, inventory-aware quotes, cross-asset spreads, competition-specific scoring verification. Avoid hardcoded product names/hidden-price assumptions.
- NVIDIA SkillSpector: https://github.com/NVIDIA/SkillSpector — scan skills for vulnerabilities, but not a general binary audit.
- akitaonrails ai-memory: https://github.com/akitaonrails/ai-memory — optional future handoffs; do not install until security gate.
- OpenAI curated skills: https://github.com/openai/skills — inspect skill-creator, jupyter-notebook, pdf, security-best-practices, and others *only if needed*; install minimal capabilities, never blindly install a skill bundle.

## Core theory starting points
- Avellaneda–Stoikov: https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf
- Cont, Kukanov, Stoikov, order flow impact: https://www.sashastoikov.com/finance/2015/3/12/the-price-impact-of-order-book-events
- Microprice: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694
- LOB overview: https://people.maths.ox.ac.uk/~porterm/papers/gould-qf-final.pdf

No remote PDFs are embedded; research URLs and descriptions are references, not proof that their full contents were read in this session.
