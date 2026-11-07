"""Small provenance and filesystem helpers shared by offline tools."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def project_path(path, root=ROOT):
    """Output and input paths stay in the personal lab, including symlinks."""
    root = Path(root).resolve()
    candidate = Path(path)
    candidate = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path must stay inside the project directory")
    return candidate


def git_state(root=ROOT):
    def query(*args):
        try:
            return subprocess.check_output(
                ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL,
                text=True, timeout=5,
            ).strip()
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
    return {"revision": query("rev-parse", "HEAD"), "branch": query("branch", "--show-current"),
            "dirty": query("status", "--porcelain") != ""}


def source_fingerprint():
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src" / "arena").glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def verification_fingerprint():
    digest = hashlib.sha256(source_fingerprint().encode())
    for directory in ("tests", "starter_tests", "starter_arena"):
        for path in sorted((ROOT / directory).rglob("*.py")):
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    digest.update((ROOT / "pyproject.toml").read_bytes())
    return digest.hexdigest()


def environment():
    packages = {}
    for name in ("quant-arena-lab", "reportlab", "pypdf", "numpy", "scipy"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "dependencies": packages}


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
