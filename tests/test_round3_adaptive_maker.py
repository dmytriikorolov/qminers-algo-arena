"""Execution invariants and causal signal checks for the standalone strategy."""
import gzip
import math
import tempfile
import unittest
from pathlib import Path

from simulator.main import load_strategy_from_file
from simulator.models import OrderStatus, OrderType, PrivateOrderEvent, Side
from simulator.strategy import StrategyContext
from simulator.simulator import ExchangeSimulator, SimulationConfig
from strategies.baseline import AdaptiveMakerMLStrategy
from strategies.round3_adaptive_maker import Round3AdaptiveMaker


class Round3MakerTests(unittest.TestCase):
    def attach(self, strategy):
        self.sent = []
        self.canceled = []
        self.modified = []

        def submit(order):
            self.sent.append(order)
            return f'order-{len(self.sent)}'

        strategy._attach_context(StrategyContext(
            submit, self.canceled.append,
            lambda oid, qty: self.modified.append((oid, qty)), lambda: 5000,
        ))
        return strategy

    def test_standalone_loader(self):
        path = Path(__file__).resolve().parents[1] / 'strategies/round3_adaptive_maker.py'
        strategy = load_strategy_from_file(path)
        self.assertEqual(type(strategy).__name__, 'Round3AdaptiveMaker')

    def test_center_needs_thirty_completed_seconds(self):
        strategy = Round3AdaptiveMaker(fade_strength=20.0, fade_limit=100, fade_risk=10.0)
        strategy._hist = [(1.0,)] * 29
        strategy._update_center()
        self.assertEqual(strategy._center, 0)
        strategy._hist.append((1.0,))
        strategy._update_center()
        self.assertEqual(strategy._center, -100)
        strategy.last_forecast = 20.0
        strategy._update_center()
        self.assertEqual(strategy._center, -50)
        strategy._hist = [(-1.0,)] * 30
        strategy._update_center()
        self.assertEqual(strategy._center, 50)

    def test_target_sizes_obey_physical_inventory_limit(self):
        strategy = Round3AdaptiveMaker()
        for inventory in (-100, -40, 0, 40, 100):
            strategy._inventory = inventory
            for center in (-100, 0, 100):
                strategy._center = center
                for effective_limit in (0, 50, 100):
                    for forecast in (0.0, 2.5, 8.0):
                        strategy.last_forecast = forecast
                        for side, sign in ((Side.BUY, 1), (Side.SELL, -1)):
                            for imbalance in (-1.0, 0.0, 1.0):
                                _, targets = strategy._quote_targets(
                                    side, 100, 104, imbalance, effective_limit, True)
                                self.assertLessEqual(sum(targets.values()), 100 - sign * inventory)
                                for price, quantity in targets.items():
                                    self.assertGreater(quantity, 0)
                                    self.assertIsInstance(quantity, int)
                                    self.assertGreater(price, 0)
                                    self.assertTrue(price < 104 if sign == 1 else price > 100)

    def test_strict_cancel_keeps_in_flight_exposure_reserved(self):
        strategy = self.attach(Round3AdaptiveMaker(strict_exposure=True))
        strategy._reconcile(Side.BUY, 100, {100: 100})
        strategy._reconcile(Side.BUY, 101, {101: 100})
        self.assertEqual(self.canceled, ['order-1'])
        self.assertEqual(len(self.sent), 1)
        strategy.on_private_order_update(PrivateOrderEvent(
            timestamp_us=5000, order_id='order-1', status=OrderStatus.CANCELED,
            remaining_quantity=0,
        ))
        strategy._reconcile(Side.BUY, 101, {101: 100})
        self.assertEqual(len(self.sent), 2)

    def test_pending_quantity_reduction_does_not_release_capacity_early(self):
        strategy = self.attach(Round3AdaptiveMaker(strict_exposure=True))
        strategy._reconcile(Side.BUY, 100, {100: 100})
        strategy._reconcile(Side.BUY, 100, {100: 40, 99: 60})
        self.assertEqual(self.modified, [('order-1', 40)])
        self.assertEqual(len(self.sent), 1)
        strategy.on_private_order_update(PrivateOrderEvent(
            timestamp_us=5000, order_id='order-1', status=OrderStatus.MODIFIED,
            remaining_quantity=40,
        ))
        strategy._reconcile(Side.BUY, 100, {100: 40, 99: 60})
        self.assertEqual(self.sent[-1].quantity, 60)

    def test_fast_cancel_race_sends_rescue_for_actual_excess(self):
        strategy = self.attach(Round3AdaptiveMaker())
        strategy._best = (100, 101)
        strategy._reconcile(Side.BUY, 100, {100: 100})
        strategy._reconcile(Side.BUY, 101, {101: 100})
        for order_id in ('order-1', 'order-2'):
            strategy.on_private_order_update(PrivateOrderEvent(
                timestamp_us=5000, order_id=order_id, status=OrderStatus.FILLED,
                filled_quantity=100, remaining_quantity=0, fill_price=100,
            ))
        self.assertEqual(strategy._inventory, 200)
        self.assertEqual(self.sent[-1].order_type, OrderType.IOC)
        self.assertEqual(self.sent[-1].side, Side.SELL)
        self.assertEqual(self.sent[-1].quantity, 100)
        strategy.on_private_order_update(PrivateOrderEvent(
            timestamp_us=10000, order_id='order-3', status=OrderStatus.FILLED,
            filled_quantity=100, remaining_quantity=0, fill_price=98,
        ))
        self.assertEqual(strategy._inventory, 100)
        self.assertFalse(strategy._iocs)

    def test_race_excess_does_not_enlarge_passive_quote_beyond_full_flip(self):
        strategy = Round3AdaptiveMaker()
        strategy._inventory = 160
        _, targets = strategy._quote_targets(Side.SELL, 100, 101, 0, 100, False)
        self.assertLessEqual(sum(targets.values()), 200)

    def test_invalid_fade_parameters(self):
        for params in ({'fade_strength': -1}, {'fade_strength': math.nan},
                       {'fade_limit': 101}, {'fade_limit': -1},
                       {'fade_risk': 0}, {'fade_risk': math.inf}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                Round3AdaptiveMaker(**params)

    def test_disabling_new_signal_reproduces_baseline_on_sample_tape(self):
        fixture = Path(__file__).resolve().parents[1] / 'data/sample.csv.gz'
        config = SimulationConfig(order_accept_delay_ms=5, max_position=100,
                                  max_potential_position=1000,
                                  position_breach_penalty_per_second=10000)
        candidate = Round3AdaptiveMaker(fade_strength=0, forecast_lo=1.4, forecast_hi=2.2)
        with tempfile.TemporaryDirectory() as directory:
            tape = Path(directory) / 'sample.csv'
            tape.write_bytes(gzip.decompress(fixture.read_bytes()))
            original = ExchangeSimulator(AdaptiveMakerMLStrategy(), config).run(tape)
            actual = ExchangeSimulator(candidate, config).run(tape)
        self.assertEqual(actual.model_dump(), original.model_dump())


if __name__ == '__main__':
    unittest.main()
