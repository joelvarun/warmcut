"""Exact warm-set selection by maximum closure, priced by a parametric min cut.

For a memory price `price` in launches per byte, the problem

    maximise  sum of runs over programs whose whole trace is resident
              minus price times resident bytes

is a maximum closure problem and therefore exactly solvable by one minimum cut.
Sweeping the price traces the upper concave envelope of the launches versus
memory trade off. Each cut is optimal for the budget it happens to spend, and
every price supplies a Lagrangian upper bound at every other budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .flow import MaxFlow


@dataclass(frozen=True)
class ClosureSolution:
    """One cut: provably optimal at a budget equal to its own `bytes_used`."""

    price: Fraction
    launches: int
    bytes_used: int
    warm: tuple
    programs: tuple

    def lagrangian_bound(self, budget: int) -> float:
        """Upper bound on the optimum at `budget`, valid for any budget."""
        slack = budget - self.bytes_used
        return float(self.launches + self.price * slack)


def solve_at_price(instance, price) -> ClosureSolution:
    """Exact maximum closure at a rational memory price."""
    price = Fraction(price)
    if price < 0:
        raise ValueError("price must be non negative")
    numerator = price.numerator
    denominator = price.denominator

    programs = instance.program_count
    files = instance.file_count
    source = 0
    sink = programs + files + 1
    infinite = instance.total_launches * denominator + numerator * instance.total_bytes + 1

    graph = MaxFlow(sink + 1)
    for index, runs in enumerate(instance.program_runs):
        graph.add_edge(source, 1 + index, runs * denominator)
        for file_index in instance.program_files[index]:
            graph.add_edge(1 + index, 1 + programs + file_index, infinite)
    for file_index, size in enumerate(instance.file_sizes):
        graph.add_edge(1 + programs + file_index, sink, numerator * size)

    graph.max_flow(source, sink)
    reachable = graph.source_side(source)
    warm = tuple(i for i in range(files) if reachable[1 + programs + i])
    chosen = tuple(i for i in range(programs) if reachable[1 + i])
    launches = sum(instance.program_runs[i] for i in chosen)
    bytes_used = sum(instance.file_sizes[i] for i in warm)
    return ClosureSolution(price, launches, bytes_used, warm, chosen)


class Frontier:
    """Cached parametric sweep over the memory price."""

    def __init__(self, instance, max_price=Fraction(4, 1), min_price=Fraction(1, 1 << 40)):
        self.instance = instance
        self.max_price = Fraction(max_price)
        self.min_price = Fraction(min_price)
        self._cache = {}

    def at(self, price) -> ClosureSolution:
        price = Fraction(price)
        if price not in self._cache:
            self._cache[price] = solve_at_price(self.instance, price)
        return self._cache[price]

    @property
    def cuts_solved(self) -> int:
        return len(self._cache)

    def solutions(self) -> list:
        """Every cut solved so far, ordered by the memory it spends."""
        return sorted(self._cache.values(), key=lambda s: s.bytes_used)

    def envelope(self) -> list:
        """Every vertex of the upper concave envelope of launches against memory.

        Eisner and Severance parametric search rather than sampling. Two cuts A
        and B that are adjacent candidates define the single price at which they
        tie; solving there either returns a strictly better cut, which is a new
        vertex, or confirms that A and B are neighbours on the envelope. Each
        call therefore either terminates or discovers a vertex, so the sweep
        costs one minimum cut per vertex plus one per confirmed edge, and the
        enumeration is complete rather than approximate.
        """
        cheap = self.at(self.min_price)
        dear = self.at(self.max_price)
        found = {cheap.bytes_used: cheap, dear.bytes_used: dear}
        self._descend(cheap, dear, found)
        return sorted(found.values(), key=lambda s: s.bytes_used)

    def _descend(self, upper, lower, found) -> None:
        span = upper.bytes_used - lower.bytes_used
        gain = upper.launches - lower.launches
        if span <= 0 or gain <= 0:
            return
        price = Fraction(gain, span)
        if not (self.min_price <= price <= self.max_price):
            return
        middle = self.at(price)
        tie = lower.launches - price * lower.bytes_used
        if middle.launches - price * middle.bytes_used <= tie:
            return
        found[middle.bytes_used] = middle
        self._descend(upper, middle, found)
        self._descend(middle, lower, found)

    # Kept under the old name so callers can read either way.

    def best_within(self, budget) -> ClosureSolution:
        """The largest cut whose spend fits the budget."""
        best = None
        for solution in self.solutions():
            if solution.bytes_used <= budget:
                if best is None or solution.launches > best.launches:
                    best = solution
        if best is None:
            best = self.at(self.max_price)
        return best

    def upper_bound(self, budget) -> float:
        """Tightest Lagrangian bound over every price solved so far."""
        return min(
            solution.lagrangian_bound(budget) for solution in self.solutions()
        )
