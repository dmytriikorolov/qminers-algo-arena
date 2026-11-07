"""The offline command line. No model calls or network access in strategy code."""
import argparse
import csv
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .common import ROOT, environment, git_state, project_path, save_json, utc_now, verification_fingerprint
from .data import diagnose_file, inspect_file
from .experiments import FAMILIES, load_config, run, tournament


def test_suite(root=ROOT):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    results = []
    for directory in ("starter_tests", "tests"):
        command = [sys.executable, "-m", "unittest", "discover", "-s", directory, "-v"]
        process = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=120)
        output = process.stdout + process.stderr
        results.append({"command": command, "returncode": process.returncode, "output": output,
                        "has_tests": "Ran 0 tests" not in output and "Ran " in output})
    return {"passed": all(row["returncode"] == 0 and row["has_tests"] for row in results),
            "suites": results, "timestamp": utc_now()}


def doctor(include_tests=False):
    checks = {}
    for name in ("common", "data", "experiments", "trading", "market_data", "ml", "games", "algorithms"):
        try:
            importlib.import_module("arena." + name)
            checks[name] = "imported"
        except ImportError as exc:
            checks[name] = str(exc)
    result = {"environment": environment(), "project": str(ROOT), "core": checks,
              "ready": all(value == "imported" for value in checks.values()),
              "submission_ready": False, "tests": "not run; use doctor --tests or validate"}
    if include_tests:
        result["tests"] = test_suite()
        result["ready"] = result["ready"] and result["tests"]["passed"]
    return result


def validate():
    before = verification_fingerprint()
    results = test_suite()
    smoke = {}
    for family, name in FAMILIES.items():
        try:
            output = importlib.import_module("arena." + name).demo(seed=7)
            json.dumps(output, allow_nan=False)
            smoke[family] = {"passed": True, "metrics": output.get("metrics", {})}
        except (ValueError, TypeError, RuntimeError, ImportError) as exc:
            smoke[family] = {"passed": False, "error": str(exc)}
    after = verification_fingerprint()
    result = {"timestamp": utc_now(), "tests": results, "smoke": smoke,
              "verification_sha256": after, "code_unchanged_during_check": before == after,
              "passed": before == after and results["passed"] and all(row["passed"] for row in smoke.values()),
              "submission_ready": False, "official_contract": "UNVERIFIED",
              "note": "Local checks only; official-contract tests are blocked until Technical Rules/API are available."}
    save_json(project_path(ROOT / "memory" / "validation.json"), result)
    return result


def handoff():
    from .experiments import load_run
    paths = sorted((ROOT / "experiments").glob("*/result.json"), key=lambda path: path.stat().st_mtime)
    recent = []
    for path in paths[-8:]:
        record = load_run(path.parent.name)
        recent.append({"id": record["id"], "family": record["config"]["family"],
                       "metrics": record["result"].get("metrics", {})})
    validation_path = project_path(ROOT / "memory" / "validation.json")
    validation = json.loads(validation_path.read_text()) if validation_path.exists() else None
    validation_current = bool(validation and validation.get("verification_sha256") == verification_fingerprint())
    state = {"timestamp": utc_now(), "git": git_state(), "recent_runs": recent,
             "validation": validation, "validation_current": validation_current,
             "next": ["Read Technical Rules and run the official sample unchanged",
                      "Implement the exact adapter/signature and official scorer",
                      "Compare a minimal baseline and one improvement on legal held-out cases"],
             "restrictions": ["Preparation only; no verified submission contract", "Synthetic fills are not live profits",
                              "Third-party AI memory and hooks remain OFF", "No push or deployment authorized"]}
    save_json(project_path(ROOT / "memory" / "current_state.json"), state)
    lines = ["# Local handoff", "", f"Generated: {state['timestamp']}",
             f"Branch: {state['git']['branch']}; commit: {state['git']['revision']}; dirty: {state['git']['dirty']}", "",
             "## Verification", ""]
    if validation:
        lines.append(f"Local validation passed: {validation['passed']} at {validation['timestamp']}.")
        lines.append(f"Evidence matches current code and tests: {validation_current}.")
        lines.append("See memory/validation.json for exact commands and complete output. Rerun after changes.")
    else:
        lines.append("No saved validation evidence. Run `.venv/bin/arena validate`.")
    lines += ["", "## Recent saved results", ""]
    for record in recent:
        lines.append(f"- {record['family']} `{record['id']}`: {json.dumps(record['metrics'], sort_keys=True)}")
    lines += ["", "Results are scenario-specific; no universal best strategy is established.",
              "", "## Reproduce", "", "```bash", "# Run from the repository root",
              ".venv/bin/arena doctor --tests", ".venv/bin/arena baseline configs/market.json",
              ".venv/bin/arena baseline configs/ml.json", ".venv/bin/arena optimize configs/games.json",
              ".venv/bin/arena baseline configs/coding.json", ".venv/bin/arena validate", "```",
              "", "## Next three actions", ""]
    lines.extend(f"{index}. {item}" for index, item in enumerate(state["next"], 1))
    lines += ["", "## Restrictions", ""] + [f"- {item}" for item in state["restrictions"]]
    lines += ["", "## Failures and decisions", "", "See memory/failures.md and memory/decisions.md."]
    project_path(ROOT / "memory" / "handoff.md").write_text("\n".join(lines) + "\n")
    project_path(ROOT / "memory" / "current_state.md").write_text("\n".join(lines[:13]) + "\n")
    return {"path": str(ROOT / "memory" / "handoff.md"), "runs": len(recent),
            "validation_current": validation_current,
            "validation_passed": validation["passed"] and validation_current if validation else None}


def parser():
    p = argparse.ArgumentParser(prog="arena", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    doc = sub.add_parser("doctor", help="offline environment and core import checks")
    doc.add_argument("--tests", action="store_true")
    for name in ("inspect", "diagnose"):
        command = sub.add_parser(name, help="bounded CSV/TSV/JSON data inspection")
        command.add_argument("path")
        command.add_argument("--max-rows", type=int, default=10000)
    command = sub.add_parser("market-features", help="causal features from explicit snapshot/bar/trade CSV schemas")
    command.add_argument("path")
    command.add_argument("--kind", choices=["snapshots", "bars", "trades"], default="snapshots")
    command.add_argument("--window", type=int, default=20)
    command.add_argument("--tick", type=float, default=0.1)
    for name in ("baseline", "experiment", "optimize", "tournament"):
        command = sub.add_parser(name, help="run config and save observed metrics and provenance")
        command.add_argument("config")
        if name == "tournament":
            command.add_argument("--seeds", default="7,11,19", help="comma-separated distinct paired seeds")
    command = sub.add_parser("report", help="HTML/Markdown and optional PDF from a saved run")
    command.add_argument("experiment_id")
    command.add_argument("--pdf", action="store_true")
    sub.add_parser("quick-cards", help="generate six offline PDF cards (reports extra required)")
    sub.add_parser("handoff", help="write readable local memory; no external service")
    sub.add_parser("validate", help="run tests and four smoke demos; record evidence")
    command = sub.add_parser("validate-submission", help="static one-file preflight; not official certification")
    command.add_argument("path")
    command.add_argument("--contract", required=True)
    command = sub.add_parser("package", help="copy a self-contained file plus provenance; never executes or submits")
    command.add_argument("path")
    command.add_argument("--contract", required=True)
    command.add_argument("--output", required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor(args.tests)
        elif args.command in ("inspect", "diagnose"):
            function = inspect_file if args.command == "inspect" else diagnose_file
            result = function(project_path(args.path), max_rows=args.max_rows)
        elif args.command == "market-features":
            from .market_data import analyze_csv
            result = analyze_csv(project_path(args.path), kind=args.kind, window=args.window, tick=args.tick)
        elif args.command in ("baseline", "experiment", "optimize", "tournament"):
            config = load_config(args.config)
            if args.command == "optimize" and config["family"] != "games":
                raise ValueError("optimize currently requires family=games")
            if args.command == "tournament":
                result = tournament(config, [int(value) for value in args.seeds.split(",")])
            else:
                result = run(config)
        elif args.command == "report":
            from .reporting import report
            result = report(args.experiment_id, pdf=args.pdf)
        elif args.command == "quick-cards":
            from .reporting import quick_cards
            (ROOT / "docs").mkdir(exist_ok=True)
            output = project_path(ROOT / "docs" / "QUICK_CARDS.pdf")
            quick_cards(output)
            result = {"pdf": str(output)}
        elif args.command == "validate":
            result = validate()
        elif args.command == "validate-submission":
            from .preflight import check_submission
            result = check_submission(project_path(args.path), project_path(args.contract))
        elif args.command == "package":
            from .packaging import prepare
            result = prepare(args.path, args.contract, args.output)
        else:
            result = handoff()
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        if (result.get("passed") is False or result.get("ready") is False
                or result.get("status") == "failed"):
            return 1
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, OverflowError, csv.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc), "command": args.command}), file=sys.stderr)
        return 2
