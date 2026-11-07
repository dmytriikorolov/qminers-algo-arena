"""Rolling-window semantics and single global order reservation checks."""

from pathlib import Path
import tempfile
import unittest

from simulator.main import load_strategy_from_file
from simulator.models import BookOrderView, OrderBookSnapshot, Side
from simulator.simulator import ExchangeSimulator, SimulationConfig


def strategy_and_engine(**settings):
    strategy = load_strategy_from_file('strategies/window_maker.py')
    for key, value in settings.items():
        setattr(strategy, key, value)
    engine = ExchangeSimulator(strategy, SimulationConfig(
        max_position=100, max_potential_position=1000,
        position_breach_penalty_per_second=10000, order_accept_delay_ms=5))
    return strategy, engine


def snapshot(stamp, mid):
    return OrderBookSnapshot(stamp,
        [BookOrderView('bid', Side.BUY, mid - 1, 100, 'market')],
        [BookOrderView('ask', Side.SELL, mid + 1, 100, 'market')])


class WindowMakerTests(unittest.TestCase):
    def test_event_and_throttled_sampling_keep_different_three_point_windows(self):
        stamps = [0, 10000, 20000, 100000, 150000, 200000]
        mids = [100, 110, 120, 130, 140, 150]
        for sample_us, expected in [(0, [130, 140, 150]), (100000, [100, 130, 150])]:
            with self.subTest(sample_us=sample_us):
                strategy, _ = strategy_and_engine(WINDOW=3, SAMPLE_US=sample_us)
                for stamp, mid in zip(stamps, mids):
                    strategy.on_order_book_change(snapshot(stamp, mid), [])
                self.assertEqual(list(strategy.mids), expected)
                self.assertEqual(strategy.mid_sum, sum(expected))
                self.assertLessEqual(len(strategy.orders), 1)

    def test_throttled_sampling_does_not_invent_samples_across_empty_time(self):
        strategy, _ = strategy_and_engine(WINDOW=100, SAMPLE_US=100000)
        strategy.on_order_book_change(snapshot(0, 100), [])
        strategy.on_order_book_change(snapshot(1000000, 120), [])
        self.assertEqual(list(strategy.mids), [100, 120])
        self.assertEqual(strategy.sample_time, 1000000)
        self.assertFalse(strategy.orders)

    def test_missing_side_does_not_enter_or_add_a_midpoint(self):
        strategy, _ = strategy_and_engine(WINDOW=3)
        strategy.on_order_book_change(OrderBookSnapshot(0, [], []), [])
        self.assertEqual((len(strategy.mids), strategy.mid_sum, len(strategy.orders)), (0, 0, 0))

    def test_pending_cancel_blocks_replacement_and_partial_fill_reconciles(self):
        strategy, engine = strategy_and_engine(WINDOW=3, SAMPLE_US=0, REDUCE_FIRST=False, LOT=2, LIMIT=2)
        observations, submitted = {}, []
        original_public = strategy.on_order_book_change
        original_private = strategy.on_private_order_update
        original_submit = strategy._ctx.submit_order

        def check():
            self.assertLessEqual(len(strategy.orders), 1)
            self.assertLessEqual(abs(strategy.inventory), strategy.LIMIT)
            for sign in (1, -1):
                reserved = sum(state[2] for state in strategy.orders.values()
                               if (1 if state[0] == Side.BUY else -1) == sign)
                self.assertLessEqual(abs(strategy.inventory + sign * reserved), strategy.LIMIT)

        def public(book, trades):
            original_public(book, trades)
            check()
            observations[book.timestamp_us] = [list(state) for state in strategy.orders.values()]

        def private(event):
            original_private(event)
            check()

        def submit(request):
            submitted.append((engine.current_ts_us, request.quantity))
            return original_submit(request)

        strategy.on_order_book_change = public
        strategy.on_private_order_update = private
        strategy._ctx.submit_order = submit
        rows = [
            '0,Insert,bid,B,100,100,G', '0,Insert,ask,A,100,102,G',
            '0.001,Cancel,noop,,,,', '0.002,Cancel,noop,,,,',
            '0.003,Cancel,bid,,,,', '0.004,Cancel,ask,,,,',
            '0.005,Insert,bid2,B,1,98,G', '0.006,Insert,ask2,A,100,100,G',
            '0.007,Cancel,noop,,,,', '0.012,Cancel,noop,,,,',
            '0.013,Cancel,ask2,,,,', '0.014,Insert,ask3,A,100,104,G',
            '0.015,Cancel,ask3,,,,', '0.016,Insert,ask4,A,100,100,G',
            '0.016500,Insert,sweep,A,2,98,F', '0.020,Cancel,noop,,,,',
            '0.021,Insert,bid3,B,100,98,G', '0.030,Cancel,noop,,,,',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.csv'
            path.write_text('Time,Operation,OrderId,Side,Volume,Price,Lifespan\n'
                            + '\n'.join(rows) + '\n')
            result = engine.run(path)
        self.assertTrue(observations[16000][0][5])
        self.assertEqual(submitted, [(6000, 2), (21000, 1)])
        self.assertEqual((strategy.inventory, strategy.cash), (result.inventory, result.cash))
        self.assertEqual((result.inventory, result.cash, result.traded_volume), (1, -98, 1))
        self.assertEqual(result.breach_penalty, 0)


if __name__ == '__main__':
    unittest.main()
