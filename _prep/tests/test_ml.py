import copy
import csv
import math
import tempfile
import unittest
from pathlib import Path

from arena.ml import chronological_split, demo, run_csv, run_rows, score


class TestSplits(unittest.TestCase):
    def test_chronology_and_embargo(self):
        train, validation, test = chronological_split(100, gap=3)
        self.assertEqual((len(train), len(validation), len(test)), (57, 17, 20))
        self.assertLess(train[-1] + 3, validation[0])
        self.assertLess(validation[-1] + 3, test[0])

    def test_invalid_sizes_and_gaps(self):
        for size, gap in ((5, 0), (10, 8), (100, -1), (100, True)):
            with self.subTest(size=size, gap=gap), self.assertRaises(ValueError):
                chronological_split(size, gap=gap)
        with self.assertRaises(ValueError):
            chronological_split(100, train_fraction=0.8, validation_fraction=0.3)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.rows = [{"time": index, "x": index % 7, "y": 3 * (index % 7) + 2,
                      "group": index // 10} for index in range(100)]

    def run_data(self, rows=None, **kwargs):
        return run_rows(self.rows if rows is None else rows, target="y", features=["x"],
                        time_column="time", **kwargs)

    def test_known_linear_relation(self):
        result = self.run_data(penalties=(1e-6,))
        self.assertLess(result["metrics"]["ridge"]["mse"], 1e-8)
        self.assertAlmostEqual(result["model"]["weights"][0], result["model"]["constant"])

    def test_test_target_never_changes_fit_or_selection(self):
        before = self.run_data()
        rows = copy.deepcopy(self.rows)
        for row in rows[80:]:
            row["y"] += 10000
        after = self.run_data(rows)
        self.assertEqual(before["model"], after["model"])
        self.assertEqual(before["selection"], after["selection"])
        self.assertNotEqual(before["metrics"], after["metrics"])

    def test_test_features_never_change_preprocessing(self):
        before = self.run_data()
        rows = copy.deepcopy(self.rows)
        for row in rows[80:]:
            row["x"] += 100000
        after = self.run_data(rows)
        self.assertEqual(before["model"], after["model"])

    def test_imputation_uses_only_train_observations(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["x"] = None
        for row in rows[60:]:
            row["x"] = 10000
        result = self.run_data(rows)
        expected = sum(row["x"] for row in rows[1:60]) / 59
        self.assertAlmostEqual(result["model"]["imputation_means"][0], expected)
        self.assertEqual(result["data_quality"]["missing_features"], 1)

    def test_reject_target_as_feature(self):
        with self.assertRaises(ValueError):
            run_rows(self.rows, target="y", features=["y"], time_column="time")

    def test_reject_direct_target_copy(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row["x"] = row["y"]
        with self.assertRaisesRegex(ValueError, "duplicates"):
            self.run_data(rows)

    def test_reject_time_as_feature(self):
        with self.assertRaises(ValueError):
            run_rows(self.rows, target="y", features=["time"], time_column="time")

    def test_reject_unsorted_or_duplicate_times(self):
        for time in (0, -1):
            rows = copy.deepcopy(self.rows)
            rows[1]["time"] = time
            with self.subTest(time=time), self.assertRaisesRegex(ValueError, "increasing"):
                self.run_data(rows)

    def test_numeric_csv_times_not_lexical(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row["time"] = str(row["time"])
        self.assertEqual(self.run_data(rows)["split"]["test_start"], 80)

    def test_iso_timestamps(self):
        from datetime import datetime, timedelta, timezone
        rows = copy.deepcopy(self.rows)
        for index, row in enumerate(rows):
            row["time"] = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)).isoformat()
        self.assertEqual(self.run_data(rows)["split"]["test_start"], 80)

    def test_label_horizon_requires_gap(self):
        with self.assertRaisesRegex(ValueError, "horizon"):
            self.run_data(label_horizon=2, gap=1)
        self.assertEqual(self.run_data(label_horizon=2, gap=2)["split"]["train_rows"], 58)

    def test_group_separation(self):
        self.run_data(group_column="group")
        rows = copy.deepcopy(self.rows)
        rows[81]["group"] = rows[0]["group"]
        with self.assertRaisesRegex(ValueError, "groups overlap"):
            self.run_data(rows, group_column="group")

    def test_missing_required_column(self):
        rows = copy.deepcopy(self.rows)
        del rows[2]["x"]
        with self.assertRaisesRegex(ValueError, "column"):
            self.run_data(rows)

    def test_nonfinite_target_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["y"] = math.inf
        with self.assertRaises(ValueError):
            self.run_data(rows)

    def test_all_missing_feature_falls_back_to_training_mean(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row["x"] = None
        result = self.run_data(rows)
        self.assertEqual(result["model"]["imputation_means"], [0.0])
        self.assertAlmostEqual(result["metrics"]["ridge"]["mse"], result["metrics"]["baseline"]["mse"])

    def test_single_class_training_supported(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row["y"] = 1
            row["x"] = 1
        result = self.run_data(rows, task="classification")
        self.assertTrue(math.isfinite(result["metrics"]["logistic"]["log_loss"]))

    def test_regression_demo_is_reproducible_and_improves(self):
        result = demo(seed=11)
        self.assertEqual(result, demo(seed=11))
        self.assertTrue(result["synthetic"])
        self.assertGreater(result["metrics"]["improvement"], 0)

    def test_actual_dataset_hash_ignores_model_and_split_settings(self):
        first = demo(seed=11)
        altered = demo(seed=11, gap=1, penalties=(0.5, 5.0))
        self.assertEqual(first["dataset_fingerprint"], altered["dataset_fingerprint"])
        self.assertEqual(len(first["dataset_fingerprint"]), 64)
        self.assertNotEqual(first["dataset_fingerprint"], demo(seed=12)["dataset_fingerprint"])
        self.assertNotEqual(first["dataset_fingerprint"], demo(seed=11, rows=241)["dataset_fingerprint"])
        self.assertNotEqual(first["dataset_fingerprint"], demo(seed=11, task="classification")["dataset_fingerprint"])

    def test_large_finite_features_request_rescaling(self):
        rows = [{"time": i, "x": 1e200 * (1 if i % 2 else -1), "y": i % 7} for i in range(30)]
        with self.assertRaisesRegex(ValueError, "rescale"):
            self.run_data(rows)

    def test_classification_calibration_accounts_for_all_test_rows(self):
        result = demo(task="classification")
        self.assertGreater(result["metrics"]["improvement"], 0)
        self.assertEqual(sum(item["count"] for item in result["calibration"]), result["split"]["test_rows"])

    def test_non_binary_targets_rejected(self):
        with self.assertRaises(ValueError):
            self.run_data(task="classification")

    def test_unknown_demo_parameters_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            demo(gapp=2)

    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["time", "x", "y", "group"])
                writer.writeheader()
                writer.writerows(self.rows)
            result = run_csv(path, target="y", features=["x"], time_column="time")
        self.assertIsNone(result["synthetic"])
        self.assertEqual(result["data_origin"], "unverified_caller_input")
        self.assertEqual(result["split"]["test_rows"], 20)


class TestMetrics(unittest.TestCase):
    def test_analytic_regression(self):
        self.assertEqual(score([1, 3], [2, 1]), {"mse": 2.5, "rmse": math.sqrt(2.5), "mae": 1.5})

    def test_analytic_probabilities(self):
        metrics = score([0, 1], [0.25, 0.75], "classification")
        self.assertAlmostEqual(metrics["brier"], 0.0625)
        self.assertAlmostEqual(metrics["log_loss"], -math.log(0.75))

    def test_invalid_metrics(self):
        for y, prediction in (([], []), ([1], []), ([math.nan], [0]), ([1], [math.inf])):
            with self.subTest(y=y), self.assertRaises(ValueError):
                score(y, prediction)
        with self.assertRaises(ValueError):
            score([1], [2], "classification")


if __name__ == "__main__":
    unittest.main()
