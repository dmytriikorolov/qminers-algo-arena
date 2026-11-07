"""Fixed-budget paired risk comparison, with no parameter search or network."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from arena.common import ROOT, environment, git_state, save_json, source_fingerprint, utc_now
from arena.trading import mock_scenario, replay


def main():
    source = source_fingerprint()
    seeds = list(range(101, 121))
    rows = []
    for regime in ("mean_reverting", "trend", "trend_down", "volatile"):
        for seed in seeds:
            events = mock_scenario(seed, 300, regime)
            dataset_hash = hashlib.sha256(json.dumps(
                [[vars(book), side, price, volume] for book, side, price, volume in events],
                sort_keys=True).encode()).hexdigest()
            for method in ("fixed", "fixed_cap5", "inventory", "guarded_fixed"):
                result = replay(events, "fixed" if method == "fixed_cap5" else method,
                                position_limit=5 if method == "fixed_cap5" else 10)
                result["strategy"] = method
                last = events[-1][0]
                position = result["position"]
                liquidation = result["cash"] + position * (last.bid if position > 0 else last.ask) - abs(position) * 0.01
                rows.append({"regime": regime, "seed": seed, "dataset_sha256": dataset_hash,
                             **{key: value for key, value in result.items() if key != "equity"},
                             "estimated_liquidation_pnl": liquidation})
    summary = {}
    for regime in ("mean_reverting", "trend", "trend_down", "volatile"):
        summary[regime] = {}
        for method in ("fixed", "fixed_cap5", "inventory", "guarded_fixed"):
            cases = [row for row in rows if row["regime"] == regime and row["strategy"] == method]
            summary[regime][method] = {
                "mean_pnl": statistics.mean(row["pnl"] for row in cases),
                "worst_pnl": min(row["pnl"] for row in cases),
                "worst_drawdown": max(row["max_drawdown"] for row in cases),
                "worst_estimated_liquidation_pnl": min(row["estimated_liquidation_pnl"] for row in cases),
                "max_position": max(row["max_abs_position"] for row in cases),
            }
    accepted = all(item["guarded_fixed"]["worst_drawdown"] <= item["fixed"]["worst_drawdown"]
                   and item["guarded_fixed"]["max_position"] <= 5 for item in summary.values())
    assert source_fingerprint() == source, "source changed during comparison"
    record = {"timestamp": utc_now(), "git": git_state(), "source_sha256": source,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "environment": environment(), "seeds": seeds, "steps": 300, "rows": rows,
              "summary": summary, "accepted_for_risk_objective": accepted,
              "acceptance": "Worst marked drawdown no worse than fixed in every regime, soft position cap <=5. Not a profit dominance criterion.",
              "limitations": ["Synthetic front-of-queue fills and one-event latency only.",
                              "Fixed guard constants, no parameter optimization; seeds distinct from original development cases.",
                              "Guard reduces mean-reverting upside; existing inventory quotes may be safer in trends.",
                              "Estimated liquidation assumes full fill at final bid/ask plus fee, ignores depth and impact.",
                              "No strategy is proven profitable; no-op has zero simulated exposure and return."]}
    save_json(ROOT / "reports/trend_guard_validation.json", record)
    print(json.dumps({"accepted_for_risk_objective": accepted, "summary": summary}, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
