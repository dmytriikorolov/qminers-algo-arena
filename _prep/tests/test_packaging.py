import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.packaging import prepare
from arena.preflight import check_submission


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "strategy.py"
        self.source.write_bytes(b"import math\r\n\r\ndef solve(data):\r\n    return math.fsum(data)\r\n")
        self.contract = self.root / "contract.json"
        self.contract_data = {"entrypoint": "solve", "parameters": ["data"],
                              "allowed_imports": ["math"], "max_bytes": 100000,
                              "official_verified": False}
        self.contract.write_text(json.dumps(self.contract_data))
        self.destination = self.root / "submissions" / "candidate.py"

    def package(self):
        return prepare("strategy.py", "contract.json", "submissions/candidate.py", root=self.root)

    def test_exact_copy_and_manifest_provenance(self):
        output = self.package()
        self.assertEqual(output["status"], "prepared")
        self.assertFalse(output["submission_ready"])
        self.assertFalse(output["official_verified"])
        self.assertEqual(self.source.read_bytes(), self.destination.read_bytes())
        manifest = json.loads(Path(output["manifest"]).read_text())
        self.assertEqual(manifest["output"]["path"], "submissions/candidate.py")
        self.assertEqual(manifest["source"]["sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(manifest["contract"]["sha256"], hashlib.sha256(self.contract.read_bytes()).hexdigest())
        self.assertEqual(manifest["output"]["sha256"], manifest["source"]["sha256"])
        self.assertEqual(manifest["static_check"]["status"], "static_checks_passed")
        self.assertIn("python", manifest["environment"])
        self.assertFalse(manifest["submission_ready"])

    def test_verified_contract_still_requires_runtime_validation(self):
        self.contract_data["official_verified"] = True
        self.contract.write_text(json.dumps(self.contract_data))
        result = self.package()
        self.assertTrue(result["official_verified"])
        self.assertFalse(result["submission_ready"])

    def test_failed_static_check_writes_nothing(self):
        self.source.write_text("import socket\ndef solve(data):\n    return data\n")
        with self.assertRaisesRegex(ValueError, "preflight failed"):
            self.package()
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.destination.with_suffix(".manifest.json").exists())

    def test_source_is_not_executed(self):
        self.source.write_text("raise RuntimeError('must never execute')\ndef solve(data):\n    return data\n")
        self.assertEqual(self.package()["status"], "prepared")

    def test_existing_output_is_preserved(self):
        self.destination.parent.mkdir()
        self.destination.write_text("known-good")
        with self.assertRaises(FileExistsError):
            self.package()
        self.assertEqual(self.destination.read_text(), "known-good")
        self.assertFalse(self.destination.with_suffix(".manifest.json").exists())

    def test_existing_manifest_is_preserved_without_source_copy(self):
        self.destination.parent.mkdir()
        manifest = self.destination.with_suffix(".manifest.json")
        manifest.write_text("previous evidence")
        with self.assertRaises(FileExistsError):
            self.package()
        self.assertFalse(self.destination.exists())
        self.assertEqual(manifest.read_text(), "previous evidence")

    def test_existing_dangling_output_symlink_is_preserved(self):
        self.destination.parent.mkdir()
        target = self.root / "must-not-create.py"
        self.destination.symlink_to(target)
        with self.assertRaises(FileExistsError):
            self.package()
        self.assertTrue(self.destination.is_symlink())
        self.assertFalse(target.exists())

    def test_existing_dangling_manifest_symlink_is_preserved(self):
        self.destination.parent.mkdir()
        target = self.root / "must-not-create.json"
        manifest = self.destination.with_suffix(".manifest.json")
        manifest.symlink_to(target)
        with self.assertRaises(FileExistsError):
            self.package()
        self.assertTrue(manifest.is_symlink())
        self.assertFalse(target.exists())
        self.assertFalse(self.destination.exists())

    def test_external_paths_and_symlink_escapes_rejected(self):
        (self.root / "escape").symlink_to(self.root.parent)
        for source, contract, output in (
                ("../outside.py", "contract.json", "candidate.py"),
                ("strategy.py", "../contract.json", "candidate.py"),
                ("strategy.py", "contract.json", "../outside.py"),
                ("strategy.py", "contract.json", "escape/outside.py")):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "inside the project"):
                prepare(source, contract, output, root=self.root)

    def test_output_requires_python_extension(self):
        with self.assertRaisesRegex(ValueError, "extension"):
            prepare(self.source, self.contract, self.root / "candidate.zip", root=self.root)

    def test_source_change_during_preflight_rejected(self):
        def mutate(source, contract):
            result = check_submission(source, contract)
            source.write_text("changed after checking")
            return result
        with patch("arena.packaging.check_submission", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed during"):
                self.package()
        self.assertFalse(self.destination.exists())

    def test_contract_change_during_preflight_rejected(self):
        def mutate(source, contract):
            result = check_submission(source, contract)
            contract.write_text("{}")
            return result
        with patch("arena.packaging.check_submission", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed during"):
                self.package()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
