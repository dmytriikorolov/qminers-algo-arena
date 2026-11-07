"""Bounded data inspection; no target or time column is silently inferred."""
import csv
import json
import math
from pathlib import Path

from .common import fingerprint


def _csv_rows(reader):
    try:
        yield from reader
    except csv.Error as exc:
        raise ValueError(f"invalid or oversized CSV field: {exc}") from exc


def _numeric_summary(values):
    numeric = []
    nonfinite = 0
    missing = 0
    text = 0
    for value in values:
        if value is None or str(value).strip() == "":
            missing += 1
            continue
        try:
            number = float(value)
        except (ValueError, TypeError):
            text += 1
            continue
        if math.isfinite(number):
            numeric.append(number)
        else:
            nonfinite += 1
    return {"missing": missing, "nonfinite": nonfinite, "text": text,
            "numeric": len(numeric), "min": min(numeric) if numeric else None,
            "max": max(numeric) if numeric else None}


def inspect_file(path, max_rows=10000, max_bytes=20 * 1024 * 1024):
    path = Path(path)
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    if not path.is_file():
        raise ValueError("input must be a regular file")
    if path.stat().st_size > max_bytes:
        raise ValueError(f"file exceeds inspection limit ({max_bytes} bytes); prepare a sample")
    info = {"path": str(path), "bytes": path.stat().st_size, "sha256": fingerprint(path)}
    if path.suffix.lower() in (".csv", ".tsv"):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = _csv_rows(csv.reader(stream, delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
            header = next(reader, [])
            if not header or len(set(header)) != len(header) or any(not col for col in header):
                raise ValueError("CSV requires unique, nonempty column names")
            rows = []
            malformed = 0
            truncated = False
            for index, row in enumerate(reader):
                if index >= max_rows:
                    truncated = True
                    break
                if len(row) != len(header):
                    malformed += 1
                rows.append((row + [None] * len(header))[:len(header)])
        info.update({"format": "csv", "sample_rows": len(rows), "truncated": truncated,
                     "malformed_rows": malformed,
                     "duplicate_rows_in_sample": len(rows) - len({tuple(row) for row in rows}),
                     "columns": {name: _numeric_summary(row[i] for row in rows)
                                 for i, name in enumerate(header)}})
    elif path.suffix.lower() == ".json":
        def reject_constant(value):
            raise ValueError(f"nonfinite JSON value: {value}")
        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"nonfinite JSON number: {value}")
            return number
        value = json.loads(path.read_text(), parse_constant=reject_constant, parse_float=finite_float)
        info.update({"format": "json", "type": type(value).__name__,
                     "keys": list(value)[:max_rows] if isinstance(value, dict) else None,
                     "items": len(value) if isinstance(value, (list, dict)) else 1})
    else:
        raise ValueError("supported inspection formats: .csv, .tsv, .json")
    return info


def diagnose_file(path, max_rows=10000):
    info = inspect_file(path, max_rows=max_rows)
    findings = []
    for name, summary in info.get("columns", {}).items():
        if summary["missing"] or summary["nonfinite"]:
            findings.append(f"{name}: validate missing/nonfinite values before training or trading")
        if summary["numeric"] and summary["min"] == summary["max"]:
            findings.append(f"{name}: constant in inspected sample")
    if info.get("duplicate_rows_in_sample"):
        findings.append("Duplicate rows: check event IDs or entity overlap before splitting")
    if info.get("malformed_rows"):
        findings.append("Malformed rows: repair schema before evaluation")
    return {"inspection": info, "findings": findings,
            "hypotheses": [{"status": "PROPOSED", "claim": "A simple baseline is useful",
                            "test": "Configure target/time/features, hold out future rows, compare on official metric"}],
            "unknowns": ["target", "timestamp semantics", "groups", "official metric"],
            "note": "No column meaning or predictive relationship has been inferred."}
