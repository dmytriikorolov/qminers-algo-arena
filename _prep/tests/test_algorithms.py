import math
import random
import unittest

from arena.algorithms import (UnionFind, bellman_ford, bfs, demo, lower_bound,
                              prefix_sums, shortest_path, shortest_path_oracle,
                              topological_sort)


class TestShortestPaths(unittest.TestCase):
    def test_nonnegative_random_graphs_against_oracle(self):
        rng = random.Random(72)
        for _ in range(50):
            graph = {i: [(j, rng.randint(0, 10)) for j in range(6)
                         if i != j and rng.random() < 0.3] for i in range(6)}
            with self.subTest(graph=graph):
                self.assertEqual(shortest_path(graph, 0, 5), shortest_path_oracle(graph, 0, 5))

    def test_unreachable_and_same_node(self):
        self.assertIsNone(shortest_path({}, "A", "B"))
        self.assertEqual(shortest_path({}, "A", "A"), 0)

    def test_negative_edge_rejected_even_after_early_goal(self):
        with self.assertRaises(ValueError):
            shortest_path({"A": [("B", 0)], "B": [("C", -1)]}, "A", "A")

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            shortest_path({0: [(1, math.nan)]}, 0, 1)

    def test_integer_distances_preserve_large_integer_precision(self):
        huge = 10 ** 100
        graph = {0: [(1, huge)], 1: [(2, 1)]}
        self.assertEqual(shortest_path(graph, 0, 2), huge + 1)
        self.assertEqual(bellman_ford(graph, 0)[2], huge + 1)

    def test_float_path_overflow_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "overflow"):
            shortest_path({0: [(1, 1e308)], 1: [(2, 1e308)]}, 0, 2)

    def test_mixed_vertex_types_do_not_need_comparison(self):
        goal = object()
        graph = {0: [("a", 1), (1, 1)], "a": [(goal, 1)], 1: [(goal, 3)]}
        self.assertEqual(shortest_path(graph, 0, goal), 2)

    def test_bellman_ford_negative_edges(self):
        graph = {"A": [("B", 4), ("C", 5)], "B": [("C", -2)]}
        self.assertEqual(bellman_ford(graph, "A")["C"], 2)

    def test_reachable_negative_cycle(self):
        with self.assertRaisesRegex(ValueError, "negative cycle"):
            bellman_ford({0: [(1, 0)], 1: [(2, -1)], 2: [(1, 0)]}, 0)

    def test_unreachable_negative_cycle_is_ignored(self):
        result = bellman_ford({1: [(2, -1)], 2: [(1, 0)]}, 0)
        self.assertEqual(result[1], math.inf)


class TestOtherPrimitives(unittest.TestCase):
    def test_dataset_hash_matches_graph_and_ignores_measurement(self):
        import hashlib
        import json
        result = demo(seed=22)
        expected = hashlib.sha256(json.dumps(result["graph"], sort_keys=True,
                                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self.assertEqual(result["dataset_fingerprint"], expected)
        self.assertEqual(expected, demo(seed=22)["dataset_fingerprint"])
        self.assertNotEqual(expected, demo(seed=23)["dataset_fingerprint"])
        self.assertNotEqual(expected, demo(seed=22, nodes=9)["dataset_fingerprint"])

    def test_unknown_demo_parameters_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            demo(nodess=6)

    def test_bfs_hop_counts(self):
        result = bfs({"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": ["A"]}, "A")
        self.assertEqual(result, {"A": 0, "B": 1, "C": 1, "D": 2})

    def test_topological_order(self):
        graph = {"A": ["C"], "B": ["C", "D"], "C": ["D"]}
        order = topological_sort(graph)
        for source, neighbors in graph.items():
            for destination in neighbors:
                self.assertLess(order.index(source), order.index(destination))

    def test_cycle_rejected(self):
        with self.assertRaises(ValueError):
            topological_sort({0: [1], 1: [0]})

    def test_union_find(self):
        union = UnionFind(range(5))
        self.assertTrue(union.union(0, 1))
        self.assertTrue(union.union(1, 2))
        self.assertFalse(union.union(0, 2))
        self.assertEqual(union.find(0), union.find(2))
        self.assertNotEqual(union.find(0), union.find(4))
        with self.assertRaises(KeyError):
            union.find(7)

    def test_lower_bound_against_enumeration(self):
        values = [-2, -1, -1, 3, 8]
        for target in range(-4, 11):
            expected = next((i for i, value in enumerate(values) if value >= target), len(values))
            self.assertEqual(lower_bound(values, target), expected)
        self.assertEqual(lower_bound([], 4), 0)

    def test_prefix_ranges(self):
        values = [4, -3, 0, 6, -2]
        sums = prefix_sums(values)
        for left in range(len(values) + 1):
            for right in range(left, len(values) + 1):
                self.assertEqual(sums[right] - sums[left], sum(values[left:right]))

    def test_demo_metrics_reproducible(self):
        result = demo(seed=22)
        self.assertEqual(result["metrics"], demo(seed=22)["metrics"])
        self.assertTrue(result["metrics"]["oracle_agrees"])
        self.assertGreaterEqual(result["benchmark"]["seconds"], 0)


if __name__ == "__main__":
    unittest.main()
