"""Offline market features and a mock exchange; no competition API assumptions.

Prices/accounting use Decimal internally. Order quantities are integer units.
Cancellation acknowledgements are fill barriers: the adapter must deliver all
preceding fills before the acknowledgement. This is an explicit mock contract.
"""
from collections import deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import math
import random
import statistics


def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("expected a finite number") from None
    if not result.is_finite():
        raise ValueError("expected a finite number")
    return result


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def round_price(price, tick, side):
    """Round bids down and asks up; never accidentally make a quote aggressive."""
    price, tick = _decimal(price), _decimal(tick)
    if price <= 0 or tick <= 0 or side not in ("buy", "sell"):
        raise ValueError("positive price/tick and buy/sell required")
    rounding = ROUND_FLOOR if side == "buy" else ROUND_CEILING
    return (price / tick).to_integral_value(rounding=rounding) * tick


@dataclass(frozen=True)
class Snapshot:
    timestamp: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    def validate(self):
        for name in ("timestamp", "bid", "ask", "bid_size", "ask_size"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"non-finite {name}")
        if self.timestamp < 0 or self.bid <= 0 or self.ask < self.bid:
            raise ValueError("invalid timestamp or crossed/nonpositive book")
        if self.bid_size < 0 or self.ask_size < 0:
            raise ValueError("negative depth")
        if self.bid_size + self.ask_size <= 0:
            raise ValueError("empty book")
        if not math.isfinite(self.bid_size + self.ask_size):
            raise ValueError("depth sum overflow")
        return self

    @property
    def mid(self):
        return float((_decimal(self.bid) + _decimal(self.ask)) / 2)

    def features(self, tick=0.1):
        self.validate()
        if not math.isfinite(tick) or tick <= 0:
            raise ValueError("tick must be positive and finite")
        depth = self.bid_size + self.ask_size
        spread = self.ask - self.bid
        features = {
            "mid": self.mid,
            "spread": spread,
            "spread_ticks": spread / tick,
            "spread_bps": spread / self.mid * 10000,
            "imbalance": (self.bid_size - self.ask_size) / depth,
            "microprice": self.bid + spread * (self.bid_size / depth),
            "depth": depth,
            "locked": self.bid == self.ask,
        }
        if any(not math.isfinite(value) for value in features.values()):
            raise ValueError("derived snapshot feature overflows; check tick and input units")
        return features


class MarketFeatures:
    """Causal top-of-book features; snapshots do not reveal L3 queue events."""

    def __init__(self, window=20, max_age=2, tick=0.1):
        _positive_int(window, "window")
        if not math.isfinite(max_age) or max_age < 0:
            raise ValueError("max_age must be nonnegative and finite")
        self.window = window
        self.max_age = max_age
        self.tick = tick
        self.mids = deque(maxlen=window + 1)
        self.timestamp = None

    def update(self, snapshot, now=None):
        snapshot.validate()
        now = snapshot.timestamp if now is None else now
        if not math.isfinite(now) or now < snapshot.timestamp:
            raise ValueError("invalid clock or future snapshot")
        if now - snapshot.timestamp > self.max_age:
            raise ValueError("stale snapshot")
        if self.timestamp is not None and snapshot.timestamp <= self.timestamp:
            raise ValueError("duplicate or out-of-order snapshot")
        features = snapshot.features(self.tick)
        mids = list(self.mids) + [snapshot.mid]
        mids = mids[-self.window - 1:]
        returns = [math.log(b) - math.log(a) for a, b in zip(mids, mids[1:])]
        features.update({
            "rolling_mean": statistics.mean(mids),
            "return": returns[-1] if returns else 0.0,
            "volatility": statistics.pstdev(returns) if len(returns) > 1 else 0.0,
        })
        self.mids.append(snapshot.mid)
        self.timestamp = snapshot.timestamp
        return features


@dataclass
class Order:
    order_id: str
    side: str
    price: Decimal
    quantity: int
    timestamp: Decimal
    filled: int = 0
    state: str = "pending"

    @property
    def remaining(self):
        return self.quantity - self.filled


class Ledger:
    """Single-instrument position limits include every potentially live order.

    Pending and cancel-pending orders reserve their full remaining quantity.
    Opposite orders cannot offset each other for this calculation: either side
    may fill by itself. A cancel request releases nothing until acknowledged.
    """

    def __init__(self, position_limit=10, tick=0.1, lot=1):
        self.position_limit = _positive_int(position_limit, "position_limit")
        self.lot = _positive_int(lot, "lot")
        self.tick = _decimal(tick)
        if self.tick <= 0:
            raise ValueError("tick must be positive")
        self.orders = {}
        self.executions = {}
        self.position = 0
        self.cash = Decimal(0)
        self.fees = Decimal(0)
        self.average_price = Decimal(0)
        self.realized_gross = Decimal(0)

    def exposure(self):
        buy = sell = 0
        for order in self.orders.values():
            if order.state in ("pending", "active", "cancel_pending"):
                if order.side == "buy":
                    buy += order.remaining
                else:
                    sell += order.remaining
        return self.position + buy, self.position - sell

    def submit(self, order_id, side, price, quantity, timestamp):
        if not isinstance(order_id, str) or not order_id or order_id in self.orders:
            raise ValueError("order ID must be nonempty and unique")
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        _positive_int(quantity, "quantity")
        price, timestamp = _decimal(price), _decimal(timestamp)
        if price <= 0 or price % self.tick != 0 or quantity % self.lot:
            raise ValueError("invalid price tick or quantity lot")
        if timestamp < 0:
            raise ValueError("negative timestamp")
        for existing in self.orders.values():
            if existing.state not in ("pending", "active", "cancel_pending"):
                continue
            if ((side == "buy" and existing.side == "sell" and price >= existing.price)
                    or (side == "sell" and existing.side == "buy" and price <= existing.price)):
                raise ValueError("order would cross own potentially live order")
        long, short = self.exposure()
        if side == "buy":
            long += quantity
        else:
            short -= quantity
        if long > self.position_limit or short < -self.position_limit:
            raise ValueError("position limit including pending orders")
        order = Order(order_id, side, price, quantity, timestamp)
        self.orders[order_id] = order
        return order

    def acknowledge(self, order_id):
        order = self.orders[order_id]
        # A delayed acknowledgement must not revive a filled/cancelled order
        # or erase an already requested cancellation.
        if order.state == "pending":
            order.state = "active"

    def reject(self, order_id):
        order = self.orders[order_id]
        if order.filled or order.state not in ("pending", "cancel_pending", "rejected"):
            raise ValueError("only an unfilled pending order may be rejected")
        order.state = "rejected"

    def request_cancel(self, order_id):
        order = self.orders[order_id]
        if order.state in ("pending", "active"):
            order.state = "cancel_pending"

    def cancel_acknowledged(self, order_id):
        order = self.orders[order_id]
        if order.state == "cancel_pending":
            order.state = "cancelled" if order.remaining else "filled"
        elif order.state not in ("cancelled", "filled", "rejected"):
            raise ValueError("cancellation was not requested")

    def fill(self, execution_id, order_id, quantity, price, timestamp, fee=0):
        """Apply an incremental execution exactly once; reject conflicting IDs.

        Fill timestamps may arrive out of order, since different callbacks can
        be delayed. They must follow submission. Duplicate execution IDs are
        checked before terminal state, permitting safe replay of old callbacks.
        """
        if not isinstance(execution_id, str) or not execution_id:
            raise ValueError("nonempty execution ID required")
        _positive_int(quantity, "quantity")
        price, timestamp, fee = _decimal(price), _decimal(timestamp), _decimal(fee)
        event = (order_id, quantity, price, timestamp, fee)
        if execution_id in self.executions:
            if self.executions[execution_id] != event:
                raise ValueError("conflicting duplicate execution ID")
            return False
        order = self.orders[order_id]
        if order.state not in ("pending", "active", "cancel_pending"):
            raise ValueError("fill after terminal state; reconcile adapter event ordering")
        if quantity > order.remaining or quantity % self.lot:
            raise ValueError("overfill or invalid quantity lot")
        if price <= 0 or price % self.tick or timestamp < order.timestamp:
            raise ValueError("invalid execution price/time/fee")
        if ((order.side == "buy" and price > order.price)
                or (order.side == "sell" and price < order.price)):
            raise ValueError("execution violates limit price")
        signed = quantity if order.side == "buy" else -quantity
        old = self.position
        new = old + signed
        if abs(new) > self.position_limit:
            raise ValueError("fill breaches position limit")
        if old == 0 or old * signed > 0:
            self.average_price = ((self.average_price * abs(old) + price * quantity)
                                  / (abs(old) + quantity))
        else:
            closing = min(abs(old), quantity)
            self.realized_gross += closing * (price - self.average_price) * (1 if old > 0 else -1)
            if new == 0:
                self.average_price = Decimal(0)
            elif old * new < 0:
                self.average_price = price
        self.position = new
        self.cash -= signed * price + fee
        self.fees += fee
        order.filled += quantity
        if order.remaining == 0:
            order.state = "filled"
        self.executions[execution_id] = event
        return True

    def summary(self, mark):
        mark = _decimal(mark)
        if mark <= 0:
            raise ValueError("mark must be positive")
        unrealized = self.position * (mark - self.average_price)
        return {
            "cash": float(self.cash),
            "position": self.position,
            "fees": float(self.fees),
            "realized_pnl": float(self.realized_gross - self.fees),
            "unrealized_pnl": float(unrealized),
            "pnl": float(self.cash + self.position * mark),
            "fills": len(self.executions),
        }


STRATEGIES = ("no_op", "fixed", "fair_value", "inventory", "signal",
              "momentum", "mean_reversion", "taker", "guarded_fixed")


def mock_scenario(seed=7, steps=300, regime="mean_reverting"):
    """Generate identical exogenous snapshot/flow events for every strategy.

    Future aggressive flow is sampled independently of our orders. Each event
    consumes at most its stated volume. There is no inferred queue position.
    """
    _positive_int(steps, "steps")
    if steps > 100000:
        raise ValueError("mock demo is bounded at 100000 steps")
    if regime not in ("mean_reverting", "trend", "trend_down", "volatile", "shock"):
        raise ValueError("unknown mock regime")
    rng = random.Random(seed)
    mid = 100.0
    events = []
    for timestamp in range(steps + 1):
        drift = (0.03 * (100 - mid) if regime == "mean_reverting" else
                 -0.025 if regime == "trend_down" else 0.0 if regime == "volatile" else 0.025)
        if regime == "shock" and timestamp == steps // 2:
            drift += 4
        noise = 0.45 if regime == "volatile" else 0.15
        mid = max(10, round(mid + drift + rng.gauss(0, noise), 1))
        bid, ask = round(mid - 0.1, 1), round(mid + 0.1, 1)
        snapshot = Snapshot(timestamp, bid, ask, rng.randint(1, 12), rng.randint(1, 12))
        aggressor = rng.choice(("buy", "sell", "none"))
        trade_price = ask if aggressor == "buy" else bid
        events.append((snapshot, aggressor, trade_price, rng.randint(1, 3)))
    return events


def _quotes(strategy, snapshot, features, position, limit, fixed_mid):
    if strategy == "no_op":
        return []
    mid = snapshot.mid
    fair = features["rolling_mean"]
    if strategy == "fixed":
        center, half_spread = fixed_mid, 0.2
    elif strategy == "guarded_fixed":
        # Keep a fixed anchor only within one price unit of the current market.
        # A soft cap halves exposure; inventory skew encourages reducing it.
        limit = min(limit, 5)
        center = min(max(_decimal(fixed_mid), _decimal(mid) - 1), _decimal(mid) + 1) - Decimal("0.1") * position
        half_spread = 0.2
    elif strategy == "fair_value":
        center, half_spread = fair, 0.2
    elif strategy == "inventory":
        center, half_spread = _decimal(mid) - Decimal("0.05") * position, 0.2
    elif strategy == "signal":
        center = _decimal(features["microprice"]) - Decimal("0.04") * position
        half_spread = 0.2
    elif strategy in ("momentum", "mean_reversion", "taker"):
        if strategy == "momentum":
            edge = features["return"] * mid * 3
        else:
            edge = fair - mid
        threshold = 0.25 if strategy == "taker" else 0.15
        if edge > threshold and position < limit:
            return [("buy", snapshot.ask, 1)]
        if edge < -threshold and position > -limit:
            return [("sell", snapshot.bid, 1)]
        return []
    else:
        raise ValueError("unknown strategy")
    quotes = []
    if position < limit:
        quotes.append(("buy", max(0.1, float(round_price(_decimal(center) - _decimal(half_spread), 0.1, "buy"))),
                       min(2, limit - position)))
    if position > -limit:
        quotes.append(("sell", float(round_price(_decimal(center) + _decimal(half_spread), 0.1, "sell")),
                       min(2, limit + position)))
    return quotes


def replay(events, strategy="inventory", fee_per_unit=0.01, position_limit=10):
    """Mock event replay with one-event latency and incremental, volume-capped fills.

    Resting orders fill only when the next external trade crosses their limit.
    An aggressive quote fills at the next displayed executable price only if
    its limit still permits it. This is optimistic about queue priority and
    deliberately offers no evidence of real-market profitability.
    """
    fee = _decimal(fee_per_unit)
    if strategy not in STRATEGIES:
        raise ValueError("unknown strategy")
    if len(events) < 2:
        raise ValueError("at least two events required")
    ledger = Ledger(position_limit=position_limit)
    feature_engine = MarketFeatures()
    pending = []
    peak = drawdown = 0.0
    max_position = orders_sent = 0
    equity = []
    first_mid = events[0][0].mid
    for i, (snapshot, aggressor, trade_price, volume) in enumerate(events):
        if aggressor not in ("buy", "sell", "none"):
            raise ValueError("invalid mock trade side")
        _positive_int(volume, "volume")
        if not math.isfinite(trade_price) or trade_price <= 0:
            raise ValueError("invalid mock trade price")
        features = feature_engine.update(snapshot)
        remaining_volume = volume
        for order_id, aggressive in pending:
            order = ledger.orders[order_id]
            execution_price = None
            executable_size = remaining_volume
            if aggressive:
                if order.side == "buy" and order.price >= _decimal(snapshot.ask):
                    execution_price = snapshot.ask
                    executable_size = min(executable_size, int(snapshot.ask_size))
                elif order.side == "sell" and order.price <= _decimal(snapshot.bid):
                    execution_price = snapshot.bid
                    executable_size = min(executable_size, int(snapshot.bid_size))
            elif ((order.side == "buy" and aggressor == "sell" and order.price >= _decimal(trade_price))
                  or (order.side == "sell" and aggressor == "buy" and order.price <= _decimal(trade_price))):
                # Passive fills execute at our resting quote; all available
                # flow is assigned to us (no fabricated queue estimate).
                execution_price = order.price
            if execution_price is not None and executable_size > 0:
                quantity = min(order.remaining, executable_size)
                ledger.fill(f"fill-{i}-{order_id}", order_id, quantity, execution_price,
                            snapshot.timestamp, quantity * fee)
                remaining_volume -= quantity
            ledger.request_cancel(order_id)
            ledger.cancel_acknowledged(order_id)
        pending = []
        result = ledger.summary(snapshot.mid)
        equity.append({"time": snapshot.timestamp, "pnl": result["pnl"], "position": ledger.position})
        peak = max(peak, result["pnl"])
        drawdown = max(drawdown, peak - result["pnl"])
        max_position = max(max_position, abs(ledger.position))
        if i == len(events) - 1:
            continue
        for j, (side, price, quantity) in enumerate(
                _quotes(strategy, snapshot, features, ledger.position, position_limit, first_mid)):
            order_id = f"{i}-{j}"
            ledger.submit(order_id, side, price, quantity, snapshot.timestamp)
            ledger.acknowledge(order_id)
            aggressive = ((side == "buy" and price >= snapshot.ask)
                          or (side == "sell" and price <= snapshot.bid))
            pending.append((order_id, aggressive))
            orders_sent += 1
    result = ledger.summary(events[-1][0].mid)
    result.update({"strategy": strategy, "max_drawdown": drawdown,
                   "max_abs_position": max_position, "orders": orders_sent,
                   "fill_rate": result["fills"] / orders_sent if orders_sent else 0.0,
                   "equity": equity})
    return result


def demo(seed=7, steps=300, fee_per_unit=0.01, position_limit=10,
         regime="mean_reverting", **config):
    if config:
        raise ValueError(f"unknown market options: {sorted(config)}")
    events = mock_scenario(seed=seed, steps=steps, regime=regime)
    comparison = [replay(events, strategy, fee_per_unit, position_limit) for strategy in STRATEGIES]
    best = max(comparison, key=lambda row: row["pnl"])
    serializable_events = [[vars(snapshot), side, price, volume]
                           for snapshot, side, price, volume in events]
    return {
        "family": "market", "synthetic": True, "seed": seed,
        "dataset_fingerprint": hashlib.sha256(json.dumps(serializable_events, sort_keys=True).encode()).hexdigest(),
        "metrics": {"best_strategy": best["strategy"], "best_pnl": best["pnl"],
                    "steps": steps, "strategies": len(comparison)},
        "comparison": comparison,
        "assumptions": [
            "Synthetic single-instrument mock exchange; not Qminers scoring or live evidence.",
            "All strategies receive identical exogenous snapshots and aggressive trade flow.",
            "One-event order latency; quotes cancelled after one event; partial fills capped by event volume.",
            "Passive fills assume front-of-queue priority; no real queue information is available.",
            "Final inventory is marked to mid; liquidation spread/cost is not included.",
            "Cancellation acknowledgements are fill barriers; actual API ordering must be reconciled.",
            "Best strategy is selected on this scenario, not an untouched evaluation set.",
        ],
    }
