"""Independent official-engine scenarios; run with unittest discovery."""

from pathlib import Path
import random
import tempfile
import unittest

from simulator.main import load_strategy_from_file
from simulator.models import OrderStatus
from simulator.simulator import ExchangeSimulator, SimulationConfig


class PlaygroundReviewTests(unittest.TestCase):
    def replay(self, name, rows, **settings):
        strategy = load_strategy_from_file(Path('strategies') / f'{name}.py')
        for key, value in settings.items():
            setattr(strategy, key, value)
        events = []
        update = strategy.on_private_order_update
        public = strategy.on_order_book_change

        def observe(event):
            events.append(event)
            update(event)
            self.assertLessEqual(abs(strategy.inventory), strategy.LIMIT)

        def check_reservations(snapshot, trades):
            public(snapshot, trades)
            if name == 'playground_quotes':
                for sign in (1, -1):
                    reserved = sum(state[2] for state in strategy.orders.values()
                                   if (1 if state[0].value == 'B' else -1) == sign)
                    self.assertLessEqual(abs(strategy.inventory + sign * reserved), strategy.LIMIT)

        strategy.on_private_order_update = observe
        strategy.on_order_book_change = check_reservations
        engine = ExchangeSimulator(strategy, SimulationConfig(
            max_position=100, max_potential_position=1000,
            position_breach_penalty_per_second=10_000, order_accept_delay_ms=5))
        with tempfile.TemporaryDirectory() as directory:
            tape = Path(directory) / 'tape.csv'
            tape.write_text('Time,Operation,OrderId,Side,Volume,Price,Lifespan\n'
                            + '\n'.join(rows) + '\n')
            result = engine.run(tape)
        self.assertEqual(strategy.inventory, result.inventory)
        self.assertEqual(result.breach_penalty, 0)
        return strategy, engine, result, events

    def test_ioc_miss_retries_after_terminal_cancel(self):
        _, engine, result, events = self.replay('playground_flow', [
            '0,Insert,b0,B,100,99,G', '0,Insert,a0,A,100,101,G',
            '0.001,Insert,t0,B,1,101,F', '0.002,Cancel,a0,,,,',
            '0.003,Insert,a1,A,100,102,G', '0.010,Insert,t1,A,1,99,F',
            '0.020,Cancel,unknown,,,,'])
        self.assertEqual(engine._user_order_seq, 2)
        self.assertGreater(result.traded_volume, 0)
        self.assertTrue(any(e.order_id == 'u000000001' and e.status == OrderStatus.CANCELED
                            for e in events))

    def test_partial_ioc_then_cancel_accounts_only_actual_fill(self):
        strategy, _, result, events = self.replay('playground_flow', [
            '0,Insert,b0,B,100,100,G', '0,Insert,a0,A,3,102,G',
            '0.001,Insert,t0,B,1,102,F', '0.010,Cancel,unknown,,,,'], LOT=20)
        first = [e for e in events if e.order_id == 'u000000001']
        self.assertEqual([e.status for e in first], [OrderStatus.ACCEPTED,
                         OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELED])
        self.assertEqual(first[1].filled_quantity, 2)
        self.assertEqual(first[2].remaining_quantity, 18)
        self.assertEqual(result.inventory, 2)
        self.assertIsNone(strategy.order_id)

    def test_quote_cancel_fill_race_does_not_resurrect_order(self):
        strategy, _, result, events = self.replay('playground_quotes', [
            '0,Insert,b0,B,1,100,G', '0,Insert,a0,A,100,102,G',
            '0.006,Cancel,a0,,,,', '0.007,Insert,sweep,A,3,100,F',
            '0.020,Cancel,unknown,,,,'], SIGNAL_WEIGHT=0, SKEW=0, VOL_WEIGHT=0)
        first = [e.status for e in events if e.order_id == 'u000000001']
        self.assertEqual(first, [OrderStatus.ACCEPTED, OrderStatus.FILLED, OrderStatus.REJECTED])
        self.assertNotIn('u000000001', strategy.orders)
        self.assertEqual(result.inventory, 2)

    def test_pending_quotes_reserve_capacity_before_acceptance(self):
        _, engine, result, _ = self.replay('playground_quotes', [
            '0,Insert,b0,B,1,100,G', '0,Insert,a0,A,10,102,G',
            '0.001,Cancel,unknown1,,,,', '0.002,Cancel,unknown2,,,,',
            '0.003,Cancel,unknown3,,,,', '0.004,Cancel,unknown4,,,,',
            '0.006,Insert,sweep,A,3,100,F'], LOT=20, LIMIT=2,
            SIGNAL_WEIGHT=0, SKEW=0, VOL_WEIGHT=0)
        self.assertEqual(engine._user_order_seq, 2)
        self.assertEqual(result.inventory, 2)

    def test_sparse_tape_fills_at_ready_time_before_next_market_event(self):
        _, _, result, events = self.replay('playground_flow', [
            '0,Insert,b0,B,100,100,G', '0,Insert,a0,A,100,102,G',
            '0.001,Insert,t0,B,1,102,F', '1.0,Cancel,a0,,,,'], LOT=1)
        fills = [e for e in events if e.filled_quantity]
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].timestamp_us, 6000)
        self.assertEqual(result.inventory, 1)

    def test_bounded_random_tapes_reconcile_inventory_and_reservations(self):
        for seed in range(4):
            rng = random.Random(seed)
            rows = ['0,Insert,b0,B,5,10000,G', '0,Insert,a0,A,5,10003,G']
            ids = {'B': 'b0', 'A': 'a0'}
            now, bid, ask = 0, 10000, 10003
            for index in range(400):
                now += rng.choice([0, 1000, 3000, 10000, 50000])
                stamp, side = f'{now / 1e6:.6f}', rng.choice(['A', 'B'])
                if rng.random() < 0.45:
                    rows.append(f'{stamp},Cancel,{ids[side]},,,,')
                    ids[side] = f'r{index}'
                    bid += rng.choice([-2, -1, 0, 1, 2])
                    ask = bid + rng.choice([1, 2, 3, 5, 10])
                    price = bid if side == 'B' else ask
                    rows.append(f'{stamp},Insert,{ids[side]},{side},{rng.choice([1, 2, 5, 20])},{price},G')
                else:
                    price = ask + 5 if side == 'B' else bid - 5
                    rows.append(f'{stamp},Insert,t{index},{side},{rng.choice([1, 3, 8])},{price},F')
            for name, lot in [('playground_flow', 20), ('playground_quotes', 10)]:
                with self.subTest(seed=seed, strategy=name):
                    self.replay(name, rows, LOT=lot, LIMIT=20)


if __name__ == '__main__':
    unittest.main()
