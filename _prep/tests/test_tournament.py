import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.experiments import load_run, run, tournament
from arena.trading import STRATEGIES


class TournamentTests(unittest.TestCase):
    def test_fixed_market_policies_and_paired_differences(self):
        with TemporaryDirectory() as tmp:
            config = {"family": "market", "parameters": {"steps": 20}}
            result = tournament(config, [7, 11], root=Path(tmp))
            self.assertEqual(result["reference_strategy"], "no_op")
            self.assertEqual(len(result["strategy_comparison"]), len(STRATEGIES))
            records = [load_run(run_id, root=tmp) for run_id in result["experiment_ids"]]
            fixed_pnls = []
            expected_differences = []
            for record in records:
                rows = {row["strategy"]: row for row in record["result"]["comparison"]}
                fixed_pnls.append(rows["fixed"]["pnl"])
                expected_differences.append(rows["fixed"]["pnl"] - rows["no_op"]["pnl"])
            observed = result["strategy_comparison"]["fixed"]["pnl"]
            self.assertEqual(observed["mean"], sum(fixed_pnls) / 2)
            self.assertEqual(observed["count"], 2)
            paired = result["paired_differences"]["fixed"]["pnl"]
            self.assertEqual(paired["seeds"], [7, 11])
            self.assertEqual(paired["values"], expected_differences)
            self.assertEqual(paired["min"], min(expected_differences))
            self.assertEqual(paired["max"], max(expected_differences))
            self.assertIn("candidate minus reference", result["difference_definition"])
            saved_path = Path(tmp) / "experiments" / result["experiment_ids"][-1] / "tournament.json"
            self.assertEqual(json.loads(saved_path.read_text()), result)

    def test_ml_loss_difference_retains_its_sign(self):
        with TemporaryDirectory() as tmp:
            config = {"family": "ml", "parameters": {"rows": 60}}
            result = tournament(config, [7, 11], root=tmp)
            self.assertEqual(result["reference_strategy"], "train_mean")
            record = load_run(result["experiment_ids"][0], root=tmp)
            rows = {row["strategy"]: row for row in record["result"]["comparison"]}
            for metric in rows["ridge"]:
                if metric == "strategy":
                    continue
                self.assertEqual(result["paired_differences"]["ridge"][metric]["values"][0],
                                 rows["ridge"][metric] - rows["train_mean"][metric])
            self.assertIn("lower is better for losses", result["difference_definition"])

    def test_family_without_named_methods_is_explicit(self):
        with TemporaryDirectory() as tmp:
            result = tournament({"family": "coding"}, [7], root=tmp)
            self.assertIsNone(result["reference_strategy"])
            self.assertEqual(result["strategy_comparison"], {})
            self.assertEqual(result["paired_differences"], {})
            self.assertEqual(result["metrics"]["shortest_distance"]["sample_stdev"], 0)

    def test_seeds_must_be_distinct_and_nonempty(self):
        with TemporaryDirectory() as tmp:
            for seeds in ([], [7, 7], list(range(101))):
                with self.subTest(seeds=seeds), self.assertRaises(ValueError):
                    tournament({"family": "coding"}, seeds, root=tmp)


class ProvenanceTests(unittest.TestCase):
    def test_actual_generated_data_fingerprint_survives_source_change(self):
        with TemporaryDirectory() as tmp:
            config = {"family": "market", "seed": 7, "parameters": {"steps": 10}}
            with patch("arena.experiments.source_fingerprint", return_value="a" * 64):
                first = run(config, root=tmp)
            with patch("arena.experiments.source_fingerprint", return_value="b" * 64):
                second = run(config, root=tmp)
            self.assertNotEqual(first["source_sha256"], second["source_sha256"])
            self.assertEqual(first["dataset"]["sha256"], second["dataset"]["sha256"])
            self.assertEqual(first["dataset"]["sha256"], first["result"]["dataset_fingerprint"])
            self.assertEqual(first["dataset"]["fingerprint_kind"], "generated_data_canonical_json")

    def test_execution_fees_do_not_change_market_dataset(self):
        with TemporaryDirectory() as tmp:
            first = run({"family": "market", "parameters": {"steps": 10, "fee_per_unit": 0.01}}, root=tmp)
            second = run({"family": "market", "parameters": {"steps": 10, "fee_per_unit": 1}}, root=tmp)
            self.assertNotEqual(first["config_sha256"], second["config_sha256"])
            self.assertEqual(first["dataset"]["sha256"], second["dataset"]["sha256"])

    def test_fallback_fingerprint_does_not_claim_data_bytes(self):
        with TemporaryDirectory() as tmp:
            with patch("arena.algorithms.demo", return_value={"family": "coding", "metrics": {}}):
                record = run({"family": "coding"}, root=tmp)
            self.assertEqual(record["dataset"]["fingerprint_kind"],
                             "generator_config_and_source_not_data_bytes")

    def test_file_dataset_uses_actual_bytes(self):
        from arena.common import fingerprint
        with TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "input.csv"
            dataset.write_text("time,x,target\n" + "\n".join(f"{i},{i},{i*2}" for i in range(30)))
            record = run({"family": "ml", "dataset": "input.csv", "parameters": {
                "time_column": "time", "target": "target", "features": ["x"]}}, root=tmp)
            self.assertEqual(record["dataset"]["fingerprint_kind"], "file_bytes")
            self.assertEqual(record["dataset"]["sha256"], fingerprint(dataset))


if __name__ == "__main__":
    unittest.main()
