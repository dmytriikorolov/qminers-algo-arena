"""Dependency-free coding primitives with explicit input assumptions."""

from collections import deque
from heapq import heappop, heappush
from itertools import count
import hashlib
import json
import math
import random
from time import perf_counter


def _edges(graph, nonnegative=False):
    for edges in graph.values():
        for _, weight in edges:
            finite = isinstance(weight, int) or (isinstance(weight, float) and math.isfinite(weight))
            if not finite or (nonnegative and weight < 0):
                raise ValueError("Dijkstra needs finite nonnegative weights" if nonnegative else "weights must be finite")


def shortest_path(graph, start, goal):
    """Dijkstra distance, or None when unreachable; all edges validated up front."""
    _edges(graph, nonnegative=True)
    serial = count()
    queue = [(0, next(serial), start)]
    distance = {start: 0}
    while queue:
        cost, _, source = heappop(queue)
        if cost != distance[source]:
            continue
        if source == goal:
            return cost
        for destination, weight in graph.get(source, []):
            candidate = cost + weight
            if isinstance(candidate, float) and not math.isfinite(candidate):
                raise ValueError("path cost overflow; use integer weights or rescale")
            if candidate < distance.get(destination, math.inf):
                distance[destination] = candidate
                heappush(queue, (candidate, next(serial), destination))
    return None


def bellman_ford(graph, start):
    """Shortest distances with negative edges; reject reachable negative cycles."""
    _edges(graph)
    vertices = {start} | set(graph)
    edges = []
    for source, neighbors in graph.items():
        for destination, weight in neighbors:
            vertices.add(destination)
            edges.append((source, destination, weight))
    distance = {node: math.inf for node in vertices}
    distance[start] = 0
    for _ in range(len(vertices) - 1):
        changed = False
        for source, destination, weight in edges:
            if distance[source] + weight < distance[destination]:
                distance[destination] = distance[source] + weight
                changed = True
        if not changed:
            break
    if any(distance[source] + weight < distance[destination] for source, destination, weight in edges):
        raise ValueError("reachable negative cycle")
    return distance


def bfs(graph, start):
    """Unweighted hop counts; graph maps vertices to neighboring vertices."""
    distance = {start: 0}
    queue = deque([start])
    while queue:
        source = queue.popleft()
        for destination in graph.get(source, []):
            if destination not in distance:
                distance[destination] = distance[source] + 1
                queue.append(destination)
    return distance


def topological_sort(graph):
    vertices = dict.fromkeys(graph)
    for neighbors in graph.values():
        vertices.update(dict.fromkeys(neighbors))
    indegree = dict.fromkeys(vertices, 0)
    for neighbors in graph.values():
        for destination in neighbors:
            indegree[destination] += 1
    queue = deque(vertex for vertex, degree in indegree.items() if degree == 0)
    ordered = []
    while queue:
        source = queue.popleft()
        ordered.append(source)
        for destination in graph.get(source, []):
            indegree[destination] -= 1
            if indegree[destination] == 0:
                queue.append(destination)
    if len(ordered) != len(vertices):
        raise ValueError("graph contains a directed cycle")
    return ordered


class UnionFind:
    def __init__(self, vertices):
        self.parent = {vertex: vertex for vertex in vertices}
        self.size = dict.fromkeys(self.parent, 1)

    def find(self, vertex):
        if vertex not in self.parent:
            raise KeyError(vertex)
        while vertex != self.parent[vertex]:
            self.parent[vertex] = self.parent[self.parent[vertex]]
            vertex = self.parent[vertex]
        return vertex

    def union(self, left, right):
        left, right = self.find(left), self.find(right)
        if left == right:
            return False
        if self.size[left] < self.size[right]:
            left, right = right, left
        self.parent[right] = left
        self.size[left] += self.size[right]
        return True


def lower_bound(values, target):
    """Index of first item >= target in an ascending sequence."""
    left, right = 0, len(values)
    while left < right:
        middle = (left + right) // 2
        if values[middle] < target:
            left = middle + 1
        else:
            right = middle
    return left


def prefix_sums(values):
    result = [0]
    for value in values:
        result.append(result[-1] + value)
    return result


def shortest_path_oracle(graph, start, goal):
    """Enumerate simple paths on tiny nonnegative graphs, for independent checks."""
    _edges(graph, nonnegative=True)
    if len(set(graph) | {node for edges in graph.values() for node, _ in edges}) > 10:
        raise ValueError("simple path enumeration limited to ten vertices")
    best = math.inf
    def visit(source, visited, cost):
        nonlocal best
        if source == goal:
            best = min(best, cost)
            return
        for destination, weight in graph.get(source, []):
            if destination not in visited:
                visit(destination, visited | {destination}, cost + weight)
    visit(start, {start}, 0)
    return None if math.isinf(best) else best


def demo(seed=7, nodes=8, **config):
    if config:
        raise ValueError("unknown coding demo parameters: " + ", ".join(sorted(config)))
    if isinstance(nodes, bool) or not isinstance(nodes, int) or not 2 <= nodes <= 10:
        raise ValueError("oracle demo needs 2-10 nodes")
    rng = random.Random(seed)
    graph = {node: [(node + 1, rng.randint(1, 9))] if node + 1 < nodes else [] for node in range(nodes)}
    for source in range(nodes):
        for destination in range(nodes):
            if source != destination and rng.random() < 0.2:
                graph[source].append((destination, rng.randint(0, 9)))
    started = perf_counter()
    distance = shortest_path(graph, 0, nodes - 1)
    elapsed = perf_counter() - started
    oracle = shortest_path_oracle(graph, 0, nodes - 1)
    return {"family": "coding", "synthetic": True, "seed": seed,
            "source": "seeded tiny directed nonnegative graph",
            "dataset_fingerprint": hashlib.sha256(json.dumps(
                graph, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest(),
            "dataset_fingerprint_format": "SHA-256 of actual graph as UTF-8 canonical JSON (sorted keys, compact separators)",
            "metrics": {"shortest_distance": distance, "oracle_distance": oracle,
                        "oracle_agrees": distance == oracle, "nodes": nodes,
                        "edges": sum(map(len, graph.values()))},
            "benchmark": {"seconds": elapsed, "method": "one perf_counter measurement; not a stable performance estimate"},
            "graph": graph,
            "warnings": ["Enumeration is an oracle for tiny inputs, not a production graph solver."]}
