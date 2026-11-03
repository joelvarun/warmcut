"""Closing the gaps the parametric sweep leaves behind.

The cuts are optimal only at the budgets they happen to spend, and on real data
those budgets are sparse: this machine has no cut at all between 0.8 and 5.5 GB.
Inside such a gap the sweep still bounds the optimum from above, and two
repairs starting from the neighbouring cuts supply the matching lower bound.
"""

from __future__ import annotations

from dataclasses import dataclass

from .baselines import density_greedy


@dataclass(frozen=True)
class RepairResult:
    launches: int
    bytes_used: int
    warm: frozenset
    origin: str
    upper_bound: float

    @property
    def gap(self) -> float:
        if self.upper_bound <= 0:
            return 0.0
        return 1.0 - self.launches / self.upper_bound


def _shrink_to_budget(instance, programs, budget):
    """Drop the worst launches-per-byte-freed program until the set fits.

    Only files owned by exactly one surviving program are freed by removing it,
    so a reference count per file is carried along and the per-program saving is
    repaired incrementally instead of being rebuilt on every removal.
    """
    sizes = instance.file_sizes
    selected = set(programs)
    owners = [[] for _ in range(instance.file_count)]
    references = [0] * instance.file_count
    for program in selected:
        for index in instance.program_files[program]:
            owners[index].append(program)
            references[index] += 1

    used = sum(size for index, size in enumerate(sizes) if references[index] > 0)
    freed = {
        program: sum(
            sizes[f] for f in instance.program_files[program] if references[f] == 1
        )
        for program in selected
    }

    while used > budget and selected:
        worst = None
        worst_score = None
        for program in selected:
            saving = freed[program]
            score = float("inf") if saving == 0 else instance.program_runs[program] / saving
            if worst_score is None or score < worst_score:
                worst_score = score
                worst = program
        selected.discard(worst)
        del freed[worst]
        for index in instance.program_files[worst]:
            references[index] -= 1
            if references[index] == 0:
                used -= sizes[index]
            elif references[index] == 1:
                for candidate in owners[index]:
                    if candidate in selected:
                        freed[candidate] += sizes[index]
                        break

    warm = {
        index for index in range(instance.file_count) if references[index] > 0
    }
    return selected, warm


def best_at_budget(instance, frontier, budget) -> RepairResult:
    """Best warm set this method can certify at an arbitrary budget."""
    candidates = []

    fitting = frontier.best_within(budget)
    grown = density_greedy(instance, budget, warm=fitting.warm)
    candidates.append(("cut-plus-growth", grown.launches, grown.bytes_used, grown.warm))

    above = None
    for solution in frontier.solutions():
        if solution.bytes_used > budget:
            above = solution
            break
    if above is not None:
        _, warm = _shrink_to_budget(instance, above.programs, budget)
        regrown = density_greedy(instance, budget, warm=warm)
        candidates.append(
            ("cut-above-shrunk", regrown.launches, regrown.bytes_used, regrown.warm)
        )

    scratch = density_greedy(instance, budget)
    candidates.append(("greedy-from-scratch", scratch.launches, scratch.bytes_used, scratch.warm))

    origin, launches, bytes_used, warm = max(candidates, key=lambda row: (row[1], -row[2]))
    return RepairResult(
        launches=launches,
        bytes_used=bytes_used,
        warm=frozenset(warm),
        origin=origin,
        upper_bound=frontier.upper_bound(budget),
    )
