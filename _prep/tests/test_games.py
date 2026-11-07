import itertools
import math
import random
import unittest

from arena.games import (auction, convert, demo, knapsack, knapsack_oracle,
                         shared_rewards, tournament_risk, zero_sum, zero_sum_lp)


class TestKnapsack(unittest.TestCase):
    def test_known_puzzle(self):
        result = knapsack([6, 4, 5], [11, 8, 9], 10)
        self.assertEqual(result, {"indices": [0, 1], "cost": 10, "reward": 19, "unused_budget": 0})

    def test_against_exhaustive_oracle(self):
        rng = random.Random(91)
        for _ in range(100):
            count = rng.randint(0, 9)
            costs = [rng.randint(0, 8) for _ in range(count)]
            rewards = [rng.randint(-3, 12) for _ in range(count)]
            budget = rng.randint(0, 20)
            answer = knapsack(costs, rewards, budget)
            with self.subTest(costs=costs, rewards=rewards, budget=budget):
                self.assertEqual(answer["reward"], knapsack_oracle(costs, rewards, budget)["reward"])
                self.assertLessEqual(answer["cost"], budget)
                self.assertEqual(len(answer["indices"]), len(set(answer["indices"])))

    def test_zero_cost_does_not_repeat_items(self):
        result = knapsack([0, 0, 1], [2, 3, 10], 0)
        self.assertEqual(result["reward"], 5)
        self.assertEqual(result["indices"], [0, 1])

    def test_negative_rewards_and_unused_budget(self):
        self.assertEqual(knapsack([1, 2], [-1, 3], 10)["unused_budget"], 8)
        self.assertEqual(knapsack([1], [-5], 1)["reward"], 0)

    def test_invalid_inputs(self):
        for costs, rewards, budget in (([-1], [1], 2), ([1.5], [1], 2),
                                      ([1], [math.inf], 2), ([1], [], 2), ([1], [2], True)):
            with self.subTest(costs=costs), self.assertRaises(ValueError):
                knapsack(costs, rewards, budget)


class TestSharedReward(unittest.TestCase):
    def test_expectation_vs_exact_binomial(self):
        for opponents in range(9):
            for probability in (0.0, 0.01, 0.2, 0.5, 0.99, 1.0):
                expected = sum(math.comb(opponents, k) * probability ** k *
                               (1 - probability) ** (opponents - k) * 100 / (1 + k)
                               for k in range(opponents + 1))
                result = shared_rewards([100, 80], [probability, 1 - probability], opponents)
                self.assertAlmostEqual(result["expected_payoffs"][0], expected)

    def test_not_ratio_of_expected_crowd(self):
        # One rival chooses us half the time: 0.5*100 + 0.5*50 = 75.
        self.assertEqual(shared_rewards([100, 100], [0.5, 0.5], 1)["expected_payoffs"], [75, 75])

    def test_invalid_probabilities(self):
        with self.assertRaises(ValueError):
            shared_rewards([100, 80], [0.6, 0.6], 10)


class TestAuction(unittest.TestCase):
    def test_payment_rules(self):
        self.assertEqual(auction(10, [6], [4], "first_price")["best_utility"], 4)
        self.assertEqual(auction(10, [6], [4], "second_price")["best_utility"], 6)
        self.assertEqual(auction(10, [3], [4], "all_pay")["best_utility"], -3)
        self.assertEqual(auction(10, [3], [4], "first_price")["best_utility"], 0)

    def test_tie_rule(self):
        self.assertEqual(auction(10, [4], [4], tie_probability=0.25)["best_utility"], 1.5)
        self.assertEqual(auction(10, [4], [4], "all_pay", tie_probability=0.25)["best_utility"], -1.5)

    def test_second_price_truthful_weakly_optimal(self):
        result = auction(5, list(range(11)), list(range(11)), "second_price")
        truthful = result["expected_utilities"][5]
        self.assertAlmostEqual(truthful, result["best_utility"])

    def test_uniform_first_price_grid(self):
        result = auction(10, list(range(11)), [index / 100 for index in range(1001)])
        self.assertEqual(result["best_bid"], 5)

    def test_invalid_rules(self):
        with self.assertRaises(ValueError):
            auction(1, [0], [1], "mystery")
        with self.assertRaises(ValueError):
            auction(1, [-1], [1])


class TestMatrixGames(unittest.TestCase):
    def test_matching_pennies(self):
        result = zero_sum([[1, -1], [-1, 1]], iterations=20000)
        self.assertLess(result["exploitability_gap"], 0.025)
        self.assertAlmostEqual(sum(result["row_strategy"]), 1)
        self.assertLessEqual(result["lower_bound"], 0)
        self.assertGreaterEqual(result["upper_bound"], 0)

    def test_dominated_action_saddle(self):
        result = zero_sum([[4, 3], [2, 1]])
        self.assertLess(result["exploitability_gap"], 0.001)
        self.assertAlmostEqual(result["value"], 3, places=3)

    def test_rock_paper_scissors(self):
        result = zero_sum([[0, -1, 1], [1, 0, -1], [-1, 1, 0]], iterations=20000)
        self.assertLess(result["exploitability_gap"], 0.04)
        self.assertLess(abs(result["value"]), 0.01)

    def test_bounds_match_best_responses(self):
        matrix = [[3, -2, 4], [0, 2, -1]]
        result = zero_sum(matrix, iterations=100)
        lower = min(sum(p * matrix[i][j] for i, p in enumerate(result["row_strategy"])) for j in range(3))
        upper = max(sum(q * matrix[i][j] for j, q in enumerate(result["column_strategy"])) for i in range(2))
        self.assertAlmostEqual(lower, result["lower_bound"])
        self.assertAlmostEqual(upper, result["upper_bound"])

    def test_invalid_matrix(self):
        for matrix in ([], [[]], [[1], [2, 3]], [[math.nan]]):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                zero_sum(matrix)

    def test_optional_lp_asymmetric_game(self):
        try:
            import scipy.optimize
        except ImportError:
            self.skipTest("optional scipy is unavailable")
        result = zero_sum_lp([[3, 0], [1, 2]])
        self.assertAlmostEqual(result["value"], 1.5)
        self.assertAlmostEqual(result["row_strategy"][0], 0.25)
        self.assertAlmostEqual(result["column_strategy"][0], 0.5)
        self.assertLess(result["exploitability_gap"], 1e-8)

    def test_optional_lp_negative_payoffs(self):
        try:
            import scipy.optimize
        except ImportError:
            self.skipTest("optional scipy is unavailable")
        result = zero_sum_lp([[-4, -2], [-3, -5]])
        self.assertLess(result["value"], 0)
        self.assertLess(result["exploitability_gap"], 1e-8)


class TestConversions(unittest.TestCase):
    def test_bounded_profitable_cycle(self):
        rates = {"A": [("B", 2)], "B": [("A", 0.6)]}
        self.assertAlmostEqual(convert(rates, "A", 1)["final_amount"], 1)
        self.assertAlmostEqual(convert(rates, "A", 2)["final_amount"], 1.2)
        self.assertAlmostEqual(convert(rates, "A", 4)["final_amount"], 1.44)

    def test_fees_remove_profit(self):
        rates = {"A": [("B", 2)], "B": [("A", 0.6)]}
        self.assertEqual(convert(rates, "A", 4, fee=0.2)["path"], ["A"])

    def test_against_all_walks(self):
        rates = {"A": [("B", 2), ("C", 3)], "B": [("A", 0.6), ("C", 1.7)], "C": [("A", 0.32)]}
        paths = [("A", 1)]
        best = 1.0
        for steps in range(6):
            best = max([best] + [value for node, value in paths if node == "A"])
            self.assertAlmostEqual(convert(rates, "A", steps)["final_amount"], best)
            paths = [(destination, value * rate) for source, value in paths for destination, rate in rates[source]]

    def test_zero_steps_or_no_edges(self):
        self.assertEqual(convert({}, "A", 0)["final_amount"], 1)
        self.assertEqual(convert({}, "A", 10)["path"], ["A"])

    def test_invalid_rates(self):
        with self.assertRaises(ValueError):
            convert({"A": [("B", 0)]}, "A", 1)


class TestTournamentAndDemo(unittest.TestCase):
    def test_dataset_hash_tracks_inputs_not_solver_iterations(self):
        result = demo(seed=11, trials=100, iterations=10)
        self.assertEqual(result["dataset_fingerprint"], demo(seed=11, trials=100, iterations=100)["dataset_fingerprint"])
        self.assertEqual(len(result["dataset_fingerprint"]), 64)
        self.assertNotEqual(result["dataset_fingerprint"], demo(seed=12, trials=100, iterations=10)["dataset_fingerprint"])
        self.assertNotEqual(result["dataset_fingerprint"], demo(seed=11, trials=101, iterations=10)["dataset_fingerprint"])
        self.assertNotEqual(result["dataset_fingerprint"], demo(seed=11, trials=100, iterations=10, budget=9)["dataset_fingerprint"])

    def test_dataset_hash_unchanged_with_lp_backend(self):
        try:
            import scipy.optimize
        except ImportError:
            self.skipTest("optional scipy is unavailable")
        approximate = demo(seed=11, trials=100, iterations=10)
        exact = demo(seed=11, trials=100, equilibrium_method="lp")
        self.assertEqual(approximate["dataset_fingerprint"], exact["dataset_fingerprint"])

    def test_unknown_demo_parameters_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            demo(budgget=10)

    def test_demo_oracle_bound_explicit(self):
        with self.assertRaisesRegex(ValueError, "22 items"):
            demo(costs=[1] * 23, rewards=[1] * 23)

    def test_reproducibility(self):
        self.assertEqual(tournament_risk(seed=99, trials=100), tournament_risk(seed=99, trials=100))

    def test_objective_changes_risk_preference(self):
        result = tournament_risk()
        self.assertEqual(result["best_for_expected_score"], "safe")
        self.assertEqual(result["best_for_probability_first"], "aggressive")

    def test_six_complete_puzzles(self):
        result = demo(trials=100)
        self.assertEqual(len(result["puzzles"]), 6)
        self.assertTrue(result["metrics"]["oracle_agrees"])
        self.assertTrue(result["synthetic"])


if __name__ == "__main__":
    unittest.main()
