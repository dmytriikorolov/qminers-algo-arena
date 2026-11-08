"""Reproducible public-tape experiments; always use official scoring rules."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import math
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulator.models import Side
from simulator.simulator import ExchangeSimulator, SimulationConfig
from strategies import baseline

BASELINE_SHA256 = hashlib.sha256(Path(baseline.__file__).read_bytes()).hexdigest()
RESEARCH_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class ResearchMaker(baseline.AdaptiveMakerMLStrategy):
    def __init__(self, *, exit_improve=False, pressure=0.0, fade=0.0,
                 strict=False, quote_size=200, inventory_skew=False,
                 online=0.0, hysteresis=0, fade_cap=40, fade_risk=2.0, **kwargs):
        super().__init__(**kwargs)
        self.exit_improve = exit_improve
        self.pressure = pressure
        self.fade = fade
        self.strict = strict
        self.quote_size = quote_size
        self.inventory_skew = inventory_skew
        self.center = 0
        self.online = online
        self.hysteresis = hysteresis
        self.fade_cap = fade_cap
        self.fade_risk = fade_risk
        self.samples = deque()
        self.weights = list(self._vw) + [self._vb]
        self.covariance = [[float(i == j) / max(1.0, online)
                            for j in range(len(self.weights))]
                           for i in range(len(self.weights))]

    def _forecast(self):
        if not self.online:
            return super()._forecast()
        hist = self._hist
        def mean(col, n):
            rows = hist[-n:]
            return sum(row[col] for row in rows) / len(rows)
        def realized(n):
            rows = hist[-n:]
            return math.sqrt(sum(row[0] ** 2 for row in rows) / len(rows))
        features = [realized(n) for n in (5, 10, 30, 120)] + [self._ewm10 ** 0.5]
        for col in range(1, 8):
            features.extend((mean(col, 5), mean(col, 60)))
        features.extend((abs(hist[-1][0]), max(abs(row[0]) for row in hist[-60:])))
        for col in range(1, 8):
            features.extend((hist[-1][col], mean(col, 2)))
        features.append(realized(2))
        x = [math.log1p(max(0.0, value)) for value in features] + [1.0]
        if len(self.samples) >= 10:
            previous = self.samples.popleft()
            target = math.log1p(realized(10))
            projected = [sum(a * b for a, b in zip(row, previous)) for row in self.covariance]
            denominator = 0.9995 + sum(a * b for a, b in zip(previous, projected))
            gain = [value / denominator for value in projected]
            error = target - sum(a * b for a, b in zip(self.weights, previous))
            error = max(-1.5, min(1.5, error))
            for i, row in enumerate(self.covariance):
                self.weights[i] += gain[i] * error
                for j in range(len(row)):
                    row[j] = (row[j] - gain[i] * projected[j]) / 0.9995
        self.samples.append(x)
        return math.expm1(max(0.0, min(10.0, sum(a * b for a, b in zip(self.weights, x)))))

    def _update_volatility(self, *args):
        super()._update_volatility(*args)
        if self.fade and len(self._hist) >= 30:
            move = sum(row[0] for row in self._hist[-30:])
            # A bounded passive target, with less conviction during turbulence.
            self.center = round(max(-self.fade_cap, min(self.fade_cap, -self.fade * move))
                                * min(1.0, self.fade_risk / max(0.1, self.last_forecast)))

    def _quote_targets(self, side, bid, ask, own_imb, limit, vacuum):
        inventory = self._inventory
        if self.fade:
            self._inventory -= self.center
        try:
            touch, want = super()._quote_targets(side, bid, ask, own_imb, limit, vacuum)
        finally:
            self._inventory = inventory
        sign = 1 if side == Side.BUY else -1
        remaining = min(self.quote_size, max(0, self._limit - sign * inventory))
        targets = {}
        for price, quantity in want.items():
            quantity = min(quantity, remaining)
            remaining -= quantity
            if quantity <= 0:
                continue
            if self.pressure and own_imb < -self.pressure:
                price -= sign
            if self.inventory_skew and sign * inventory > 40:
                price -= sign
            if self.exit_improve and sign * inventory < -20 and ask - bid >= 2:
                flatten = min(quantity, abs(inventory))
                improved = min(ask - 1, bid + 1) if sign == 1 else max(bid + 1, ask - 1)
                targets[improved] = targets.get(improved, 0) + flatten
                quantity -= flatten
            if quantity:
                targets[price] = targets.get(price, 0) + quantity
        return touch, targets

    def _reconcile(self, side, touch, want):
        sign = 1 if side == Side.BUY else -1
        if self.hysteresis and sign * self._inventory >= 0:
            targets = {}
            for price, quantity in want.items():
                candidates = [o[1] for o in self._orders.values()
                              if o[0] == side and not o[3]
                              and 0 <= sign * (price - o[1]) <= self.hysteresis]
                if candidates:
                    price = max(candidates) if sign == 1 else min(candidates)
                targets[price] = targets.get(price, 0) + quantity
            want = targets
        if self.strict:
            # Disable early release of pending cancels by choosing the least
            # aggressive price of all outstanding orders on this side.
            prices = [o[1] for o in self._orders.values() if o[0] == side]
            if prices:
                touch = min(prices + [touch]) if side == Side.BUY else max(prices + [touch])
        super()._reconcile(side, touch, want)


VARIANTS = {
    'baseline': {},
    'ramp': {'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'inside': {'vacuum_spread': 2, 'volatility_quotes': False},
    'exit': {'exit_improve': True, 'forecast_lo': 1.6, 'forecast_hi': 2.6},
    'pressure': {'pressure': 0.6, 'forecast_lo': 1.6, 'forecast_hi': 2.6},
    'fade': {'fade': 3.0, 'forecast_lo': 1.6, 'forecast_hi': 2.6},
    'simple': {'forecast_lo': 1.6, 'forecast_hi': 2.6, 'volatility_quotes': False,
               'shock_cooldown_ms': 0},
    'inside_ramp': {'vacuum_spread': 2, 'volatility_quotes': False,
                    'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'clip40': {'quote_size': 40, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'clip80': {'quote_size': 80, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'skew': {'inventory_skew': True, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'online50': {'online': 50.0, 'forecast_lo': 1.6, 'forecast_hi': 2.6},
    'online500': {'online': 500.0, 'forecast_lo': 1.6, 'forecast_hi': 2.6},
    'fade_ramp': {'fade': 3.0, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'fade_large': {'fade': 8.0, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'broad_ramp': {'forecast_lo': 2.5, 'forecast_hi': 4.0},
    'ungated': {'imb_gate': None, 'flip_gate': None, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'queue1': {'hysteresis': 1, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'queue2': {'hysteresis': 2, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'queue5': {'hysteresis': 5, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'fade_strict': {'fade': 8.0, 'strict': True, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'fade_capacity': {'fade': 8.0, 'fade_cap': 80, 'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'fade_risk': {'fade': 8.0, 'fade_cap': 80, 'fade_risk': 4.0,
                  'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'fade_full': {'fade': 20.0, 'fade_cap': 100, 'fade_risk': 10.0,
                  'forecast_lo': 2.0, 'forecast_hi': 3.0},
    'fade_full_capped': {'fade': 20.0, 'fade_cap': 100, 'fade_risk': 4.0,
                         'forecast_lo': 2.0, 'forecast_hi': 3.0},
}


def run(job):
    name, tape = job
    started = time.monotonic()
    strategy = ResearchMaker(**VARIANTS[name])
    config = SimulationConfig(order_accept_delay_ms=5, max_position=100,
                              max_potential_position=1000,
                              position_breach_penalty_per_second=10000)
    engine = ExchangeSimulator(strategy, config)
    result = engine.run(ROOT / 'data' / f'{tape}.csv')
    points = engine.pnl_curve(result.pnl)
    split = (points[0][0] + points[-1][0]) / 2
    first = next(p for t, p in reversed(points) if t <= split)
    peak = drawdown = 0.0
    for _, pnl in points:
        peak = max(peak, pnl)
        drawdown = max(drawdown, peak - pnl)
    record = dict(result.model_dump(), variant=name, parameters=VARIANTS[name],
                  tape=tape, first_half=first, second_half=result.pnl - first,
                  max_drawdown=drawdown, max_abs_inventory=strategy.max_abs_inventory,
                  elapsed_seconds=round(time.monotonic() - started, 1),
                  strategy_sha256=BASELINE_SHA256,
                  research_sha256=RESEARCH_SHA256,
                  config=config.model_dump(mode='json'))
    out = ROOT / 'logs' / 'round3_final' / f'{tape}_{name}'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    with (out / 'pnl.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_us', 'pnl'])
        writer.writerows(points)
    print(json.dumps({key: record[key] for key in ('variant', 'tape', 'pnl', 'first_half',
          'second_half', 'max_drawdown', 'breach_penalty', 'elapsed_seconds')}), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variants', nargs='+', choices=VARIANTS)
    parser.add_argument('--tape', default='round3_public', choices=['round3_public', 'round2_public', 'round1'])
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, [(name, args.tape) for name in args.variants]))
