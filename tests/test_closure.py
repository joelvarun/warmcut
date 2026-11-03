import itertools
import os
import random
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warmcut.baselines import density_greedy, frequency_ranked
from warmcut.closure import Frontier, solve_at_price
from warmcut.instance import WarmSetInstance


def random_instance(seed):
    rng = random.Random(seed)
    files = rng.randint(2, 7)
    programs = rng.randint(1, 5)
    sizes = [rng.randint(1, 20) for _ in range(files)]
    runs = []
    members = []
    for _ in range(programs):
        count = rng.randint(1, files)
        members.append(sorted(rng.sample(range(files), count)))
        runs.append(rng.randint(1, 30))
    return WarmSetInstance(
        file_sizes=sizes,
        file_labels=["f%d" % i for i in range(files)],
        program_runs=runs,
        program_files=members,
        program_labels=["p%d" % i for i in range(programs)],
    )


def brute_force_lagrangian(instance, price):
    best = None
    files = range(instance.file_count)
    for size in range(instance.file_count + 1):
        for subset in itertools.combinations(files, size):
            warm = set(subset)
            value = instance.fault_free_launches(warm) - price * instance.bytes_of(warm)
            if best is None or value > best:
                best = value
    return best


def brute_force_budget(instance, budget):
    best = 0
    files = range(instance.file_count)
    for size in range(instance.file_count + 1):
        for subset in itertools.combinations(files, size):
            if instance.bytes_of(subset) > budget:
                continue
            best = max(best, instance.fault_free_launches(set(subset)))
    return best


def test_lagrangian_matches_brute_force():
    for seed in range(60):
        instance = random_instance(seed)
        for price in (Fraction(0), Fraction(1, 7), Fraction(1, 2), Fraction(3, 1)):
            solution = solve_at_price(instance, price)
            got = solution.launches - price * solution.bytes_used
            assert got == brute_force_lagrangian(instance, price), (seed, price)


def test_cut_is_closed():
    for seed in range(60):
        instance = random_instance(seed)
        solution = solve_at_price(instance, Fraction(1, 5))
        warm = set(solution.warm)
        for program in solution.programs:
            assert all(f in warm for f in instance.program_files[program])


def test_breakpoint_is_optimal_at_its_own_budget():
    for seed in range(40):
        instance = random_instance(seed)
        frontier = Frontier(instance, max_price=Fraction(40), min_price=Fraction(1, 1 << 12))
        for solution in frontier.envelope():
            assert solution.launches == brute_force_budget(instance, solution.bytes_used)


def test_heuristics_never_beat_the_optimum():
    for seed in range(40):
        instance = random_instance(seed)
        frontier = Frontier(instance, max_price=Fraction(40), min_price=Fraction(1, 1 << 12))
        for solution in frontier.envelope():
            budget = solution.bytes_used
            assert density_greedy(instance, budget).launches <= solution.launches
            assert frequency_ranked(instance, budget).launches <= solution.launches


def test_lagrangian_bound_dominates_the_truth():
    for seed in range(30):
        instance = random_instance(seed)
        frontier = Frontier(instance, max_price=Fraction(40), min_price=Fraction(1, 1 << 12))
        frontier.envelope()
        for budget in (1, 5, 13, 29, instance.total_bytes):
            assert frontier.upper_bound(budget) >= brute_force_budget(instance, budget) - 1e-9
