import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from arena.cli import main
from arena.common import project_path
from arena.data import inspect_file, diagnose_file
from arena.experiments import load_run, run, validate_config
from arena.reporting import report, quick_cards


class TestData(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_quality_sample_and_truncation(self):
        path = self.root / "data.csv"
        path.write_text("time,value\n1,2\n2,\n3,nan\n3,nan\n4,999\n")
        result = inspect_file(path, max_rows=4)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["columns"]["value"]["missing"], 1)
        self.assertEqual(result["columns"]["value"]["nonfinite"], 2)
        self.assertEqual(result["duplicate_rows_in_sample"], 1)
        self.assertEqual(result["columns"]["value"]["max"], 2)
        self.assertTrue(diagnose_file(path)["findings"])

    def test_duplicate_headers_rejected(self):
        path = self.root / "data.csv"
        path.write_text("x,x\n1,2\n")
        with self.assertRaises(ValueError):
            inspect_file(path)

    def test_malformed_rows_reported(self):
        path = self.root / "data.csv"
        path.write_text("x,y\n1\n2,3,4\n")
        self.assertEqual(inspect_file(path)["malformed_rows"], 2)

    def test_json_nonfinite_rejected(self):
        path = self.root / "data.json"
        path.write_text('{"x": NaN}')
        with self.assertRaises(ValueError):
            inspect_file(path)

    def test_input_size_limit(self):
        path = self.root / "data.csv"
        path.write_text("x\n1\n")
        with self.assertRaises(ValueError):
            inspect_file(path, max_bytes=2)

    def test_overflowing_json_number_rejected(self):
        path = self.root / "data.json"
        path.write_text('{"x": 1e999}')
        with self.assertRaises(ValueError):
            inspect_file(path)

    def test_large_csv_field_gives_validation_error(self):
        path = self.root / "data.csv"
        path.write_text("value\n" + "a" * 140000 + "\n")
        with self.assertRaises(ValueError):
            inspect_file(path)

    def test_path_traversal_and_symlink_rejected(self):
        with self.assertRaises(ValueError):
            project_path("../outside", self.root)
        (self.root / "escape").symlink_to(self.root.parent)
        with self.assertRaises(ValueError):
            project_path("escape/outside", self.root)


class TestExperiments(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_ml_save_load_replay_and_metadata(self):
        config = {"family": "ml", "seed": 17, "parameters": {"rows": 60}}
        first, second = run(config, self.root), run(config, self.root)
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(first["dataset"], second["dataset"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["config_sha256"], second["config_sha256"])
        self.assertEqual(load_run(first["id"], self.root), first)
        self.assertIn("python", first["environment"])
        self.assertFalse(first["submission_ready"])
        self.assertEqual(len((self.root / "memory/experiments.jsonl").read_text().splitlines()), 2)

    def test_file_backed_ml_explicit_columns_and_hash(self):
        path = self.root / "data.csv"
        path.write_text("time,x,target\n" + "".join(f"{i},{i%7},{2*(i%7)+1}\n" for i in range(40)))
        config = {"family": "ml", "dataset": "data.csv", "seed": 4,
                  "parameters": {"target": "target", "features": ["x"], "time_column": "time"}}
        record = run(config, self.root)
        self.assertEqual(record["dataset"]["kind"], "file")
        self.assertFalse(record["result"]["synthetic"])
        self.assertLess(record["result"]["metrics"]["ridge"]["mse"], 0.01)
        with self.assertRaises(ValueError):
            load_run("../../other", self.root)

    def test_coding_in_memory_result_matches_json_artifact(self):
        record = run({"family": "coding", "seed": 23}, self.root)
        self.assertEqual(load_run(record["id"], self.root), record)

    def test_source_mutation_during_run_creates_no_artifact(self):
        with patch("arena.experiments.source_fingerprint", side_effect=["before", "after"]):
            with self.assertRaisesRegex(ValueError, "source changed"):
                run({"family": "ml", "parameters": {"rows": 30}}, self.root)
        self.assertFalse((self.root / "experiments").exists())

    def test_dataset_mutation_during_run_creates_no_artifact(self):
        from arena import ml
        path = self.root / "data.csv"
        data = "time,x,target\n" + "".join(f"{i},{i%7},{2*(i%7)+1}\n" for i in range(40))
        path.write_text(data)
        original = ml.run_csv
        def changing_loader(*args, **kwargs):
            path.write_text(data + "40,5,11\n")
            return original(*args, **kwargs)
        config = {"family": "ml", "dataset": "data.csv",
                  "parameters": {"target": "target", "features": ["x"], "time_column": "time"}}
        with patch("arena.ml.run_csv", side_effect=changing_loader):
            with self.assertRaisesRegex(ValueError, "dataset changed"):
                run(config, self.root)
        self.assertFalse((self.root / "experiments").exists())

    def test_config_rejects_unknowns_and_invalid_values(self):
        for config in ({"family": "typo"}, {"family": "ml", "seed": True},
                       {"family": "market", "dataset": "x.csv"},
                       {"family": "ml", "oops": 1},
                       {"family": "ml", "parameters": {"x": float("nan")}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_config(config)

    def test_report_uses_saved_metrics_and_escapes_html(self):
        record = run({"family": "ml", "seed": 7, "parameters": {"rows": 60}}, self.root)
        record["result"]["warnings"] = ["<script>alert(1)</script>"]
        path = self.root / "experiments" / record["id"] / "result.json"
        path.write_text(json.dumps(record))
        outputs = report(record["id"], self.root)
        html = Path(outputs["html"]).read_text()
        self.assertIn(record["id"], html)
        self.assertIn("SYNTHETIC", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        metric = record["result"]["metrics"]["ridge"]["mse"]
        self.assertIn(f"{metric:.8g}", html)

    def test_pdf_contains_real_run_and_cards_have_six_pages(self):
        try:
            from pypdf import PdfReader
            import reportlab
        except ImportError:
            self.skipTest("optional reports extra not installed")
        record = run({"family": "ml", "seed": 7, "parameters": {"rows": 60}}, self.root)
        outputs = report(record["id"], self.root, pdf=True)
        document = PdfReader(outputs["pdf"])
        text = "\n".join(page.extract_text() for page in document.pages)
        self.assertIn(record["id"], text)
        self.assertIn("SYNTHETIC", text)
        self.assertIn(f"{record['result']['metrics']['ridge']['mse']:.8g}", text)
        output = self.root / "cards.pdf"
        quick_cards(output)
        self.assertEqual(len(PdfReader(output).pages), 6)

    def test_report_rejects_output_symlink(self):
        record = run({"family": "ml", "parameters": {"rows": 30}}, self.root)
        directory = self.root / "reports" / record["id"]
        directory.mkdir(parents=True)
        outside = self.root.parent / (self.root.name + "-outside.html")
        (directory / "report.html").symlink_to(outside)
        with self.assertRaises(ValueError):
            report(record["id"], self.root)
        self.assertFalse(outside.exists())


class TestCLI(unittest.TestCase):
    def test_doctor_offline(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["doctor"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result["ready"])
        self.assertFalse(result["submission_ready"])

    def test_bad_config_gives_machine_readable_error(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = main(["baseline", "configs/no-such-file.json"])
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(error.getvalue()))

    def test_external_file_rejected(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = main(["inspect", "/etc/passwd"])
        self.assertEqual(code, 2)
        self.assertIn("inside the project", json.loads(error.getvalue())["error"])
