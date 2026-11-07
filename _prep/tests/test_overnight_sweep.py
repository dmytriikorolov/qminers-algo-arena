"""One-time evaluation guards; outputs stay in a temporary directory."""
from argparse import Namespace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "overnight_sweep.py"
SPEC = importlib.util.spec_from_file_location("overnight_sweep", SCRIPT)
overnight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(overnight)


class OvernightTests(unittest.TestCase):
    def args(self, **changes):
        return Namespace(**{"run_key": "20261107T010000Z", "seeds": 1,
                            "steps": 10, "start_at": None, **changes})

    def test_tiny_real_sweep_and_repeat_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = overnight.run(self.args(), root=temporary)
            result = json.loads((directory / "result.json").read_text())
            self.assertEqual(result["status"], "complete")
            self.assertEqual(len(result["metrics"]), 12)
            self.assertEqual(result["config"]["seeds"], [0])
            self.assertEqual(len(result["source_sha256"]), 64)
            self.assertTrue(all("equity" not in row for row in result["metrics"]))
            self.assertTrue(all(row["max_abs_position"] <= 10 for row in result["metrics"]))
            with self.assertRaises(FileExistsError):
                overnight.run(self.args(), root=temporary)

    def test_invalid_budget_and_key_write_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            for changes in ({"seeds": 21}, {"seeds": 0}, {"steps": 301},
                            {"steps": 0}, {"run_key": "../escape"},
                            {"start_at": "2026-11-07T02:00:00"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    overnight.run(self.args(**changes), root=temporary)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_source_change_fails_and_preserves_reservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(overnight, "frozen_source", side_effect=["before", "after"]):
                with self.assertRaisesRegex(RuntimeError, "source changed"):
                    overnight.run(self.args(), root=temporary)
            result = json.loads((Path(temporary) / "overnight_runs" /
                                 self.args().run_key / "result.json").read_text())
            self.assertEqual(result["status"], "failed")

    def test_deadline_interrupts_a_stalled_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(overnight, "MAX_SECONDS", 0.01), \
                    patch.object(overnight, "sweep", side_effect=lambda *args: overnight.time.sleep(1)):
                with self.assertRaisesRegex(TimeoutError, "deadline"):
                    overnight.run(self.args(), root=temporary)
            result = json.loads((Path(temporary) / "overnight_runs" /
                                 self.args().run_key / "result.json").read_text())
            self.assertEqual(result["status"], "failed")

    def test_concurrent_run_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "overnight_runs"
            base.mkdir()
            lock = overnight.os.open(base, overnight.os.O_RDONLY)
            try:
                overnight.fcntl.flock(lock, overnight.fcntl.LOCK_EX | overnight.fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    overnight.run(self.args(), root=temporary)
                self.assertEqual(list(base.iterdir()), [])
            finally:
                overnight.os.close(lock)

    def test_symlink_output_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "overnight_runs").symlink_to(root / "docs", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "inside the project"):
                overnight.run(self.args(), root=temporary)
            self.assertEqual(list((root / "docs").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
