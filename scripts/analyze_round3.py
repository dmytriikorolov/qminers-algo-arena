"""Replay the public tapes and produce reproducible round 3 research.

Run from the repository root: .venv/bin/python scripts/analyze_round3.py
The matching engine is reused unchanged. Outputs are local, under logs/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulator.models import MarketOperation, OrderType, Side
from simulator.simulator import ExchangeSimulator
from simulator.strategy import BaseStrategy

GRID_US = 100_000
CACHE_VERSION = 2


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def quotes(engine: ExchangeSimulator) -> tuple[float, float]:
    # Reading the engine's sorted prices avoids constructing millions of views.
    book = engine.book
    bid = book._bid_prices[-1] if book._bid_prices else math.nan
    ask = book._ask_prices[0] if book._ask_prices else math.nan
    return bid, ask


def depth(engine: ExchangeSimulator, bid: float, ask: float) -> tuple[int, int, int, int]:
    book = engine.book
    b1 = sum(o.remaining_quantity for o in book._bids[bid].queue) if np.isfinite(bid) else 0
    a1 = sum(o.remaining_quantity for o in book._asks[ask].queue) if np.isfinite(ask) else 0
    b5 = sum(o.remaining_quantity for o in book.iter_levels(Side.BUY, 5))
    a5 = sum(o.remaining_quantity for o in book.iter_levels(Side.SELL, 5))
    return b1, a1, b5, a5


def replay(path: Path, output: Path, refresh: bool = False) -> dict:
    name = path.stem
    cache = output / f"{name}_metadata.json"
    identity = fingerprint(path)
    engine_identity = {name: fingerprint(ROOT / "simulator" / name) for name in ["simulator.py", "models.py"]}
    if cache.exists() and not refresh:
        meta = json.loads(cache.read_text())
        if (meta.get("sha256") == identity and meta.get("cache_version") == CACHE_VERSION
                and meta.get("engine_sha256") == engine_identity):
            print(f"{name}: verified cache", flush=True)
            return meta

    engine = ExchangeSimulator(BaseStrategy())
    samples, trades, changes = [], [], []
    counters = np.zeros(8, dtype=np.float64)
    # events, G inserts, F inserts, cancels, buy executed qty, sell executed qty,
    # match count, sum(price * executed qty)
    previous_us, next_grid, area, valid_us = 0, GRID_US, 0.0, 0
    bid, ask = math.nan, math.nan
    unknown_cancels, previous_event, ties, last_progress = 0, -1, 0, time.monotonic()
    size_rows = []
    inserted_quantity, canceled_quantity, ioc_unfilled = 0, 0, 0
    for event in engine.iter_backtest(path):
        now = event.timestamp_us
        if now < previous_event:
            raise ValueError(f"Unsorted event at {now}")
        ties += now == previous_event
        previous_event = now
        valid = np.isfinite(bid) and np.isfinite(ask)
        spread = ask - bid if valid else 0.0
        while next_grid <= now:
            b1, a1, b5, a5 = depth(engine, bid, ask)
            samples.append((
                next_grid / 1e6, bid, ask, b1, a1, b5, a5,
                area + spread * (next_grid - previous_us),
                valid_us + (next_grid - previous_us if valid else 0), *counters,
            ))
            next_grid += GRID_US
        area += spread * (now - previous_us)
        valid_us += now - previous_us if valid else 0
        previous_us = now

        pre_mid = (bid + ask) / 2 if valid else math.nan
        pre_spread = ask - bid if valid else math.nan
        pre_imb = math.nan
        if event.operation == MarketOperation.INSERT:
            crossing = valid and (event.price >= ask if event.side == Side.BUY else event.price <= bid)
            if crossing:
                b1, a1, _, _ = depth(engine, bid, ask)
                pre_imb = (b1 - a1) / (b1 + a1)
            counters[1 if event.order_type == OrderType.LIMIT else 2] += 1
            inserted_quantity += event.volume
            size_rows.append((event.volume, event.order_type == OrderType.IOC))
        else:
            counters[3] += 1
            unknown_cancels += engine.book.get(event.order_id) is None
            resting = engine.book.get(event.order_id)
            canceled_quantity += resting.remaining_quantity if resting else 0
        counters[0] += 1
        engine.current_ts_us = now
        engine._process_market_event(event)
        if event.operation == MarketOperation.INSERT and event.order_type == OrderType.IOC:
            ioc_unfilled += event.volume - sum(t.quantity for t in engine._trades)
        if engine._trades:
            quantity = sum(t.quantity for t in engine._trades)
            notional = sum(t.quantity * t.price for t in engine._trades)
            sign = 1 if event.side == Side.BUY else -1
            counters[4 if sign == 1 else 5] += quantity
            counters[6] += len(engine._trades)
            counters[7] += notional
            trades.append((now / 1e6, sign, quantity, notional / quantity, pre_mid, pre_spread, pre_imb))
            engine._trades.clear()
        old_quotes = (bid, ask)
        bid, ask = quotes(engine)
        if (bid, ask) != old_quotes:
            changes.append((now / 1e6, bid, ask))
        if counters[0] % 250_000 == 0:
            elapsed = time.monotonic() - last_progress
            print(f"{name}: {int(counters[0]):,} events, t={now/1e6:.1f}s, last 250k in {elapsed:.1f}s", flush=True)
            last_progress = time.monotonic()

    columns = ["time", "bid", "ask", "bid_qty", "ask_qty", "bid5_qty", "ask5_qty", "spread_area_us", "valid_us",
               "events_cum", "g_cum", "f_cum", "cancels_cum", "buy_qty_cum", "sell_qty_cum", "matches_cum", "notional_cum"]
    frame = pd.DataFrame(samples, columns=columns)
    frame["mid"] = (frame.bid + frame.ask) / 2
    frame["spread"] = frame.ask - frame.bid
    frame["imbalance"] = (frame.bid_qty - frame.ask_qty) / (frame.bid_qty + frame.ask_qty)
    frame["imbalance5"] = (frame.bid5_qty - frame.ask5_qty) / (frame.bid5_qty + frame.ask5_qty)
    frame.to_csv(output / f"{name}_100ms.csv.gz", index=False)
    pd.DataFrame(trades, columns=["time", "sign", "quantity", "price", "pre_mid", "pre_spread", "pre_imbalance"]).to_csv(
        output / f"{name}_trades.csv.gz", index=False)
    pd.DataFrame(changes, columns=["time", "bid", "ask"]).to_csv(output / f"{name}_quotes.csv.gz", index=False)
    sizes = np.asarray(size_rows)
    final_resting_quantity = sum(o.remaining_quantity for o in engine.book._orders.values())
    quantity_residual = inserted_quantity - canceled_quantity - ioc_unfilled - 2 * int(counters[4] + counters[5]) - final_resting_quantity
    if quantity_residual != 0:
        raise AssertionError(f"Quantity conservation failed: {quantity_residual}")
    metadata = {
        "source": str(path.relative_to(ROOT)), "sha256": identity, "cache_version": CACHE_VERSION,
        "engine_sha256": engine_identity, "quantity_conservation_residual": quantity_residual,
        "inserted_quantity": inserted_quantity, "canceled_quantity": canceled_quantity,
        "ioc_unfilled_quantity": ioc_unfilled, "final_resting_quantity": final_resting_quantity,
        "duration_s": previous_us / 1e6, "events": int(counters[0]), "g_inserts": int(counters[1]),
        "f_inserts": int(counters[2]), "cancels": int(counters[3]), "unknown_cancels": int(unknown_cancels),
        "executed_qty": int(counters[4] + counters[5]), "matches": int(counters[6]), "ties": int(ties),
        "final_bid": bid, "final_ask": ask, "valid_book_fraction": valid_us / previous_us,
        "mean_spread_time_weighted": area / valid_us,
        "insert_size_quantiles": {"IOC" if ioc else "G": dict(zip(["p50", "p90", "p99", "max"],
            np.quantile(sizes[sizes[:, 1] == ioc, 0], [0.5, 0.9, 0.99, 1]).tolist())) for ioc in [0, 1]},
    }
    cache.write_text(json.dumps(metadata, indent=2))
    return metadata


def load_round(output: Path, name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    grid = pd.read_csv(output / f"{name}_100ms.csv.gz")
    seconds = grid[np.isclose(grid.time % 1, 0)].copy().reset_index(drop=True)
    for label, source in {"events": "events_cum", "g_inserts": "g_cum", "f_inserts": "f_cum", "cancels": "cancels_cum",
                          "buy_qty": "buy_qty_cum", "sell_qty": "sell_qty_cum", "matches": "matches_cum"}.items():
        seconds[label] = seconds[source].diff().fillna(seconds[source])
    seconds["trade_qty"] = seconds.buy_qty + seconds.sell_qty
    seconds["flow"] = (seconds.buy_qty - seconds.sell_qty) / seconds.trade_qty.replace(0, np.nan)
    seconds["return1"] = seconds.mid.diff()
    seconds["rv30"] = seconds.return1.pow(2).rolling(30).mean().pow(0.5)
    seconds["spread_mean"] = seconds.spread_area_us.diff() / seconds.valid_us.diff()
    seconds["min_depth"] = seconds[["bid_qty", "ask_qty"]].min(axis=1)
    seconds["drawdown"] = seconds.mid - seconds.mid.cummax()
    return grid, seconds


def block_interval(values: np.ndarray, weights: np.ndarray | None = None, block: int = 600) -> tuple[float, float]:
    """Moving-block bootstrap on the regular grid; NaNs preserve temporal gaps.

    Default block is 60 seconds on a 100 ms grid. Caller must adjust for other grids.
    """
    values = np.asarray(values, dtype=float)
    weights = np.ones(len(values)) if weights is None else np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights)
    numerator = np.where(valid, values * weights, 0.0)
    denominator = np.where(valid, weights, 0.0)
    if denominator.sum() == 0:
        return math.nan, math.nan
    block = min(block, max(1, len(values) // 4))
    ns = np.r_[0.0, np.cumsum(numerator)]
    ds = np.r_[0.0, np.cumsum(denominator)]
    rng = np.random.default_rng(20261108)
    starts = rng.integers(0, len(values) - block + 1, (800, math.ceil(len(values) / block)))
    n = (ns[starts + block] - ns[starts]).sum(axis=1)
    d = (ds[starts + block] - ds[starts]).sum(axis=1)
    means = np.divide(n, d, out=np.full(len(d), np.nan), where=d > 0)
    return tuple(np.nanquantile(means, [0.025, 0.975]).tolist())


def summarize(meta: dict, grid: pd.DataFrame, seconds: pd.DataFrame, changes: pd.DataFrame) -> dict:
    mid = ((changes.bid + changes.ask) / 2).dropna()
    ret = seconds.return1.dropna()
    out = dict(meta)
    out.update({
        "mid_start": float(mid.iloc[0]), "mid_end": float((meta["final_bid"] + meta["final_ask"]) / 2),
        "mid_min": float(mid.min()), "mid_max": float(mid.max()),
        "rms_return1": float(np.sqrt(np.mean(ret ** 2))), "max_drawdown_ticks": float((mid.cummax() - mid).max()),
        "spread1_share_grid": float((grid.spread == 1).mean()), "spread_ge4_share_grid": float((grid.spread >= 4).mean()),
        "l1_min_median": float(grid[["bid_qty", "ask_qty"]].min(axis=1).median()),
        "jump_ge5_count": int((ret.abs() >= 5).sum()), "jump_ge10_count": int((ret.abs() >= 10).sum()),
        "lag1_return_corr": float(ret.autocorr()), "lag1_abs_return_corr": float(ret.abs().autocorr()),
        "top1pct_variance_share": float(ret.pow(2).nlargest(max(1, math.ceil(len(ret) / 100))).sum() / ret.pow(2).sum()),
    })
    out["net_move_ticks"] = out["mid_end"] - out["mid_start"]
    return out


def signals(grid: pd.DataFrame, seconds: pd.DataFrame, output: Path) -> pd.DataFrame:
    rows = []
    grid = grid.copy()
    # All rolling inputs end at the decision time. No forward-filled future observations.
    grid["flow1"] = (grid.buy_qty_cum.diff(10) - grid.sell_qty_cum.diff(10)) / (
        grid.buy_qty_cum.diff(10) + grid.sell_qty_cum.diff(10)).replace(0, np.nan)
    grid["momentum30"] = grid.mid.diff(300)
    grid["momentum120"] = grid.mid.diff(1200)
    split = 3000.0
    for feature, threshold in [("imbalance", 0.6), ("imbalance5", 0.4), ("flow1", 0.6),
                               ("momentum30", 5.0), ("momentum120", 10.0)]:
        x = grid[feature]
        direction = np.where(x > threshold, 1, np.where(x < -threshold, -1, 0))
        for horizon in [0.1, 0.5, 1, 5, 10, 30, 60]:
            forward = grid.mid.shift(-round(horizon * 10)) - grid.mid
            for period, mask in [
                ("first_half", (grid.time >= 120) & (grid.time + horizon < split)),
                ("second_half", (grid.time >= split) & (grid.time + horizon <= grid.time.iloc[-1])),
            ]:
                selected = mask & (direction != 0) & x.notna() & forward.notna()
                values = np.where(selected, direction * forward, np.nan)
                ci_lo, ci_hi = block_interval(values[np.asarray(mask)], block=max(600, round(horizon * 20)))
                # Approximate immediate round-trip spread burden, diagnostic only.
                spread_cost = (grid.spread + grid.spread.shift(-round(horizon * 10))) / 2
                fade_net = -direction * forward - spread_cost
                fade_lo, fade_hi = block_interval(np.where(selected, fade_net, np.nan)[np.asarray(mask)],
                                                  block=max(600, round(horizon * 20)))
                rows.append({"feature": feature, "threshold": threshold, "horizon_s": horizon, "period": period,
                             "n": int(selected.sum()), "coverage": float(selected.sum() / mask.sum()),
                             "signed_mid_move": float(np.nanmean(values)), "ci_low": ci_lo, "ci_high": ci_hi,
                             "after_spread": float((direction * forward - spread_cost)[selected].mean()),
                             "fade_after_spread": float(fade_net[selected].mean()), "fade_net_ci_low": fade_lo, "fade_net_ci_high": fade_hi,
                             "mean_spread_cost": float(spread_cost[selected].mean())})
    result = pd.DataFrame(rows)
    result.to_csv(output / "signal_validation.csv", index=False)
    return result


def markouts(output: Path, name: str) -> pd.DataFrame:
    trades = pd.read_csv(output / f"{name}_trades.csv.gz")
    changes = pd.read_csv(output / f"{name}_quotes.csv.gz")
    times = changes.time.to_numpy()
    mids = ((changes.bid + changes.ask) / 2).to_numpy()
    end = json.loads((output / f"{name}_metadata.json").read_text())["duration_s"]
    trades["own_imbalance"] = -trades.sign * trades.pre_imbalance
    groups = {
        "all": np.ones(len(trades), dtype=bool),
        "spread=1": trades.pre_spread == 1,
        "spread=2-3": trades.pre_spread.between(2, 3),
        "spread>=4": trades.pre_spread >= 4,
        "maker side thin (<-0.6)": trades.own_imbalance < -0.6,
        "maker side thick (>0.6)": trades.own_imbalance > 0.6,
    }
    rows = []
    for horizon in [0, 0.005, 0.1, 0.5, 1, 5, 10, 30]:
        target = trades.time.to_numpy() + horizon
        indices = np.searchsorted(times, target, side="right") - 1
        future = mids[np.maximum(indices, 0)]
        edge = trades.sign.to_numpy() * (trades.price.to_numpy() - future)
        valid = (target <= end) & (indices >= 0) & np.isfinite(edge)
        for group, mask in groups.items():
            selected = valid & mask
            qty = trades.quantity.to_numpy()[selected]
            rows.append({"round": name, "group": group, "horizon_s": horizon, "events": int(selected.sum()),
                         "quantity": int(qty.sum()), "maker_edge_ticks_per_lot": float(np.average(edge[selected], weights=qty)) if len(qty) else math.nan})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "logs/round3_analysis")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--replay-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summaries, frames = [], {}
    for name in ["round1", "round2_public", "round3_public"]:
        meta = replay(ROOT / "data" / f"{name}.csv", args.output, args.refresh)
        grid, seconds = load_round(args.output, name)
        frames[name] = (grid, seconds)
        changes = pd.read_csv(args.output / f"{name}_quotes.csv.gz")
        summaries.append(summarize(meta, grid, seconds, changes))
        seconds.to_csv(args.output / f"{name}_1s.csv", index=False)
    (args.output / "summary.json").write_text(json.dumps(summaries, indent=2))
    pd.DataFrame(summaries).drop(columns=["insert_size_quantiles", "engine_sha256"]).to_csv(args.output / "round_comparison.csv", index=False)
    if not args.replay_only:
        for strategy in ["full_two_sided", "capacity_inventory_cycler", "adaptive_ml_regime"]:
            destination = args.output / "benchmarks" / strategy
            if args.refresh or not (destination / "result.json").exists():
                subprocess.run([sys.executable, "-m", "simulator.main", "--strategy", f"strategies/{strategy}.py",
                                "--backtest", "data/round3_public.csv", "--log-dir", str(destination), "--no-logs"],
                               cwd=ROOT, check=True)
        grid, seconds = frames["round3_public"]
        signals(grid, seconds, args.output)
        pd.concat([markouts(args.output, name) for name in frames], ignore_index=True).to_csv(args.output / "maker_markouts.csv", index=False)
        from round3_report import build_report
        build_report(args.output, frames, summaries)
    for summary in summaries:
        print(f"{Path(summary['source']).stem}: {summary['events']:,} events; "
              f"1 s RMS {summary['rms_return1']:.3f} ticks; median thinner L1 {summary['l1_min_median']:.0f}; "
              f"quantity residual {summary['quantity_conservation_residual']}", flush=True)


if __name__ == "__main__":
    main()
