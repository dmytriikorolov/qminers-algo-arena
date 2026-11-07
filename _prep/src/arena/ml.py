"""Small dependency-free tabular baselines with chronological validation.

The pipeline fits imputation and scaling on training rows only. A chronological
split prevents one common form of leakage, but cannot prove features were known
at prediction time; the caller must verify their provenance.
"""

import csv
import hashlib
import json
import math
import random
from pathlib import Path


def _number(value, missing=False):
    if value is None or value == "":
        if missing:
            return None
        raise ValueError("target/time values cannot be missing")
    number = float(value)
    if not math.isfinite(number):
        if missing and math.isnan(number):
            return None
        raise ValueError("values must be finite")
    return number


def chronological_split(n, train_fraction=0.6, validation_fraction=0.2, gap=0):
    """Return train/validation/test index ranges, dropping gap rows at boundaries.

    For labels that look ahead h observations, gap >= h keeps training labels
    from reaching the first validation observation (likewise validation/test).
    Fractions refer to the original row count, not the rows left after purging.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 6:
        raise ValueError("need at least six observations")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("leave a nonempty test fraction")
    if isinstance(gap, bool) or not isinstance(gap, int) or gap < 0:
        raise ValueError("gap must be a nonnegative integer")
    first = int(n * train_fraction)
    second = int(n * (train_fraction + validation_fraction))
    splits = (range(0, first - gap), range(first, second - gap), range(second, n))
    if any(len(part) < 2 for part in splits):
        raise ValueError("each split needs at least two rows after purging")
    return splits


def _fit_transform(x):
    columns = list(zip(*x))
    means = []
    scales = []
    for column in columns:
        observed = [value for value in column if value is not None]
        mean = sum(observed) / len(observed) if observed else 0.0
        if not math.isfinite(mean):
            raise ValueError("feature mean overflow; rescale feature units before fitting")
        filled = [mean if value is None else value for value in column]
        try:
            variance = sum((value - mean) ** 2 for value in filled) / len(filled)
        except OverflowError as exc:
            raise ValueError("feature variance overflow; rescale feature units before fitting") from exc
        if not math.isfinite(variance):
            raise ValueError("feature variance overflow; rescale feature units before fitting")
        means.append(mean)
        scales.append(math.sqrt(variance) or 1.0)
    return means, scales


def _transform(x, means, scales):
    return [[1.0] + [((means[j] if value is None else value) - means[j]) / scales[j]
                    for j, value in enumerate(row)] for row in x]


def _solve(matrix, vector):
    """Gauss-Jordan with pivoting; tiny dense systems only."""
    size = len(vector)
    rows = [list(row) + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda index: abs(rows[index][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise ValueError("singular system; use a positive ridge penalty")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for index in range(size):
            if index == column:
                continue
            factor = rows[index][column]
            rows[index] = [a - factor * b for a, b in zip(rows[index], rows[column])]
    return [row[-1] for row in rows]


def _ridge(x, y, penalty):
    size = len(x[0])
    matrix = [[sum(row[i] * row[j] for row in x) / len(x)
               + (penalty if i == j and i != 0 else 0.0)
               for j in range(size)] for i in range(size)]
    vector = [sum(row[j] * target for row, target in zip(x, y)) / len(x)
              for j in range(size)]
    return _solve(matrix, vector)


def _sigmoid(value):
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _predict(x, weights, classification=False):
    scores = [sum(value * weight for value, weight in zip(row, weights)) for row in x]
    return [_sigmoid(value) for value in scores] if classification else scores


def _logistic(x, y, penalty, iterations=400):
    frequency = min(1 - 1e-8, max(1e-8, sum(y) / len(y)))
    weights = [math.log(frequency / (1 - frequency))] + [0.0] * (len(x[0]) - 1)
    # A conservative learning rate bounded by feature magnitudes.
    rate = 1.0 / (0.25 * max(sum(value * value for value in row) for row in x) + penalty + 1)
    for _ in range(iterations):
        predictions = _predict(x, weights, True)
        gradients = [sum((prediction - target) * row[j]
                         for prediction, target, row in zip(predictions, y, x)) / len(x)
                     + (penalty * weight if j else 0.0)
                     for j, weight in enumerate(weights)]
        weights = [weight - rate * gradient for weight, gradient in zip(weights, gradients)]
    return weights


def score(y, predictions, task="regression"):
    if len(y) != len(predictions) or not y:
        raise ValueError("metrics need equally sized, nonempty inputs")
    if any(not math.isfinite(value) for value in list(y) + list(predictions)):
        raise ValueError("metrics need finite inputs")
    if task == "regression":
        mse = sum((target - prediction) ** 2 for target, prediction in zip(y, predictions)) / len(y)
        mae = sum(abs(target - prediction) for target, prediction in zip(y, predictions)) / len(y)
        return {"mse": mse, "rmse": math.sqrt(mse), "mae": mae}
    if task != "classification":
        raise ValueError("task must be regression or classification")
    if any(value not in (0, 1) for value in y) or any(not 0 <= value <= 1 for value in predictions):
        raise ValueError("classification needs binary targets and probabilities in [0,1]")
    clipped = [min(1 - 1e-12, max(1e-12, value)) for value in predictions]
    return {
        "brier": sum((target - value) ** 2 for target, value in zip(y, predictions)) / len(y),
        "log_loss": -sum(target * math.log(value) + (1 - target) * math.log(1 - value)
                         for target, value in zip(y, clipped)) / len(y),
        "accuracy": sum((value >= 0.5) == target for target, value in zip(y, predictions)) / len(y),
    }


def run_rows(rows, target, features, time_column, task="regression", gap=0,
             label_horizon=0, group_column=None, penalties=(0.001, 0.1, 1.0),
             seed=7):
    """Fit on training data, choose penalty on validation, evaluate test once.

    Rows must already be ordered by a strictly increasing numeric or ISO time
    column. Group separation, if requested, is checked rather than inferred.
    The test rows never influence training, preprocessing, or model selection.
    """
    if task not in ("regression", "classification"):
        raise ValueError("task must be regression or classification")
    features = list(features)
    if not features or len(set(features)) != len(features) or len(features) > 64:
        raise ValueError("specify 1-64 distinct features")
    if target in features or time_column in features or (group_column and group_column in features):
        raise ValueError("target/time/group columns must not be features")
    if not isinstance(label_horizon, int) or isinstance(label_horizon, bool) or label_horizon < 0:
        raise ValueError("label_horizon must be a nonnegative integer")
    if gap < label_horizon:
        raise ValueError("gap must cover the label horizon")
    if not rows or len(rows) > 100000:
        raise ValueError("supply 6-100000 rows; use a numerical library for larger datasets")
    required = set(features + [target, time_column] + ([group_column] if group_column else []))
    if any(not required.issubset(row) for row in rows):
        raise ValueError("a required column is missing")
    times = [row[time_column] for row in rows]
    if any(value is None or value == "" for value in times):
        raise ValueError("timestamps cannot be missing")
    # CSV numeric times must compare numerically; ISO timestamps compare lexically.
    try:
        ordered_times = [_number(value) for value in times]
    except (ValueError, TypeError):
        from datetime import datetime
        try:
            ordered_times = [datetime.fromisoformat(str(value).replace("Z", "+00:00")) for value in times]
        except (ValueError, TypeError) as exc:
            raise ValueError("timestamps must be numeric or ISO 8601") from exc
    try:
        if any(left >= right for left, right in zip(ordered_times, ordered_times[1:])):
            raise ValueError("timestamps must be strictly increasing; aggregate ties explicitly")
    except TypeError as exc:
        raise ValueError("timestamps must use consistent time zones") from exc
    train, validation, test = chronological_split(len(rows), gap=gap)
    if group_column:
        groups = [{rows[i][group_column] for i in split} for split in (train, validation, test)]
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise ValueError("groups overlap between chronological splits")
    x = [[_number(row[name], missing=True) for name in features] for row in rows]
    y = [_number(row[target]) for row in rows]
    if task == "classification" and any(value not in (0.0, 1.0) for value in y):
        raise ValueError("binary classification targets must be 0 or 1")
    # This catches direct copies only; temporal/provenance leakage requires review.
    for j, name in enumerate(features):
        if len({y[i] for i in train}) > 1 and all(x[i][j] == y[i] for i in train):
            raise ValueError("feature duplicates the training target: " + name)
    means, scales = _fit_transform([x[i] for i in train])
    transformed = _transform(x, means, scales)
    train_x, train_y = [transformed[i] for i in train], [y[i] for i in train]
    validation_y = [y[i] for i in validation]
    test_y = [y[i] for i in test]
    constant = sum(train_y) / len(train_y)
    primary = "log_loss" if task == "classification" else "mse"
    model_name = "logistic" if task == "classification" else "ridge"
    candidates = []
    for penalty in penalties:
        if not math.isfinite(penalty) or penalty <= 0:
            raise ValueError("penalties must be positive finite numbers")
        weights = (_logistic if task == "classification" else _ridge)(train_x, train_y, penalty)
        predictions = _predict([transformed[i] for i in validation], weights, task == "classification")
        candidates.append((score(validation_y, predictions, task)[primary], penalty, weights))
    if not candidates:
        raise ValueError("provide at least one penalty")
    validation_loss, penalty, weights = min(candidates, key=lambda candidate: candidate[0])
    predictions = _predict([transformed[i] for i in test], weights, task == "classification")
    baseline_metrics = score(test_y, [constant] * len(test_y), task)
    model_metrics = score(test_y, predictions, task)
    bins = []
    if task == "classification":
        for low in (0.0, 0.2, 0.4, 0.6, 0.8):
            indices = [i for i, value in enumerate(predictions) if low <= value <= 1 and
                       (value < low + 0.2 or low == 0.8)]
            if indices:
                bins.append({"lower": low, "count": len(indices),
                             "mean_probability": sum(predictions[i] for i in indices) / len(indices),
                             "observed_frequency": sum(test_y[i] for i in indices) / len(indices)})
    return {
        "family": "ml", "synthetic": None, "data_origin": "unverified_caller_input",
        "task": task, "seed": seed,
        "metrics": {"baseline": baseline_metrics, model_name: model_metrics,
                    "improvement": baseline_metrics[primary] - model_metrics[primary]},
        "comparison": [{"strategy": "train_mean", **baseline_metrics},
                       {"strategy": model_name, **model_metrics}],
        "split": {"train_rows": len(train), "validation_rows": len(validation),
                  "test_rows": len(test), "gap": gap, "label_horizon": label_horizon,
                  "train_end": train.stop - 1, "validation_start": validation.start,
                  "validation_end": validation.stop - 1, "test_start": test.start},
        "selection": {"penalty": penalty, "validation_loss": validation_loss,
                      "primary_metric": primary, "test_used_for_selection": False},
        "model": {"name": model_name, "features": features, "weights": weights,
                  "imputation_means": means, "scales": scales, "constant": constant},
        "data_quality": {"missing_features": sum(value is None for row in x for value in row),
                         "train_target_mean": constant},
        "calibration": bins,
        "warnings": ["Chronology does not establish feature availability; inspect provenance.",
                     "Final holdout is evaluated once by this run; repeated tuning can overfit it."],
    }


def run_csv(path, target, features, time_column, **config):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV must have distinct column names")
        rows = []
        for row in reader:
            if len(rows) >= 100000:
                raise ValueError("CSV exceeds the 100000-row baseline limit")
            if None in row:
                raise ValueError("CSV row has excess fields")
            rows.append(row)
    result = run_rows(rows, target, features, time_column, **config)
    result["source"] = str(path)
    return result


def demo(seed=7, task="regression", rows=240, **config):
    unknown = set(config) - {"gap", "label_horizon", "group_column", "penalties"}
    if unknown:
        raise ValueError("unknown ML demo parameters: " + ", ".join(sorted(unknown)))
    if not isinstance(rows, int) or isinstance(rows, bool) or not 30 <= rows <= 10000:
        raise ValueError("synthetic demo rows must be 30-10000")
    rng = random.Random(seed)
    data = []
    for index in range(rows):
        x = rng.gauss(0, 1)
        nuisance = rng.gauss(0, 1)
        target = 2.5 * x - 0.6 * nuisance + rng.gauss(0, 0.3)
        if task == "classification":
            target = int(rng.random() < _sigmoid(target))
        data.append({"time": index, "x": None if index % 17 == 0 else x,
                     "nuisance": nuisance, "target": target})
    result = run_rows(data, target="target", features=["x", "nuisance"],
                      time_column="time", task=task, seed=seed, **config)
    result["synthetic"] = True
    result["data_origin"] = "seeded_synthetic_demo"
    result["source"] = "seeded independent synthetic observations; no contest data"
    result["dataset_fingerprint"] = hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    result["dataset_fingerprint_format"] = "SHA-256 of actual generated rows as UTF-8 canonical JSON (sorted keys, compact separators)"
    return result
