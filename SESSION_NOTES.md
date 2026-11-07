# Session notes (handoff summary)

Compact context for this project so any model can pick up where we left off.
Delete this file when it's no longer useful.

## Project
Qminers trading hackathon starter (`qminers-algo-arena`, uv, Python 3.13).
Simulator replays a fixed recorded tape (CSV); strategies subclass
`simulator.strategy.BaseStrategy`; arena builds them with NO arguments, so
tunables live as module constants. Scoring: PnL = cash + markout(inventory)
− penalty; |I| > 100 ⇒ $10k/s penalty; order actions have 5 ms latency; only
`simulator.models` + stdlib + numpy/pandas/scipy/sklearn importable in
strategies; no os/sys/open/getattr/dunder access (static check).

## Environment notes
- System `python3.13` binary is a broken orphan (Nobara upgraded to 3.14); uv
  manages its own CPython 3.13.11 — `.python-version` pins 3.13. Don't trust
  /usr/bin/python3.13.
- Zen Browser is the Flathub flatpak; WebGL needed `flatpak update` to pull the
  NVIDIA 595.112.07 GL extension.

## Strategies (all in `strategies/`)
1. `following_mean.py` — taker mean-reversion (sliding-window mean, k=100,
   deviation threshold t). RETIRED: pays the spread every fill, loses on real
   tape (−263k ungated on round1, −0.62/fill). User said keep the file as is.
2. `mean_maker.py` — **MAIN submission candidate.** Passive maker: one limit
   order at a time joined to the touch; side = reversion vs window mean beyond
   deadband, else flat-reducing side; requote only when side changes or touch
   improves past resting price; hard exposure bound (never quote if one fill
   could push |I| > 100). Params: WINDOW_SIZE=100, DEVIATION_DEADBAND=1,
   QUOTE_QUANTITY=100, EXPOSURE_LIMIT=100.
   - sample_v2.csv: PnL +158,705 (PnL/lot 0.48, z≈41)
   - round1.csv:   PnL +229,336 (PnL/lot 0.17, z≈35, penalty 0)
   - Leaderboard (first submission): rank 8/52, +164,194 ("没有内幕").
3. `mean_maker_2.py` — same maker with a local-level Kalman filter replacing
   the rolling mean (KALMAN_GAIN=0.02 ≈ k=100 memory, OBSERVATION_VARIANCE=0.25).
   VERDICT: no edge (+229,548 at matched gain ≈ +0.3%; gain 0.05 → +236k ≈ 1 se
   = noise). The estimator is not the bottleneck; the signal is.
4. `two_sided_maker.py` — both sides at the touch, per-side order slots,
   reversion-side-only beyond the deadband, skew band inside it (defaults
   q=100, band=0 = measured best). VERDICT: neutral on round1 (+223,421 vs
   mean_maker's +229,336, < 1 se). Sweep (sweep_2s.py in /tmp/opencode):
   band=0 strictly dominates at every q, PnL ∝ q, per-lot 0.16–0.20; the
   band=50 hard-gate version regressed to +142k — i.e. inventory-adding is
   ~$80k of adverse selection. Reference only, not the candidate.

## Key measured facts
- Real tapes: spread cost ≈ 0.6–0.8/fill; any spread-crossing mean-chaser loses.
- Maker earns 0.17–0.53/lot; PnL ∝ size linearly (q swept 1→100, per-lot flat).
- Parameter-insensitive: k ∈ {50,100,200}, t ∈ {1,2} within ~0.3% → robust.
- Deadband is essential at size: t=0 with q=80 → side churn → 973,926 penalty.
- On real tapes the mid never deviates >2 ticks from its k=100 mean.
- round1 is busier (≈2.4× events/s) with worse adverse selection (per-lot
  0.48 → 0.17) but 4× more volume → net higher PnL.
- Mid price = (best bid + best ask)/2; deviation signals use half-ticks.

## Data / tooling
- `data/sample.csv` (synthetic, trends), `data/sample_v2.csv` (72 MB round,
  2M events, 96 min), `data/round1.csv` (161 MB, 4.4M events, 200 min).
- Backtest: `uv run exchange-simulator --strategy strategies/mean_maker.py
  --backtest data/round1.csv --log-dir logs/round1_maker --no-logs --progress`
  (drop --no-logs for explorer logs; ~330 MB on round1).
- Explorer: `uv run backtest-explorer --log-dir <dir> --port <p>` — currently
  running on port 8053 (logs/round1_maker); older ones stopped.
- Sweep scripts in /tmp/opencode/: sweep_k.py, sweep_maker.py, sweep_maker2.py,
  eval_taker_round1.py — run as `uv run python <script>`; they import the
  strategy module directly and drive ExchangeSimulator with the arena's config.

## Agreed roadmap (in order)
1. ~~Two-sided quoting~~ DONE — neutral on round1 (+223k vs +229k < 1 se at
   q=100/band=0). Double presence adds no edge; the useful output was the
   measurement that inventory-adding costs ~$80k (adverse selection).
   Next candidates, in discussion: fill-level forensics (bucket per-fill PnL
   by flow/queue/spread/inventory state) then trade-flow gating; microprice
   fair value; queue-position awareness (count orders ahead via `owner`
   field in book views); burst-aware sizing (event-rate EWMA).
2. Trade-flow imbalance from the `trades` callback — unused so far; real
   short-horizon alpha candidate; use to defend per-lot edge (adverse selection).
3. Hawkes-lite intensity (O(1)/event online, NOT scipy refits) for burst-aware
   sizing. Predicts WHEN, not direction.
4. Momentum-taker leg only when flow + trend strongly agree (rare); exits stay
   passive. Last, highest spread cost.
Discipline: keep guardrails (exposure bound, deadband), keep parameter
insensitivity, validate on new rounds instead of tuning per tape.

## User preferences
Metric units only; concise answers; `websearch` CLI exists at ~/.local/bin.
Backtests/sweeps: round1.csv only (user preference, 2026-11-07); sample tapes
no longer used for iteration.
