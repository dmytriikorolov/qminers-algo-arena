"""Small adversarial tapes against the untouched official matching engine."""

from pathlib import Path
import tempfile
import unittest

from simulator.main import load_strategy_from_file
from simulator.simulator import ExchangeSimulator, SimulationConfig


ENTRY = [
    '0,Insert,bid,B,10000,100,G', '0,Insert,ask,A,10000,102,G',
    '0.001,Insert,buy,B,1,102,F', '0.008,Cancel,noop,,,,',
]
REVERSAL = ENTRY + [
    '0.010,Cancel,bid,,,,', '0.011,Insert,lowbid,B,10000,90,G',
    '0.012,Cancel,ask,,,,', '0.013,Insert,lowask,A,10000,92,G',
    '10,Cancel,noop,,,,',
]
MISSING_LIQUIDITY = ENTRY + [
    '0.010,Cancel,bid,,,,', '0.011,Cancel,ask,,,,',
    '1,Cancel,noop,,,,', '2,Insert,lowbid1,B,1,40,G',
    '2.020,Cancel,lowbid1,,,,', '3,Insert,lowbid2,B,10000,35,G',
    '3.020,Cancel,noop,,,,', '10,Cancel,noop,,,,',
]
CHURN = ['0,Insert,bid,B,100000,100,G', '0,Insert,ask,A,100000,102,G'] + [
    f'{(index * 20000 + 1000) / 1e6:.6f},Insert,t{index},'
    f'{"B" if index % 2 == 0 else "A"},1,{102 if index % 2 == 0 else 100},F'
    for index in range(100)
] + ['3,Cancel,noop,,,,']


def replay(strategy_file, rows, **settings):
    strategy = load_strategy_from_file(Path('strategies') / strategy_file)
    for key, value in settings.items():
        setattr(strategy, key, value)
    updates, snapshots = [], []
    original_update = strategy.on_private_order_update
    original_book = strategy.on_order_book_change

    def observe_update(event):
        original_update(event)
        updates.append((event, strategy.inventory))

    def observe_book(snapshot, trades):
        original_book(snapshot, trades)
        snapshots.append((snapshot.timestamp_us, strategy.inventory))

    strategy.on_private_order_update = observe_update
    strategy.on_order_book_change = observe_book
    engine = ExchangeSimulator(strategy, SimulationConfig(
        max_position=100, max_potential_position=1000,
        position_breach_penalty_per_second=10_000, order_accept_delay_ms=5))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'tape.csv'
        path.write_text('Time,Operation,OrderId,Side,Volume,Price,Lifespan\n'
                        + '\n'.join(rows) + '\n')
        result = engine.run(path)
    return strategy, engine, result, updates, snapshots


class OriginalFlowAdversarialTests(unittest.TestCase):
    def test_original_holds_reversal_without_opposite_flow(self):
        _, engine, result, _, _ = replay('playground_flow.py', REVERSAL)
        self.assertEqual((result.pnl, result.inventory, result.traded_volume), (-240, 20, 20))
        self.assertEqual(engine._user_order_seq, 1)

    def test_original_holds_through_missing_and_thin_liquidity(self):
        _, engine, result, _, _ = replay('playground_flow.py', MISSING_LIQUIDITY)
        self.assertEqual((result.pnl, result.inventory, result.traded_volume), (-1340, 20, 20))
        self.assertEqual(engine._user_order_seq, 1)

    def test_original_churns_on_alternating_market_trades(self):
        _, engine, result, _, _ = replay('playground_flow.py', CHURN)
        self.assertEqual((result.pnl, result.inventory, result.traded_volume), (-2000, 0, 2000))
        self.assertEqual(engine._user_order_seq, 100)


# Entry confirmation uses only past book changes: +1 mid tick after 100 ms.
CONFIRMED_ENTRY = ENTRY + [
    '0.050,Cancel,ask,,,,', '0.051,Insert,ask2,A,10000,104,G',
    '0.110,Cancel,noop,,,,', '0.120,Insert,bid2,B,10000,102,G',
    '0.121,Cancel,bid,,,,',
]
CONFIRMED_REVERSAL = CONFIRMED_ENTRY + [
    '0.200,Cancel,bid2,,,,', '0.202,Insert,lowbid,B,10000,90,G',
    '0.220,Cancel,noop,,,,', '10,Cancel,noop,,,,',
]


def mirror(rows):
    result = []
    for row in rows:
        fields = row.split(',')
        if fields[1] == 'Insert':
            fields[3] = 'A' if fields[3] == 'B' else 'B'
            fields[5] = str(202 - int(fields[5]))
        result.append(','.join(fields))
    return result


class DefensiveFlowAdversarialTests(unittest.TestCase):
    def check_reconciliation(self, strategy, result, updates):
        self.assertEqual(strategy.inventory, result.inventory)
        self.assertEqual(strategy.cash, result.cash)
        self.assertEqual(result.breach_penalty, 0)
        self.assertTrue(all(abs(inventory) <= strategy.LIMIT for _, inventory in updates))
        for event, _ in updates:
            if event.filled_quantity:
                self.assertGreaterEqual(event.timestamp_us, 115000)

    def test_confirmed_entry_exits_reversal_without_opposite_flow(self):
        strategy, _, result, updates, _ = replay('defensive_flow.py', CONFIRMED_REVERSAL)
        self.check_reconciliation(strategy, result, updates)
        self.assertEqual((result.inventory, result.traded_volume, result.pnl), (0, 4, -28))
        # Stop triggers after a gap; its threshold is not a guaranteed loss cap.
        self.assertLess(result.pnl, -strategy.MAX_TRADE_LOSS)
        self.assertIsNone(strategy.holding_since)

    def test_short_exit_is_symmetric(self):
        strategy, _, result, updates, _ = replay('defensive_flow.py', mirror(CONFIRMED_REVERSAL))
        self.check_reconciliation(strategy, result, updates)
        self.assertEqual((result.inventory, result.traded_volume, result.pnl), (0, 4, -28))
        fills = [event for event, _ in updates if event.filled_quantity]
        self.assertEqual([event.fill_price for event in fills], [98, 112])

    def test_timeout_starts_at_actual_fill_and_ignores_entry_flow(self):
        rows = CONFIRMED_ENTRY + ['5.114,Cancel,noop,,,,', '5.115,Cancel,noop,,,,',
                                  '5.200,Cancel,noop,,,,']
        strategy, _, result, updates, snapshots = replay('defensive_flow.py', rows)
        self.check_reconciliation(strategy, result, updates)
        self.assertEqual(dict(snapshots)[5114000], 2)
        fills = [event for event, _ in updates if event.filled_quantity]
        self.assertEqual([event.timestamp_us for event in fills], [115000, 5120000])
        self.assertEqual((result.inventory, result.pnl), (0, -4))

    def test_missing_book_cannot_fill_stop_and_thin_return_only_partially_exits(self):
        rows = CONFIRMED_ENTRY + [
            '0.200,Cancel,bid2,,,,', '0.201,Cancel,ask2,,,,',
            '1,Cancel,noop,,,,', '5.200,Cancel,noop,,,,',
            '6,Insert,thinbid,B,1,40,G', '6.020,Cancel,thinbid,,,,',
            '7,Insert,deepbid,B,10000,35,G', '7.020,Cancel,noop,,,,',
        ]
        strategy, _, result, updates, snapshots = replay('defensive_flow.py', rows)
        self.check_reconciliation(strategy, result, updates)
        self.assertEqual(dict(snapshots)[5200000], 2)
        self.assertEqual(dict(snapshots)[6020000], 1)
        fills = [event for event, _ in updates if event.filled_quantity]
        self.assertEqual([event.filled_quantity for event in fills], [2, 1, 1])
        self.assertEqual((result.inventory, result.pnl), (0, -133))
        self.assertTrue(strategy.halted)

    def test_drawdown_halt_blocks_later_confirmed_signal_when_flat(self):
        rows = CONFIRMED_REVERSAL[:-1] + [
            '2,Insert,newask,A,10000,92,G', '2.001,Insert,newbuy,B,1,92,F',
            '2.050,Cancel,newask,,,,', '2.051,Insert,newask2,A,10000,94,G',
            '2.110,Cancel,noop,,,,', '3,Cancel,noop,,,,',
        ]
        strategy, engine, result, updates, _ = replay('defensive_flow.py', rows, MAX_DRAWDOWN=20)
        self.check_reconciliation(strategy, result, updates)
        self.assertTrue(strategy.halted)
        self.assertEqual((engine._user_order_seq, result.inventory, result.pnl), (2, 0, -28))

    def test_cooldown_blocks_confirmed_signal_after_losing_exit(self):
        rows = CONFIRMED_REVERSAL[:-1] + [
            '0.300,Insert,coolask,A,10000,102,G',
            '0.301,Insert,coolbid,B,10000,100,G',
            '0.310,Insert,coolbuy,B,1,102,F', '0.350,Cancel,coolask,,,,',
            '0.351,Insert,coolask2,A,10000,104,G',
            '0.420,Cancel,noop,,,,', '1.0,Cancel,noop,,,,',
        ]
        strategy, engine, result, updates, _ = replay('defensive_flow.py', rows)
        self.check_reconciliation(strategy, result, updates)
        self.assertFalse(strategy.halted)
        self.assertEqual((engine._user_order_seq, result.inventory, result.pnl), (2, 0, -28))
        self.assertGreater(strategy.cooldown_until, 1000000)

    def test_stale_exit_ioc_miss_retries_after_backoff(self):
        rows = CONFIRMED_ENTRY + [
            '5.115,Cancel,noop,,,,', '5.116,Cancel,bid2,,,,',
            '5.117,Insert,lowerbid,B,10000,90,G', '5.121,Cancel,noop,,,,',
            '5.216,Cancel,noop,,,,', '5.230,Cancel,noop,,,,',
        ]
        strategy, engine, result, updates, _ = replay('defensive_flow.py', rows)
        self.check_reconciliation(strategy, result, updates)
        fills = [event for event, _ in updates if event.filled_quantity]
        self.assertEqual([event.timestamp_us for event in fills], [115000, 5221000])
        self.assertEqual((engine._user_order_seq, result.inventory, result.pnl), (3, 0, -28))

    def test_unconfirmed_alternating_flow_does_not_churn(self):
        strategy, engine, result, updates, _ = replay('defensive_flow.py', CHURN)
        self.check_reconciliation(strategy, result, updates)
        self.assertEqual((engine._user_order_seq, result.traded_volume, result.pnl), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
