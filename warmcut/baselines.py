"""Warm-set policies to compare the exact cut against.

`frequency_ranked` is the policy class a real prefetcher uses: rank files by how
much demand they carry per byte and fill the cache in that order. It is the
incumbent. `density_greedy` is the strongest hand written heuristic found here;
it reasons about whole programs and so already exploits shared libraries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyResult:
    name: str
    launches: int
    bytes_used: int
    warm: frozenset


def frequency_ranked(instance, budget) -> PolicyResult:
    demand = instance.launch_demand()
    sizes = instance.file_sizes
    order = sorted(
        range(instance.file_count),
        key=lambda index: (-demand[index] / sizes[index], sizes[index]),
    )
    warm = set()
    used = 0
    for index in order:
        size = sizes[index]
        if used + size <= budget:
            warm.add(index)
            used += size
    return PolicyResult("frequency-ranked", instance.fault_free_launches(warm), used, frozenset(warm))


def run_count_ranked(instance, budget) -> PolicyResult:
    order = sorted(range(instance.program_count), key=lambda i: -instance.program_runs[i])
    warm = set()
    used = 0
    launches = 0
    for program in order:
        files = instance.program_files[program]
        increment = sum(instance.file_sizes[f] for f in files if f not in warm)
        if used + increment <= budget:
            warm.update(files)
            used += increment
            launches += instance.program_runs[program]
    return PolicyResult("run-count-ranked", launches, used, frozenset(warm))


def density_greedy(instance, budget, warm=None) -> PolicyResult:
    """Repeatedly admit the program with the best launches per incremental byte.

    Incremental costs are carried in an array and repaired only along the
    programs that share a file with the program just admitted, so the whole
    run costs one pass over the program-file edges rather than one per step.
    """
    sizes = instance.file_sizes
    owners = [[] for _ in range(instance.file_count)]
    for program, files in enumerate(instance.program_files):
        for index in files:
            owners[index].append(program)

    warm = set() if warm is None else set(warm)
    increments = [
        sum(sizes[f] for f in files if f not in warm)
        for files in instance.program_files
    ]
    alive = [value > 0 for value in increments]
    used = instance.bytes_of(warm)
    launches = instance.fault_free_launches(warm)
    runs = instance.program_runs

    while True:
        best = None
        best_score = -1.0
        for program in range(instance.program_count):
            if not alive[program]:
                continue
            increment = increments[program]
            if used + increment > budget:
                continue
            score = float("inf") if increment == 0 else runs[program] / increment
            if score > best_score:
                best_score = score
                best = program
        if best is None:
            break
        alive[best] = False
        used += increments[best]
        launches += runs[best]
        for index in instance.program_files[best]:
            if index in warm:
                continue
            warm.add(index)
            size = sizes[index]
            for program in owners[index]:
                increments[program] -= size
        increments[best] = 0

    return PolicyResult("density-greedy", launches, used, frozenset(warm))
