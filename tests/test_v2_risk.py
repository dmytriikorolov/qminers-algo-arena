"""Remaining deterministic exploits; no market-data profitability assertions."""

from pathlib import Path
import tempfile
import unittest

from simulator.main import load_strategy_from_file
from simulator.simulator import ExchangeSimulator, SimulationConfig
from simulator.models import OrderType


def widening_tape(cycles=1):
    # Bid never improves. Removing the best ask creates the whole +1 mid signal.
    rows = ['0,Insert,bid,B,10000,100,G']
    previous_ask = None
    for index in range(cycles):
        start = index * 10
        if previous_ask:
            rows.append(f'{start:.6f},Cancel,{previous_ask},,,,')
        rows.extend([
            f'{start + .000003:.6f},Insert,a{index},A,10000,102,G',
            f'{start + .010:.6f},Insert,t{index},B,1,102,F',
            f'{start + .050:.6f},Cancel,a{index},,,,',
            f'{start + .051:.6f},Insert,wide{index},A,10000,104,G',
            f'{start + .120:.6f},Cancel,heartbeat,,,,',
            f'{start + 5.125:.6f},Cancel,heartbeat,,,,',
            f'{start + 5.140:.6f},Cancel,heartbeat,,,,',
        ])
        previous_ask = f'wide{index}'
    return rows


def replay(filename, rows, **settings):
    strategy = load_strategy_from_file(Path('strategies') / filename)
    for key, value in settings.items():
        setattr(strategy, key, value)
    fills = []
    strategy.review_max_inventory = 0
    strategy.review_requests = []
    original = strategy.on_private_order_update

    def observe(event):
        original(event)
        if filename == 'v2_inventory_maker.py':
            strategy.review_max_inventory = max(strategy.review_max_inventory, abs(strategy.inventory))
            assert abs(strategy.inventory) <= strategy.LIMIT
        if event.filled_quantity:
            fills.append(event)

    strategy.on_private_order_update = observe
    engine = ExchangeSimulator(strategy, SimulationConfig(
        max_position=100, max_potential_position=1000,
        position_breach_penalty_per_second=10000, order_accept_delay_ms=5))
    original_send = strategy._ctx.submit_order

    def record_send(request):
        strategy.review_requests.append(request)
        return original_send(request)

    strategy._ctx.submit_order = record_send
    if filename == 'v2_inventory_maker.py':
        original_public = strategy.on_order_book_change

        def check_reservations(snapshot, trades):
            original_public(snapshot, trades)
            for sign in (1, -1):
                reserved = sum(state[2] for state in strategy.orders.values()
                               if (1 if state[0].value == 'B' else -1) == sign)
                assert abs(strategy.inventory + sign * reserved) <= strategy.LIMIT

        strategy.on_order_book_change = check_reservations
    with tempfile.TemporaryDirectory() as directory:
        tape = Path(directory) / 'widening.csv'
        tape.write_text('Time,Operation,OrderId,Side,Volume,Price,Lifespan\n'
                        + '\n'.join(rows) + '\n')
        result = engine.run(tape)
    return strategy, result, fills


class V2RiskTests(unittest.TestCase):
    def test_ask_removal_alone_baits_confirmed_long_at_worse_price(self):
        strategy, result, fills = replay('defensive_flow.py', widening_tape())
        self.assertEqual([event.fill_price for event in fills], [104, 100])
        self.assertEqual(fills[0].timestamp_us, 125000)
        self.assertEqual((result.inventory, result.traded_volume, result.pnl), (0, 4, -8))
        self.assertEqual(strategy.cash, result.cash)
        self.assertFalse(strategy.halted)

    def test_repeated_widening_consumes_budget_and_overshoots_halt_threshold(self):
        strategy, result, fills = replay('defensive_flow.py', widening_tape(cycles=6))
        self.assertEqual((len(fills), result.inventory, result.pnl), (8, 0, -32))
        self.assertTrue(strategy.halted)
        self.assertLess(result.pnl, -strategy.MAX_DRAWDOWN)
        self.assertEqual(result.breach_penalty, 0)

    def test_widening_defense_loses_more_than_size_matched_control_and_noop(self):
        rows = widening_tape()
        _, defensive, _ = replay('defensive_flow.py', rows)
        _, control, _ = replay('playground_flow.py', rows, LOT=2, LIMIT=2)
        _, noop, _ = replay('template_strategy.py', rows)
        self.assertEqual((defensive.pnl, control.pnl, noop.pnl), (-8, -4, 0))


MAKER_START = [
    '0,Insert,bid,B,1,100,G', '0,Insert,ask,A,100,102,G',
    '0.006,Insert,sweep,A,2,100,F', '0.007,Insert,lowbid,B,100,70,G',
]


class V2MakerRiskTests(unittest.TestCase):
    def check_reconciliation(self, strategy, result):
        self.assertEqual(strategy.inventory, result.inventory)
        self.assertEqual(strategy.cash, result.cash)
        self.assertEqual(result.breach_penalty, 0)
        self.assertLessEqual(strategy.review_max_inventory, strategy.LIMIT)
        self.assertTrue(strategy.halted)

    def test_opposite_fill_during_cancel_flattens_without_overshooting_ioc(self):
        rows = MAKER_START + [
            '0.008,Cancel,ask,,,,', '0.009,Insert,buy,B,1,102,F',
            '0.020,Cancel,heartbeat,,,,',
        ]
        strategy, result, _ = replay('v2_inventory_maker.py', rows)
        self.check_reconciliation(strategy, result)
        self.assertEqual((result.inventory, result.pnl), (0, 2))
        self.assertEqual(len(strategy.review_requests), 2)
        self.assertFalse(any(r.order_type == OrderType.IOC for r in strategy.review_requests))

    def test_same_side_partial_fill_during_cancel_changes_final_ioc_size(self):
        rows = MAKER_START + [
            '0.008,Insert,sweep2,A,1,100,F', '0.009,Cancel,ask,,,,',
            '0.020,Cancel,heartbeat,,,,', '0.030,Cancel,heartbeat,,,,',
        ]
        strategy, result, _ = replay('v2_inventory_maker.py', rows, LOT=2)
        self.check_reconciliation(strategy, result)
        exits = [r for r in strategy.review_requests if r.order_type == OrderType.IOC]
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].quantity, 2)
        self.assertEqual((result.inventory, result.pnl, strategy.review_max_inventory), (0, -60, 2))

    def test_halted_maker_waits_for_missing_liquidity_without_phantom_exit(self):
        rows = MAKER_START + [
            '0.008,Cancel,lowbid,,,,', '0.020,Cancel,heartbeat,,,,',
            '1,Cancel,heartbeat,,,,',
        ]
        strategy, result, _ = replay('v2_inventory_maker.py', rows)
        self.check_reconciliation(strategy, result)
        self.assertEqual(result.inventory, 1)
        self.assertFalse(any(r.order_type == OrderType.IOC for r in strategy.review_requests))
        strategy, result, _ = replay('v2_inventory_maker.py', rows + [
            '2,Insert,returnbid,B,1,40,G', '2.020,Cancel,heartbeat,,,,',
        ])
        self.check_reconciliation(strategy, result)
        self.assertEqual((result.inventory, result.pnl), (0, -60))
        self.assertLess(result.pnl, -strategy.MAX_DRAWDOWN)


if __name__ == '__main__':
    unittest.main()
