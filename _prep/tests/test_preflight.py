import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.preflight import check_submission


class PreflightTests(unittest.TestCase):
    def check(self, source, **contract_changes):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / "solution.py"
            path.write_text(source)
            contract_path = directory / "contract.json"
            contract = {"entrypoint": "solve", "parameters": ["x"],
                        "allowed_imports": ["math"], "max_bytes": 10000,
                        "official_verified": False, **contract_changes}
            contract_path.write_text(json.dumps(contract))
            return check_submission(path, contract_path)

    def test_context_invalid_python_is_rejected(self):
        for statement in ("break", "continue", "return 1", "await something()", "yield 1"):
            with self.subTest(statement=statement):
                result = self.check("def solve(x): return x\n" + statement + "\n")
                self.assertEqual(result["status"], "failed")
                self.assertIn("syntax error", result["errors"][0])

    def test_compile_checks_duplicate_arguments(self):
        result = self.check("def solve(x, x): return x\n")
        self.assertEqual(result["status"], "failed")
        self.assertIn("duplicate argument", result["errors"][0])

    def test_compile_does_not_execute_program(self):
        result = self.check("def solve(x): return 1 / x\nraise RuntimeError('must not execute')\n")
        self.assertEqual(result["status"], "static_checks_passed")
        self.assertFalse(result["submission_ready"])

    def test_signature_and_import_restrictions(self):
        for source in ("def solve(y): return y\n", "import os\ndef solve(x): return x\n",
                       "def solve(x=1): return x\n", "async def solve(x): return x\n"):
            with self.subTest(source=source):
                self.assertEqual(self.check(source)["status"], "failed")
        self.assertEqual(self.check("import math\ndef solve(x): return math.sqrt(x)\n")["status"],
                         "static_checks_passed")


if __name__ == "__main__":
    unittest.main()
