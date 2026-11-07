"""Bounded, causal analysis of explicit CSV market schemas, without fill inference."""
from collections import deque
import csv
import math
from pathlib import Path
import statistics

from .common import fingerprint
from .trading import MarketFeatures, Snapshot

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100000
FEATURE_ROW_LIMIT = 200
SCHEMAS = {
    "snapshots": {"time", "bid", "ask", "bid_size", "ask_size"},
    "bars": {"time", "open", "high", "low", "close", "volume"},
    "trades": {"time", "price", "quantity"},
}


def _number(value, column, row_number):
    if value is None or not str(value).strip():
        raise ValueError(f"row {row_number}: missing {column}")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"row {row_number}: {column} must be numeric") from None
    if not math.isfinite(number):
        raise ValueError(f"row {row_number}: nonfinite {column}")
    return number


class _Summary:
    def __init__(self):
        self.columns = {}

    def update(self, features):
        for name, value in features.items():
            if value is None or isinstance(value, (str, bool)):
                continue
            if not math.isfinite(value):
                raise ValueError(f"derived feature {name} is nonfinite; rescale input units")
            if name not in self.columns:
                self.columns[name] = {"count": 1, "min": value, "max": value, "mean": value}
                continue
            state = self.columns[name]
            state["count"] += 1
            # This weighted form avoids the overflow of (value - mean) for
            # otherwise finite observations of opposite sign.
            state["mean"] = (state["mean"] * ((state["count"] - 1) / state["count"])
                             + value / state["count"])
            state["min"] = min(state["min"], value)
            state["max"] = max(state["max"], value)


def depth_features(bids, asks, k=5):
    """Top-k imbalance only when actual sorted (price, quantity) levels exist."""
    if type(k) is not int or k < 1:
        raise ValueError("k must be a positive integer")
    if len(bids) > 10000 or len(asks) > 10000:
        raise ValueError("depth helper is bounded at 10000 levels per side")
    levels = []
    for name, side in (("bids", bids), ("asks", asks)):
        if not side:
            raise ValueError("both sides require actual price/quantity levels")
        converted = []
        for index, level in enumerate(side):
            if len(level) != 2:
                raise ValueError("each depth level requires price and quantity")
            price, quantity = (_number(value, name, index + 1) for value in level)
            if price <= 0 or quantity < 0:
                raise ValueError("depth prices must be positive and quantities nonnegative")
            if converted and ((name == "bids" and price >= converted[-1][0])
                              or (name == "asks" and price <= converted[-1][0])):
                raise ValueError("depth levels must have distinct sorted prices")
            converted.append((price, quantity))
        levels.append(converted)
    bids, asks = levels
    if bids[0][0] > asks[0][0]:
        raise ValueError("crossed depth book")
    try:
        bid_depth = math.fsum(quantity for _, quantity in bids[:k])
        ask_depth = math.fsum(quantity for _, quantity in asks[:k])
    except OverflowError as exc:
        raise ValueError("top-k depth sum overflows; rescale quantity units") from exc
    total = bid_depth + ask_depth
    if not math.isfinite(total) or total <= 0:
        raise ValueError("top-k depth must be finite and positive")
    return {"k": k, "bid_levels_used": min(k, len(bids)), "ask_levels_used": min(k, len(asks)),
            "bid_depth": bid_depth, "ask_depth": ask_depth,
            "depth_imbalance": (bid_depth - ask_depth) / total}


def analyze_csv(path, kind="snapshots", window=20, tick=0.1):
    """Validate all rows and retain only the latest 200 feature rows.

    `time` is an explicit numeric timestamp in caller-defined units. Strictly
    increasing times are required; do not fabricate sequencing for duplicates.
    Snapshots provide book state, bars provide completed-bar values, and trades
    provide only reported executions. None of these inputs implies our fills.
    """
    if kind not in SCHEMAS:
        raise ValueError("kind must be snapshots, bars or trades")
    if type(window) is not int or not 1 <= window <= 10000:
        raise ValueError("window must be an integer in 1..10000")
    if isinstance(tick, bool) or not isinstance(tick, (int, float)) or not math.isfinite(tick) or tick <= 0:
        raise ValueError("tick must be positive and finite")
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".csv":
        raise ValueError("market data must be a regular .csv file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"market CSV exceeds {MAX_BYTES} byte limit")
    required = SCHEMAS[kind]
    optional = {"side"} if kind == "trades" else set()
    features = deque(maxlen=FEATURE_ROW_LIMIT)
    values = deque(maxlen=window)
    returns = deque(maxlen=window)
    volumes = deque(maxlen=window)
    signed = deque(maxlen=window)
    market = MarketFeatures(window=window, tick=tick)
    summary = _Summary()
    previous_time = previous_price = None
    first_time = None
    rows = locked = unknown_side = 0
    buy_volume = sell_volume = 0.0
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream, strict=True)
            header = reader.fieldnames
            if not header or len(set(header)) != len(header):
                raise ValueError("market CSV requires distinct nonempty column names")
            if set(header) - required - optional or required - set(header):
                raise ValueError(f"{kind} schema requires {sorted(required)}; optional {sorted(optional)}")
            for row_number, row in enumerate(reader, start=2):
                if rows >= MAX_ROWS:
                    raise ValueError(f"market CSV exceeds {MAX_ROWS} row limit")
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"row {row_number}: column count differs from header")
                record = {name: _number(row[name], name, row_number) for name in required}
                timestamp = record["time"]
                if timestamp < 0 or (previous_time is not None and timestamp <= previous_time):
                    raise ValueError(f"row {row_number}: time must be nonnegative and strictly increasing")
                if first_time is None:
                    first_time = timestamp
                if kind == "snapshots":
                    snapshot = Snapshot(timestamp, record["bid"], record["ask"],
                                        record["bid_size"], record["ask_size"])
                    feature = {"time": timestamp, **market.update(snapshot)}
                    locked += int(feature["locked"])
                else:
                    if kind == "bars":
                        price, quantity = record["close"], record["volume"]
                        if (record["low"] <= 0 or record["high"] < record["low"]
                                or not record["low"] <= record["open"] <= record["high"]
                                or not record["low"] <= price <= record["high"] or quantity < 0):
                            raise ValueError(f"row {row_number}: invalid OHLC prices or negative volume")
                        feature = {"time": timestamp, "close": price,
                                   "bar_range": record["high"] - record["low"], "volume": quantity}
                    else:
                        price, quantity = record["price"], record["quantity"]
                        if price <= 0 or quantity <= 0:
                            raise ValueError(f"row {row_number}: trade price and quantity must be positive")
                        side = row.get("side", "").strip()
                        if side not in ("", "buy", "sell"):
                            raise ValueError(f"row {row_number}: side must be explicit buy/sell or empty")
                        signed_quantity = quantity * (1 if side == "buy" else -1) if side else None
                        signed.append(signed_quantity)
                        if not side:
                            unknown_side += 1
                        elif side == "buy":
                            buy_volume += quantity
                        else:
                            sell_volume += quantity
                        if not math.isfinite(buy_volume) or not math.isfinite(sell_volume):
                            raise ValueError("observed trade volume overflows; rescale quantity units")
                        feature = {"time": timestamp, "price": price, "quantity": quantity,
                                   "side": side or None, "signed_quantity": signed_quantity,
                                   "rolling_signed_quantity": (math.fsum(signed) if None not in signed else None)}
                    values.append(price)
                    volumes.append(quantity)
                    # Difference of logs avoids overflow in price / previous_price.
                    change = math.log(price) - math.log(previous_price) if previous_price is not None else 0.0
                    if previous_price is not None:
                        returns.append(change)
                    feature.update({"log_return": change, "rolling_mean": statistics.fmean(values),
                                    "volatility": statistics.pstdev(returns) if len(returns) > 1 else 0.0,
                                    "rolling_volume": math.fsum(volumes), "notional": price * quantity})
                    previous_price = price
                summary.update(feature)
                features.append(feature)
                rows += 1
                previous_time = timestamp
    except (csv.Error, OverflowError, UnicodeError) as exc:
        raise ValueError(f"invalid or numerically out-of-range market CSV: {exc}") from exc
    if not rows:
        raise ValueError("market CSV contains no data rows")
    return {
        "family": "market_data", "synthetic": None, "kind": kind,
        "data_origin": "unverified_caller_input",
        "source": str(path), "dataset_fingerprint": fingerprint(path),
        "metrics": {"rows": rows, "first_time": first_time, "last_time": previous_time,
                    **({"observed_buy_volume": buy_volume, "observed_sell_volume": sell_volume}
                       if kind == "trades" else {})},
        "quality": {"validation": "all rows passed", "locked_snapshot_rows": locked,
                    "unknown_trade_side_rows": unknown_side},
        "feature_summaries": summary.columns, "feature_rows": list(features),
        "feature_rows_limit": FEATURE_ROW_LIMIT, "feature_rows_truncated": rows > FEATURE_ROW_LIMIT,
        "warnings": [
            "Caller-supplied CSV, not independently verified market or competition data.",
            "Features include the current completed observation; use them only after that observation is available.",
            "Numeric time units and reported trade-side semantics must be confirmed from the source.",
            "No own fills, L3 queue events, order-flow imbalance or trade signs are inferred from snapshots.",
            "Rolling signed flow is unavailable whenever a row in its window has no explicit side.",
        ],
    }
