import itertools
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warmcut.flow import MaxFlow


def test_known_small_network():
    graph = MaxFlow(4)
    graph.add_edge(0, 1, 3)
    graph.add_edge(0, 2, 2)
    graph.add_edge(1, 2, 5)
    graph.add_edge(1, 3, 2)
    graph.add_edge(2, 3, 3)
    assert graph.max_flow(0, 3) == 5


def brute_force_min_cut(nodes, edges, source, sink):
    best = None
    others = [n for n in range(nodes) if n not in (source, sink)]
    for size in range(len(others) + 1):
        for subset in itertools.combinations(others, size):
            side = {source} | set(subset)
            value = sum(c for (u, v, c) in edges if u in side and v not in side)
            if best is None or value < best:
                best = value
    return best


def test_matches_brute_force_min_cut():
    random.seed(11)
    for _ in range(40):
        nodes = random.randint(4, 7)
        edges = []
        for u in range(nodes):
            for v in range(nodes):
                if u != v and random.random() < 0.45:
                    edges.append((u, v, random.randint(1, 9)))
        if not edges:
            continue
        graph = MaxFlow(nodes)
        for u, v, c in edges:
            graph.add_edge(u, v, c)
        flow = graph.max_flow(0, nodes - 1)
        assert flow == brute_force_min_cut(nodes, edges, 0, nodes - 1)


def test_source_side_is_a_valid_cut():
    graph = MaxFlow(4)
    graph.add_edge(0, 1, 3)
    graph.add_edge(1, 3, 1)
    graph.add_edge(0, 2, 1)
    graph.add_edge(2, 3, 4)
    flow = graph.max_flow(0, 3)
    side = graph.source_side(0)
    assert side[0] and not side[3]
    assert flow == 2
