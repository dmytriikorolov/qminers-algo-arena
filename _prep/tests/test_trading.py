"""Accounting invariants and explicit mock-execution behavior."""
from decimal import Decimal
import json
import math
import random
import unittest

from arena.trading import (Ledger, MarketFeatures, Snapshot, STRATEGIES, demo,
                           mock_scenario, replay, round_price)


class LedgerTests(unittest.TestCase):
    def test_cash_position_realized_and_mark(self):
        ledger = Ledger()
        ledger.submit("buy", "buy", 100, 4, 1)
        ledger.acknowledge("buy")
        ledger.fill("b1", "buy", 2, 100, 2, fee="0.2")
        self.assertEqual(ledger.position, 2)
        self.assertEqual(ledger.cash, Decimal("-200.2"))
        self.assertEqual(ledger.orders["buy"].remaining, 2)
        ledger.fill("b2", "buy", 2, 99, 3, fee="0.2")
        self.assertEqual(ledger.average_price, Decimal("99.5"))
        ledger.submit("sell", "sell", 102, 3, 4)
        ledger.fill("s1", "sell", 3, 102, 5, fee="0.3")
        summary = ledger.summary(101)
        self.assertEqual(summary["position"], 1)
        self.assertAlmostEqual(summary["realized_pnl"], 6.8)
        self.assertAlmostEqual(summary["unrealized_pnl"], 1.5)
        self.assertAlmostEqual(summary["pnl"], 8.3)
        self.assertAlmostEqual(summary["realized_pnl"] + summary["unrealized_pnl"], summary["pnl"])

    def test_short_cover_and_flip(self):
        ledger = Ledger(position_limit=20)
        ledger.submit("s", "sell", 100, 3, 0)
        ledger.fill("1", "s", 3, 100, 1)
        ledger.submit("b", "buy", 95, 5, 2)
        ledger.fill("2", "b", 5, 95, 3)
        self.assertEqual(ledger.position, 2)
        self.assertEqual(ledger.average_price, 95)
        self.assertEqual(ledger.realized_gross, 15)
        self.assertEqual(ledger.summary(96)["pnl"], 17)
        ledger.submit("close", "sell", 96, 2, 4)
        ledger.fill("3", "close", 2, 96, 5)
        self.assertEqual(ledger.position, 0)
        self.assertEqual(ledger.average_price, 0)
        self.assertEqual(ledger.summary(96)["realized_pnl"], 17)

    def test_duplicate_fill_is_idempotent(self):
        ledger = Ledger()
        ledger.submit("o", "buy", 100, 1, 1)
        self.assertTrue(ledger.fill("execution", "o", 1, 100, 2, 0.1))
        before = ledger.summary(101)
        self.assertFalse(ledger.fill("execution", "o", 1, 100, 2, 0.1))
        self.assertEqual(before, ledger.summary(101))
        with self.assertRaises(ValueError):
            ledger.fill("execution", "o", 1, 100, 2, 0.2)

    def test_pending_exposure_not_netted(self):
        ledger = Ledger(position_limit=5)
        ledger.submit("buy", "buy", 99, 5, 0)
        ledger.submit("sell", "sell", 101, 5, 0)
        self.assertEqual(ledger.exposure(), (5, -5))
        for side, price in (("buy", 99), ("sell", 101)):
            with self.assertRaises(ValueError):
                ledger.submit(side + "2", side, price, 1, 0)

    def test_cancel_fill_race_and_delayed_ack(self):
        ledger = Ledger(position_limit=5)
        ledger.submit("o", "buy", 100, 5, 0)
        ledger.request_cancel("o")
        ledger.acknowledge("o")
        self.assertEqual(ledger.orders["o"].state, "cancel_pending")
        with self.assertRaises(ValueError):
            ledger.submit("replacement", "buy", 100, 1, 1)
        ledger.fill("partial", "o", 2, 100, 1)
        self.assertEqual(ledger.exposure(), (5, 2))
        ledger.cancel_acknowledged("o")
        self.assertEqual(ledger.exposure(), (2, 2))
        ledger.acknowledge("o")
        self.assertEqual(ledger.orders["o"].state, "cancelled")
        ledger.submit("replacement", "buy", 100, 3, 2)
        with self.assertRaisesRegex(ValueError, "terminal state"):
            ledger.fill("unreconciled", "o", 1, 100, 1)

    def test_full_fill_before_cancel_ack(self):
        ledger = Ledger()
        ledger.submit("o", "sell", 100, 2, 1)
        ledger.request_cancel("o")
        ledger.fill("f", "o", 2, 100, 2)
        ledger.cancel_acknowledged("o")
        ledger.acknowledge("o")
        self.assertEqual(ledger.orders["o"].state, "filled")
        self.assertEqual(ledger.exposure(), (-2, -2))

    def test_rejection_after_early_cancel_releases_exposure(self):
        ledger = Ledger()
        ledger.submit("o", "buy", 100, 3, 0)
        ledger.request_cancel("o")
        ledger.reject("o")
        ledger.acknowledge("o")
        ledger.cancel_acknowledged("o")
        self.assertEqual(ledger.orders["o"].state, "rejected")
        self.assertEqual(ledger.exposure(), (0, 0))

    def test_tick_lot_side_quantity_and_duplicate_order(self):
        ledger = Ledger(tick=0.05, lot=2)
        invalid = [("x", "buy", 100.01, 2, 0), ("x", "buy", 100, 1, 0),
                   ("x", "buy", 100, 0, 0), ("x", "buy", 100, -2, 0),
                   ("x", "BUY", 100, 2, 0), ("x", "buy", float("nan"), 2, 0),
                   ("x", "buy", 100, True, 0), ("x", "buy", 100, 2, -1)]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                ledger.submit(*args)
        ledger.submit("valid", "buy", "100.05", 2, 0)
        with self.assertRaises(ValueError):
            ledger.submit("valid", "buy", 100, 2, 0)

    def test_invalid_fills_are_atomic(self):
        ledger = Ledger(lot=2)
        ledger.submit("o", "buy", 100, 4, 1)
        before = ledger.summary(100)
        for quantity, price, timestamp, fee in (
                (6, 100, 2, 0), (1, 100, 2, 0), (0, 100, 2, 0),
                (2, 100.1, 2, 0), (2, 99.99, 2, 0), (2, 100, 0, 0),
                (2, 100, 2, float("inf"))):
            with self.subTest(quantity=quantity, price=price), self.assertRaises(ValueError):
                ledger.fill("bad", "o", quantity, price, timestamp, fee)
            self.assertEqual(ledger.summary(100), before)
            self.assertFalse(ledger.executions)

    def test_sell_limit_and_rebate(self):
        ledger = Ledger()
        ledger.submit("o", "sell", 100, 1, 0)
        with self.assertRaises(ValueError):
            ledger.fill("bad", "o", 1, 99.9, 1)
        ledger.fill("f", "o", 1, 100.1, 1, fee=-0.05)
        self.assertAlmostEqual(ledger.summary(100)["pnl"], 0.15)
        self.assertEqual(ledger.fees, Decimal("-0.05"))

    def test_own_cross_includes_cancel_pending(self):
        ledger = Ledger()
        ledger.submit("s", "sell", 100, 1, 0)
        ledger.request_cancel("s")
        with self.assertRaisesRegex(ValueError, "own"):
            ledger.submit("b", "buy", 100, 1, 1)
        ledger.cancel_acknowledged("s")
        ledger.submit("b", "buy", 100, 1, 1)

    def test_random_round_trips_keep_accounting_identity(self):
        rng = random.Random(37)
        ledger = Ledger(position_limit=100)
        for i in range(150):
            quantity = rng.randint(1, 3)
            side = rng.choice(("buy", "sell"))
            price = Decimal(rng.randint(980, 1020)) / 10
            ledger.submit(str(i), side, price, quantity, i)
            ledger.fill(str(i), str(i), quantity, price, i, Decimal("0.03"))
            summary = ledger.summary(100)
            self.assertAlmostEqual(summary["pnl"], summary["realized_pnl"] + summary["unrealized_pnl"])


class MarketFeatureTests(unittest.TestCase):
    def test_finite_large_price_and_depth_do_not_overflow_microprice(self):
        features = Snapshot(0, 1e200, 1.1e200, 1e200, 1e200).features()
        self.assertTrue(math.isfinite(features["microprice"]))
        self.assertAlmostEqual(features["microprice"] / 1e200, 1.05)

    def test_log_returns_do_not_overflow_price_ratios(self):
        engine = MarketFeatures()
        engine.update(Snapshot(0, 1e-300, 1.1e-300, 1, 1))
        feature = engine.update(Snapshot(1, 1e300, 1.1e300, 1, 1))
        self.assertTrue(math.isfinite(feature["return"]))
        self.assertAlmostEqual(feature["return"], 600 * math.log(10))

    def test_rolling_mean_of_large_finite_prices_stays_finite(self):
        engine = MarketFeatures()
        for time in range(5):
            feature = engine.update(Snapshot(time, 1e308, 1e308, 1, 1))
            self.assertEqual(feature["rolling_mean"], 1e308)
            json.dumps(feature, allow_nan=False)

    def test_tick_units_that_overflow_are_rejected_before_history_changes(self):
        engine = MarketFeatures(tick=1e-300)
        with self.assertRaisesRegex(ValueError, "overflows"):
            engine.update(Snapshot(0, 1e200, 1.1e200, 1, 1))
        self.assertIsNone(engine.timestamp)
        self.assertFalse(engine.mids)

    def test_numeric_features(self):
        features = Snapshot(1, 99, 101, 3, 1).features(tick=0.5)
        self.assertEqual(features["mid"], 100)
        self.assertEqual(features["spread"], 2)
        self.assertEqual(features["spread_ticks"], 4)
        self.assertEqual(features["spread_bps"], 200)
        self.assertEqual(features["imbalance"], 0.5)
        self.assertEqual(features["microprice"], 100.5)

    def test_empty_crossed_invalid_books(self):
        for snapshot in (Snapshot(0, 101, 100, 1, 1), Snapshot(0, 99, 100, 0, 0),
                         Snapshot(0, 99, 100, -1, 1), Snapshot(0, 0, 100, 1, 1),
                         Snapshot(0, 99, float("nan"), 1, 1)):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                snapshot.features()
        self.assertTrue(Snapshot(0, 100, 100, 1, 1).features()["locked"])

    def test_causal_rolling_and_stale_rejection(self):
        engine = MarketFeatures(window=2, max_age=1)
        first = engine.update(Snapshot(1, 99, 101, 1, 1))
        self.assertEqual(first["rolling_mean"], 100)
        self.assertEqual(first["volatility"], 0)
        self.assertEqual(engine.update(Snapshot(2, 100, 102, 1, 1))["rolling_mean"], 100.5)
        for snapshot, now in ((Snapshot(2, 99, 101, 1, 1), 2),
                              (Snapshot(3, 99, 101, 1, 1), 5),
                              (Snapshot(3, 99, 101, 1, 1), 2)):
            with self.assertRaises(ValueError):
                engine.update(snapshot, now=now)
        self.assertEqual(engine.timestamp, 2)
        engine.update(Snapshot(3, 101, 103, 1, 1))
        self.assertEqual(first["rolling_mean"], 100)

    def test_price_rounding(self):
        self.assertEqual(round_price("100.03", "0.05", "buy"), Decimal("100.00"))
        self.assertEqual(round_price("100.03", "0.05", "sell"), Decimal("100.05"))
        with self.assertRaises(ValueError):
            round_price(100, 0, "buy")


class ReplayTests(unittest.TestCase):
    def test_deterministic_comparison(self):
        result = demo(seed=3, steps=30)
        self.assertEqual(result, demo(seed=3, steps=30))
        self.assertEqual(len(result["comparison"]), len(STRATEGIES))
        self.assertTrue(result["synthetic"])
        json.dumps(result, allow_nan=False)
        noop = result["comparison"][0]
        self.assertEqual(noop["pnl"], 0)
        self.assertEqual(noop["fills"], 0)
        for row in result["comparison"]:
            self.assertLessEqual(row["max_abs_position"], 10)
            self.assertAlmostEqual(row["pnl"], row["realized_pnl"] + row["unrealized_pnl"])

    def test_regime_and_seed_change_fingerprint(self):
        initial = demo(seed=7, steps=20)
        self.assertNotEqual(initial["dataset_fingerprint"], demo(seed=8, steps=20)["dataset_fingerprint"])
        self.assertNotEqual(initial["dataset_fingerprint"], demo(seed=7, steps=20, regime="shock")["dataset_fingerprint"])

    def test_partial_flow_does_not_overfill(self):
        # Fixed quote bid is 99.8; a one-unit sell at 99.7 fills just one unit.
        events = [(Snapshot(0, 99.9, 100.1, 5, 5), "none", 99.9, 1),
                  (Snapshot(1, 99.7, 99.9, 5, 5), "sell", 99.7, 1)]
        result = replay(events, "fixed", fee_per_unit=0.02)
        self.assertEqual(result["position"], 1)
        self.assertEqual(result["fills"], 1)
        self.assertAlmostEqual(result["cash"], -99.82)

    def test_many_scenarios_preserve_limits(self):
        for regime in ("trend", "shock", "mean_reverting"):
            for seed in (1, 5, 19):
                for strategy in STRATEGIES:
                    with self.subTest(regime=regime, seed=seed, strategy=strategy):
                        result = replay(mock_scenario(seed, 80, regime), strategy, position_limit=3)
                        self.assertLessEqual(result["max_abs_position"], 3)
                        self.assertLessEqual(result["fill_rate"], 1)

    def test_invalid_configuration(self):
        for kwargs in ({"steps": 0}, {"steps": 100001}, {"regime": "unknown"},
                       {"position_limit": 0}, {"fee_per_unit": float("nan")}, {"typo": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                demo(**kwargs)


if __name__ == "__main__":
    unittest.main()
