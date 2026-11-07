"""Config-driven offline runs with reproducible provenance and paired seeds."""
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import statistics
import time
import uuid

from .common import (ROOT, canonical, environment, fingerprint, git_state,
                     project_path, save_json, source_fingerprint, utc_now)

FAMILIES = {"market": "trading", "ml": "ml", "games": "games", "coding": "algorithms"}


def load_config(path):
    path = project_path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("config exceeds 1 MB")
    config = json.loads(path.read_text())
    validate_config(config)
    return config


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    if set(config) - {"family", "seed", "parameters", "dataset"}:
        raise ValueError("unknown config keys")
    if config.get("family") not in FAMILIES:
        raise ValueError(f"family must be one of {list(FAMILIES)}")
    if type(config.get("seed", 7)) is not int:
        raise ValueError("seed must be an integer")
    if not isinstance(config.get("parameters", {}), dict):
        raise ValueError("parameters must be an object")
    if "seed" in config.get("parameters", {}):
        raise ValueError("set seed at top level only")
    if "dataset" in config and config["family"] != "ml":
        raise ValueError("file-backed evaluation currently supports ML only; other demos are synthetic")
    canonical(config)  # Reject NaN and Infinity in parameters.


def run(config, root=ROOT):
    validate_config(config)
    config = json.loads(canonical(config))
    family = config["family"]
    seed = config.get("seed", 7)
    params = dict(config.get("parameters", {}))
    module = importlib.import_module(f"arena.{FAMILIES[family]}")
    config_hash = hashlib.sha256(canonical(config).encode()).hexdigest()
    code_hash = source_fingerprint()
    if "dataset" in config:
        dataset_path = project_path(config["dataset"], root)
        dataset = {"kind": "file", "path": str(dataset_path.relative_to(Path(root).resolve())),
                   "sha256": fingerprint(dataset_path), "fingerprint_kind": "file_bytes"}
    else:
        dataset = {"kind": "synthetic", "generator": FAMILIES[family],
                   "sha256": hashlib.sha256((config_hash + code_hash).encode()).hexdigest(),
                   "fingerprint_kind": "generator_config_and_source_not_data_bytes"}
    started = time.perf_counter()
    if "dataset" in config:
        result = module.run_csv(dataset_path, seed=seed, **params)
    else:
        result = module.demo(seed=seed, **params)
    elapsed = time.perf_counter() - started
    # Round-trip once so Python callers and saved JSON see the same key/types.
    result = json.loads(canonical(result))
    if source_fingerprint() != code_hash:
        raise ValueError("source changed during evaluation; rerun with frozen code")
    if "dataset" in config and fingerprint(dataset_path) != dataset["sha256"]:
        raise ValueError("dataset changed during evaluation; rerun with an immutable input")
    if "dataset" not in config and "dataset_fingerprint" in result:
        actual_fingerprint = result["dataset_fingerprint"]
        if (not isinstance(actual_fingerprint, str) or len(actual_fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in actual_fingerprint)):
            raise ValueError("generator dataset_fingerprint must be a SHA-256 hex string")
        dataset["sha256"] = actual_fingerprint
        dataset["fingerprint_kind"] = "generated_data_canonical_json"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:10]
    record = {"schema_version": 1, "id": run_id, "timestamp": utc_now(),
              "config": config, "config_sha256": config_hash, "seed": seed,
              "dataset": dataset, "source_sha256": code_hash,
              "git": git_state(), "environment": environment(),
              "elapsed_seconds": elapsed, "result": result,
              "submission_ready": False}
    directory = project_path(Path(root) / "experiments" / run_id, root)
    directory.mkdir(parents=True, exist_ok=False)
    save_json(directory / "config.json", config)
    save_json(directory / "result.json", record)
    log = project_path(Path(root) / "memory" / "experiments.jsonl", root)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as stream:
        stream.write(canonical({"id": run_id, "family": family, "seed": seed,
                                "timestamp": record["timestamp"], "config_sha256": config_hash,
                                "metrics": result.get("metrics", {})}) + "\n")
    return record


def load_run(run_id, root=ROOT):
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("use an experiment ID, not a path")
    path = project_path(Path(root) / "experiments" / run_id / "result.json", root)
    return json.loads(path.read_text())


def numeric_metrics(value, prefix=""):
    """Flatten observed numeric metrics without guessing which direction is better."""
    output = {}
    if isinstance(value, dict):
        for key, child in value.items():
            output.update(numeric_metrics(child, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        output[prefix] = value
    return output


def tournament(config, seeds, root=ROOT):
    if not seeds or len(seeds) > 100 or len(set(seeds)) != len(seeds):
        raise ValueError("provide 1-100 distinct paired seeds")
    records = [run({**config, "seed": seed}, root) for seed in seeds]
    # Each demo compares its methods on exactly the same input for that seed.
    rows = [numeric_metrics(record["result"].get("metrics", {})) for record in records]
    common = set.intersection(*(set(row) for row in rows))
    summary = {key: _summary([row[key] for row in rows]) for key in sorted(common)}
    # Compare named methods, rather than aggregating each path's selected
    # winner as if it were a fixed, independently evaluated strategy.
    comparisons = [_comparison_metrics(record["result"]) for record in records]
    strategies = set.intersection(*(set(comparison) for comparison in comparisons))
    strategy_comparison = {}
    for strategy in sorted(strategies):
        common_metrics = set.intersection(*(set(comparison[strategy]) for comparison in comparisons))
        strategy_comparison[strategy] = {
            metric: _summary([comparison[strategy][metric] for comparison in comparisons])
            for metric in sorted(common_metrics)
        }
    reference = {"market": "no_op", "ml": "train_mean"}.get(config["family"])
    if reference not in strategies:
        reference = None
    paired_differences = {}
    if reference is not None:
        for strategy in sorted(strategies - {reference}):
            paired_differences[strategy] = {}
            common_metrics = set(strategy_comparison[strategy]) & set(strategy_comparison[reference])
            for metric in sorted(common_metrics):
                differences = [comparison[strategy][metric] - comparison[reference][metric]
                               for comparison in comparisons]
                paired_differences[strategy][metric] = {
                    **_summary(differences), "seeds": list(seeds), "values": differences,
                }
    result = {"kind": "paired_seed_comparison", "family": config["family"], "seeds": seeds,
              "experiment_ids": [record["id"] for record in records], "metrics": summary,
              "strategy_comparison": strategy_comparison,
              "reference_strategy": reference, "paired_differences": paired_differences,
              "difference_definition": "candidate minus reference on identical seeds; lower is better for losses, higher for rewards; confirm the official objective",
              "warning": "Seeds describe sensitivity, not confidence in official performance. Top-level best_* metrics select a winner per path; use named strategy comparisons to assess a fixed policy."}
    save_json(project_path(Path(root) / "experiments" / records[-1]["id"] / "tournament.json", root), result)
    return result


def _summary(values):
    return {"mean": statistics.mean(values), "min": min(values), "max": max(values),
            "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "count": len(values)}


def _comparison_metrics(result):
    output = {}
    for row in result.get("comparison", []):
        strategy = row.get("strategy")
        if not isinstance(strategy, str) or not strategy or strategy in output:
            raise ValueError("comparison rows require distinct nonempty strategy names")
        output[strategy] = numeric_metrics(row)
    return output
