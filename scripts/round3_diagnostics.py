"""Fixed ablations of the retained adaptive strategy; never edits its source.

Usage: .venv/bin/python scripts/round3_diagnostics.py --variant no_inventory_bias
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulator.simulator import ExchangeSimulator, SimulationConfig
from strategies.adaptive_ml_regime import AdaptiveMakerMLStrategy

VARIANTS = {
    "adaptive_trace": {},
    "no_inventory_bias": {"regime": False},
    "no_fade": {"fade_size": 0},
    "no_crash_bias": {"crash_drop": 1e9, "recovery_rise": None},
    "no_risk_or_inventory_bias": {"regime": False, "force_full_size": True},
}


class ObservedAdaptive(AdaptiveMakerMLStrategy):
    def __init__(self, force_full_size=False, **kwargs):
        super().__init__(**kwargs)
        self.force_full_size = force_full_size
        self.observations = []
        self.last_observed = -1

    def _update_volatility(self, *args):
        super()._update_volatility(*args)
        if self.force_full_size:
            self._eff_limit = self._limit

    def on_order_book_change(self, snapshot, trades):
        super().on_order_book_change(snapshot, trades)
        second = snapshot.timestamp_us // 1_000_000
        if second != self.last_observed:
            self.observations.append((snapshot.timestamp_us / 1e6, self._inventory, self._eff_limit,
                                      self._center, self._state, self._forecast() if self._hist else None))
            self.last_observed = second


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, default="adaptive_trace")
    parser.add_argument("--output", type=Path, default=ROOT / "logs/round3_analysis/ablations")
    args = parser.parse_args()
    output = args.output / args.variant
    output.mkdir(parents=True, exist_ok=True)
    strategy = ObservedAdaptive(**VARIANTS[args.variant])
    config = SimulationConfig(order_accept_delay_ms=5, max_position=100, max_potential_position=1000,
                              position_breach_penalty_per_second=10_000)
    engine = ExchangeSimulator(strategy, config)
    result = engine.run(ROOT / "data/round3_public.csv")
    (output / "result.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2))
    (output / "parameters.json").write_text(json.dumps(VARIANTS[args.variant], indent=2))
    with (output / "pnl.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["elapsed_s", "pnl"])
        writer.writerows((t / 1e6, p) for t, p in engine.pnl_curve(result.pnl))
    with (output / "controls.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time", "inventory", "effective_limit", "center", "state", "risk_forecast"])
        writer.writerows(strategy.observations)
    print(args.variant, result.model_dump(), flush=True)


if __name__ == "__main__":
    main()
