"""Dinic maximum flow over integer capacities.

Capacities are arbitrary Python integers because the parametric closure solver
scales every edge by the denominator of a rational memory price.
"""

from __future__ import annotations


class MaxFlow:
    """Directed graph with reverse edges stored adjacently (edge i, edge i ^ 1)."""

    def __init__(self, node_count: int) -> None:
        self.node_count = node_count
        self.adjacency = [[] for _ in range(node_count)]
        self.head = []
        self.capacity = []

    def add_edge(self, source: int, target: int, capacity: int) -> int:
        index = len(self.head)
        self.adjacency[source].append(index)
        self.head.append(target)
        self.capacity.append(capacity)
        self.adjacency[target].append(index + 1)
        self.head.append(source)
        self.capacity.append(0)
        return index

    def max_flow(self, source: int, sink: int) -> int:
        total = 0
        head = self.head
        capacity = self.capacity
        adjacency = self.adjacency
        while True:
            level = self._levels(source)
            if level[sink] < 0:
                return total
            cursor = [0] * self.node_count
            path = []
            node = source
            while True:
                if node == sink:
                    delta = min(capacity[edge] for edge in path)
                    for edge in path:
                        capacity[edge] -= delta
                        capacity[edge ^ 1] += delta
                    total += delta
                    for position, edge in enumerate(path):
                        if capacity[edge] == 0:
                            del path[position:]
                            break
                    node = head[path[-1]] if path else source
                    continue
                advanced = False
                neighbours = adjacency[node]
                while cursor[node] < len(neighbours):
                    edge = neighbours[cursor[node]]
                    nxt = head[edge]
                    if capacity[edge] > 0 and level[nxt] == level[node] + 1:
                        path.append(edge)
                        node = nxt
                        advanced = True
                        break
                    cursor[node] += 1
                if advanced:
                    continue
                level[node] = -1
                if node == source:
                    break
                edge = path.pop()
                node = head[edge ^ 1]
                cursor[node] += 1

    def _levels(self, source: int) -> list:
        level = [-1] * self.node_count
        level[source] = 0
        frontier = [source]
        while frontier:
            nxt = []
            for node in frontier:
                depth = level[node] + 1
                for edge in self.adjacency[node]:
                    target = self.head[edge]
                    if self.capacity[edge] > 0 and level[target] < 0:
                        level[target] = depth
                        nxt.append(target)
            frontier = nxt
        return level

    def source_side(self, source: int) -> list:
        """Nodes reachable from the source in the residual graph after max_flow."""
        seen = [False] * self.node_count
        seen[source] = True
        frontier = [source]
        while frontier:
            nxt = []
            for node in frontier:
                for edge in self.adjacency[node]:
                    target = self.head[edge]
                    if self.capacity[edge] > 0 and not seen[target]:
                        seen[target] = True
                        nxt.append(target)
            frontier = nxt
        return seen
