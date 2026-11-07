import unittest

from arena.trading import Snapshot, _quotes, mock_scenario, replay


class TrendGuardTests(unittest.TestCase):
    def test_fixed_nominal_spread_does_not_widen_by_float_roundoff(self):
        for bid, ask, expected in [(100.0, 100.2, [99.9, 100.3]),
                                   (99.7, 99.9, [99.6, 100.0])]:
            snapshot = Snapshot(0, bid, ask, 10, 10)
            features = {**snapshot.features(), "rolling_mean": snapshot.mid, "return": 0}
            quotes = _quotes("fixed", snapshot, features, 0, 10, snapshot.mid)
            self.assertEqual([row[1] for row in quotes], expected)

    def test_soft_limit_restricts_risk_increasing_orders(self):
        snapshot = Snapshot(1, 99.9, 100.1, 10, 10)
        features = snapshot.features()
        features.update(rolling_mean=100, **{"return": 0})
        for position in range(-5, 6):
            quotes = _quotes("guarded_fixed", snapshot, features, position, 10, 100)
            for side, _, quantity in quotes:
                after = position + (quantity if side == "buy" else -quantity)
                self.assertLessEqual(abs(after), 5)
        self.assertFalse(any(side == "buy" for side, _, _ in
                             _quotes("guarded_fixed", snapshot, features, 5, 10, 100)))

    def test_guard_reanchors_stale_fixed_quotes(self):
        snapshot = Snapshot(1, 89.9, 90.1, 10, 10)
        features = {**snapshot.features(), "rolling_mean": 90, "return": 0}
        guarded = _quotes("guarded_fixed", snapshot, features, 0, 10, 100)
        fixed = _quotes("fixed", snapshot, features, 0, 10, 100)
        self.assertLess(guarded[0][1], fixed[0][1])
        self.assertLessEqual(guarded[0][1], 91)

    def test_paired_regimes_preserve_limits_and_accounting(self):
        for regime in ("mean_reverting", "trend", "trend_down", "volatile"):
            for seed in (101, 109):
                events = mock_scenario(seed, 300, regime)
                result = replay(events, "guarded_fixed")
                self.assertLessEqual(result["max_abs_position"], 5)
                self.assertAlmostEqual(result["pnl"], result["cash"] + result["position"] * events[-1][0].mid)
                self.assertAlmostEqual(result["pnl"], result["realized_pnl"] + result["unrealized_pnl"])

    def test_direction_and_volatility_scenarios_are_distinct(self):
        up = mock_scenario(101, 300, "trend")
        down = mock_scenario(101, 300, "trend_down")
        volatile = mock_scenario(101, 300, "volatile")
        self.assertGreater(up[-1][0].mid, down[-1][0].mid)
        self.assertNotEqual(up, volatile)
