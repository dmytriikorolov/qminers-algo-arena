"""Copy one self-contained source after static preflight, without executing it."""

import hashlib
import json
from pathlib import Path

from .common import ROOT, environment, project_path, utc_now
from .preflight import check_submission


def _read_snapshot(path, max_bytes):
    with path.open("rb") as stream:
        content = stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"packaging input exceeds {max_bytes} bytes: {path.name}")
    return content


def prepare(path, contract_path, output, root=ROOT):
    """Prepare a new .py plus adjacent .manifest.json; never overwrite artifacts.

    The input must already be a self-contained file. Static checks do not prove
    runtime correctness or contest eligibility, even with a verified contract.
    A false official_verified flag permits a local rehearsal, never readiness.
    """
    root = Path(root).resolve()
    source = project_path(path, root)
    contract = project_path(contract_path, root)
    requested_output = Path(output)
    if not requested_output.is_absolute():
        requested_output = root / requested_output
    destination = project_path(requested_output, root)
    if destination.suffix != ".py":
        raise ValueError("packaged output must have a .py extension")
    requested_manifest = requested_output.with_suffix(".manifest.json")
    manifest_path = project_path(requested_manifest, root)
    # Check lexical paths too: resolve() follows a dangling in-project symlink
    # to a nonexistent target, but that symlink is still an existing artifact.
    if requested_output.exists() or requested_output.is_symlink():
        raise FileExistsError(f"refusing to overwrite packaged output: {requested_output}")
    if requested_manifest.exists() or requested_manifest.is_symlink():
        raise FileExistsError(f"refusing to overwrite package manifest: {requested_manifest}")
    if not source.is_file() or source.suffix != ".py" or not contract.is_file():
        raise ValueError("packaging requires a regular Python source and a contract file")
    source_bytes = _read_snapshot(source, 10 * 1024 * 1024)
    contract_bytes = _read_snapshot(contract, 1024 * 1024)
    static_check = check_submission(source, contract)
    if static_check["status"] != "static_checks_passed":
        raise ValueError("submission static preflight failed: " + "; ".join(static_check["errors"]))
    if (_read_snapshot(source, 10 * 1024 * 1024) != source_bytes
            or _read_snapshot(contract, 1024 * 1024) != contract_bytes):
        raise ValueError("source or contract changed during static preflight; retry with stable inputs")
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    manifest = {
        "schema_version": 1,
        "timestamp": utc_now(),
        "source": {"path": str(source.relative_to(root)), "sha256": source_hash},
        "contract": {"path": str(contract.relative_to(root)),
                     "sha256": hashlib.sha256(contract_bytes).hexdigest()},
        "output": {"path": str(destination.relative_to(root)), "sha256": source_hash},
        "static_check": static_check,
        "environment": environment(),
        "official_verified": static_check["official_verified"],
        "submission_ready": False,
        "note": "Local copy only. No code executed or submitted. Run the official evaluator and enforce its runtime restrictions separately.",
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(source_bytes)
    try:
        with manifest_path.open("x", encoding="utf-8") as stream:
            stream.write(manifest_text)
    except OSError as exc:
        # Preserve the source copy and any competing artifact; never silently
        # overwrite or delete a file when publication of the manifest fails.
        raise OSError(f"source copied to {destination}, but manifest creation failed; "
                      "no existing file was overwritten; use a new output path") from exc
    return {
        "status": "prepared",
        "output": str(destination),
        "manifest": str(manifest_path),
        "sha256": source_hash,
        "official_verified": static_check["official_verified"],
        "submission_ready": False,
    }
