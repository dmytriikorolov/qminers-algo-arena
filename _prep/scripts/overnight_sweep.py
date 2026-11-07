"""Opt-in, bounded synthetic evaluation; never installs a schedule."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import re
import signal
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))
from arena.common import git_state, save_json, source_fingerprint
from arena.trading import mock_scenario, replay

REGIMES = ("mean_reverting", "trend", "trend_down", "volatile")
STRATEGIES = ("fixed", "inventory", "guarded_fixed")
MAX_SECONDS = 20 * 60


def frozen_source():
    return hashlib.sha256(source_fingerprint().encode() + Path(__file__).read_bytes()).hexdigest()


def check_source(expected):
    if frozen_source() != expected:
        raise RuntimeError("source changed; reserve a new run key after freezing code")


def sweep(seeds, steps, expected):
    rows = []
    for regime in REGIMES:
        for seed in range(seeds):
            check_source(expected)
            events = mock_scenario(seed=seed, steps=steps, regime=regime)
            for strategy in STRATEGIES:
                result = replay(events, strategy=strategy, fee_per_unit=0.01, position_limit=10)
                rows.append({"regime": regime, "seed": seed,
                             **{key: value for key, value in result.items() if key != "equity"}})
    check_source(expected)
    return rows


def run(args, root=ROOT):
    if not re.fullmatch(r"\d{8}T\d{6}Z", args.run_key):
        raise ValueError("run key must be a UTC ID: YYYYMMDDTHHMMSSZ")
    datetime.strptime(args.run_key, "%Y%m%dT%H%M%SZ")
    if not 1 <= args.seeds <= 20 or not 1 <= args.steps <= 300:
        raise ValueError("budget must be 1-20 seeds and 1-300 steps")
    started = datetime.now(timezone.utc)
    target = started
    if args.start_at:
        target = datetime.fromisoformat(args.start_at)
        if target.tzinfo is None or not started < target <= started + timedelta(days=1):
            raise ValueError("start-at must be timezone-aware, future, and within 24 hours")
    local = target.astimezone(ZoneInfo("Europe/Prague"))
    stop = local.replace(hour=7, minute=0, second=0, microsecond=0)
    seconds = min(MAX_SECONDS, (stop - target).total_seconds()) if args.start_at else MAX_SECONDS
    if seconds <= 0:
        raise ValueError("waiting mode must start before 07:00 Europe/Prague")
    output = Path(root) / "overnight_runs"
    base = output.resolve()
    if output.is_symlink() or not base.is_relative_to(Path(root).resolve()):
        raise ValueError("output directory must remain inside the project")
    base.mkdir(exist_ok=True)
    lock = os.open(base, os.O_RDONLY)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory = base / args.run_key
        directory.mkdir()  # Exclusive reservation persists even after failure/interruption.
        expected = frozen_source()
        record = {"synthetic": True, "submission_ready": False, "status": "waiting",
                  "created_utc": started.isoformat(), "start_at": target.isoformat(),
                  "source_sha256": expected, "git": git_state(),
                  "config": {"seeds": list(range(args.seeds)), "steps": args.steps,
                             "regimes": REGIMES, "strategies": STRATEGIES,
                             "fee_per_unit": 0.01, "position_limit": 10,
                             "max_seconds": seconds}}
        save_json(directory / "result.json", record)
        try:
            while datetime.now(timezone.utc) < target:
                check_source(expected)
                time.sleep(max(0, min(30, (target - datetime.now(timezone.utc)).total_seconds())))
            check_source(expected)
            if args.start_at:
                seconds = min(seconds, (stop - datetime.now(timezone.utc)).total_seconds())
            if seconds <= 0:
                raise TimeoutError("07:00 deadline reached")
            previous = signal.signal(signal.SIGALRM, deadline)
            began = time.monotonic()
            signal.setitimer(signal.ITIMER_REAL, seconds)
            try:
                record["metrics"] = sweep(args.seeds, args.steps, expected)
                record["elapsed_seconds"] = time.monotonic() - began
                record["status"] = "complete"
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
        except BaseException as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            save_json(directory / "result.json", record)
        return directory
    finally:
        os.close(lock)


def deadline(signum, frame):
    raise TimeoutError("bounded evaluation deadline reached")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-key", required=True, help="unique UTC ID YYYYMMDDTHHMMSSZ")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--start-at", help="optional future ISO timestamp with UTC offset")
    print(run(parser.parse_args()))
