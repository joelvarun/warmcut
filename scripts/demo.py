"""Run the whole comparison on the committed instance and write docs/results.json."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warmcut import WarmSetInstance
from warmcut.baselines import density_greedy, frequency_ranked, run_count_ranked
from warmcut.closure import Frontier
from warmcut.repair import best_at_budget

MB = 1000000
BUDGETS_MB = [250, 500, 1000, 2000, 4000, 8000]


def rule(title):
    print()
    print(title)
    print("-" * len(title))


def summarise(instance):
    rule("instance")
    demand = instance.launch_demand()
    referenced = sum(1 for value in demand if value > 0)
    print("programs                 %d" % instance.program_count)
    print("recorded launches        %d" % instance.total_launches)
    print("distinct files           %d" % instance.file_count)
    print("files referenced         %d" % referenced)
    print("total resident bytes     %.1f MB" % (instance.total_bytes / MB))
    print("mean files per program   %.1f" % (
        sum(len(f) for f in instance.program_files) / instance.program_count))
    print("paths dropped as stale   %d of %d" % (
        instance.excluded_paths, instance.total_paths))


def sweep(instance):
    rule("parametric sweep")
    frontier = Frontier(instance, max_price=Fraction(4, 1), min_price=Fraction(1, 1 << 40))
    started = time.time()
    cuts = frontier.envelope()
    elapsed = time.time() - started
    print("minimum cuts solved      %d" % frontier.cuts_solved)
    print("distinct optimal sets    %d" % len(cuts))
    print("sweep wall clock         %.1f s" % elapsed)
    widest = max((b.bytes_used - a.bytes_used, a, b) for a, b in zip(cuts, cuts[1:]))
    print("widest budget gap        %.0f MB to %.0f MB" % (
        widest[1].bytes_used / MB, widest[2].bytes_used / MB))
    return frontier, cuts, elapsed


def matched_budgets(instance, cuts):
    rule("exact versus heuristics at budgets where the cut is provably optimal")
    print("%10s %10s %10s %10s %10s" % ("MB", "optimal", "density", "frequency", "ratio"))
    rows = []
    for cut in cuts:
        if cut.bytes_used == 0 or cut.bytes_used > 12000 * MB:
            continue
        budget = cut.bytes_used
        dense = density_greedy(instance, budget).launches
        freq = frequency_ranked(instance, budget).launches
        assert dense <= cut.launches, "a heuristic beat a provable optimum"
        assert freq <= cut.launches, "a heuristic beat a provable optimum"
        rows.append({
            "mb": budget / MB,
            "optimal": cut.launches,
            "density": dense,
            "frequency": freq,
        })
    for row in rows[:: max(1, len(rows) // 14)]:
        if row["frequency"]:
            ratio = "%8.2fx" % (row["optimal"] / row["frequency"])
        else:
            ratio = "      n/a"
        print("%10.1f %10d %10d %10d %s" % (
            row["mb"], row["optimal"], row["density"], row["frequency"], ratio))
    return rows


def headline(instance, frontier):
    rule("before and after at realistic cache budgets")
    print("%8s %12s %12s %8s %12s %7s  %s" % (
        "MB", "frequency", "warmcut", "gain", "bound", "gap", "origin"))
    rows = []
    for megabytes in BUDGETS_MB:
        budget = megabytes * MB
        before = frequency_ranked(instance, budget)
        after = best_at_budget(instance, frontier, budget)
        gain = after.launches / before.launches if before.launches else float("nan")
        rows.append({
            "mb": megabytes,
            "before": before.launches,
            "before_bytes": before.bytes_used,
            "after": after.launches,
            "after_bytes": after.bytes_used,
            "bound": after.upper_bound,
            "gap": after.gap,
            "origin": after.origin,
            "run_count_ranked": run_count_ranked(instance, budget).launches,
            "density": density_greedy(instance, budget).launches,
        })
        print("%8d %12d %12d %7.2fx %12.0f %6.1f%%  %s" % (
            megabytes, before.launches, after.launches, gain,
            after.upper_bound, 100 * after.gap, after.origin))
    return rows


def _subset(instance, picks):
    return WarmSetInstance(
        file_sizes=instance.file_sizes,
        file_labels=instance.file_labels,
        program_runs=[instance.program_runs[i] for i in picks],
        program_files=[instance.program_files[i] for i in picks],
        program_labels=[instance.program_labels[i] for i in picks],
    )


def curves(instance, frontier, points=36):
    """Sample every policy on a geometric budget grid for the chart."""
    rule("sampling the whole budget range for docs/before_after.png")
    ceiling = instance.total_bytes
    floor = ceiling / 400
    rows = []
    for step in range(points):
        budget = int(floor * (ceiling / floor) ** (step / (points - 1)))
        after = best_at_budget(instance, frontier, budget)
        rows.append({
            "mb": budget / MB,
            "frequency": frequency_ranked(instance, budget).launches,
            "density": density_greedy(instance, budget).launches,
            "run_count": run_count_ranked(instance, budget).launches,
            "warmcut": after.launches,
            "bound": after.upper_bound,
        })
    print("sampled %d budgets from %.0f MB to %.0f MB" % (
        len(rows), rows[0]["mb"], rows[-1]["mb"]))
    return rows


def held_out(instance, fraction=0.7, seed=7):
    """Split the recorded launches, not the programs.

    Each program's run count is split by a binomial draw. The warm set is
    chosen from the fitted half only, then scored on the other half, so a
    policy that overfits the demand estimate is penalised. Programs whose
    fitted share came out zero are invisible to the chooser and still scored.
    """
    rule("held out launches: warm set fitted on a %d percent run-count split"
         % int(100 * fraction))
    rng = random.Random(seed)
    fit_runs = []
    test_runs = []
    for runs in instance.program_runs:
        drawn = sum(1 for _ in range(runs) if rng.random() < fraction)
        fit_runs.append(drawn)
        test_runs.append(runs - drawn)

    fitted = _reweight(instance, fit_runs)
    scorer = _reweight(instance, test_runs)
    sub = Frontier(fitted, max_price=Fraction(4, 1), min_price=Fraction(1, 1 << 40))
    sub.envelope()

    print("fitted launches %d   held out launches %d   programs unseen by the fitter %d"
          % (sum(fit_runs), sum(test_runs), sum(1 for r in fit_runs if r == 0)))
    print("%8s %14s %14s %10s %8s" % ("MB", "frequency", "warmcut", "density", "gain"))
    rows = []
    for megabytes in (500, 1000, 2000, 4000, 8000):
        budget = megabytes * MB
        before = scorer.fault_free_launches(frequency_ranked(fitted, budget).warm)
        after = scorer.fault_free_launches(best_at_budget(fitted, sub, budget).warm)
        dense = scorer.fault_free_launches(density_greedy(fitted, budget).warm)
        rows.append({
            "mb": megabytes,
            "before": before,
            "after": after,
            "density": dense,
            "held_out_launches": sum(test_runs),
        })
        print("%8d %14d %14d %10d %7.2fx" % (
            megabytes, before, after, dense, after / before if before else 0.0))
    return rows


def _reweight(instance, runs):
    picks = [i for i, value in enumerate(runs) if value > 0]
    return WarmSetInstance(
        file_sizes=instance.file_sizes,
        file_labels=instance.file_labels,
        program_runs=[runs[i] for i in picks],
        program_files=[instance.program_files[i] for i in picks],
        program_labels=[instance.program_labels[i] for i in picks],
    )


def unseen_programs(instance, fraction=0.7, seed=11):
    """The harsher split: whole programs the chooser never saw."""
    rule("unseen programs: warm set fitted on 70 percent of programs")
    order = list(range(instance.program_count))
    random.Random(seed).shuffle(order)
    split = int(fraction * len(order))
    fitted = _subset(instance, sorted(order[:split]))
    scorer = _subset(instance, sorted(order[split:]))
    sub = Frontier(fitted, max_price=Fraction(4, 1), min_price=Fraction(1, 1 << 40))
    sub.envelope()
    print("fit %d programs   held out %d programs (%d launches)" % (
        fitted.program_count, scorer.program_count, scorer.total_launches))
    print("%8s %14s %14s   %s" % ("MB", "frequency", "warmcut", "held-out bytes resident"))
    rows = []
    for megabytes in (1000, 4000, 8000):
        budget = megabytes * MB
        before = frequency_ranked(fitted, budget)
        after = best_at_budget(fitted, sub, budget)
        referenced = sorted({f for files in scorer.program_files for f in files})
        total = sum(scorer.file_sizes[f] for f in referenced)
        share_before = sum(scorer.file_sizes[f] for f in referenced if f in before.warm) / total
        share_after = sum(scorer.file_sizes[f] for f in referenced if f in after.warm) / total
        rows.append({
            "mb": megabytes,
            "before": scorer.fault_free_launches(before.warm),
            "after": scorer.fault_free_launches(after.warm),
            "bytes_before": share_before,
            "bytes_after": share_after,
        })
        print("%8d %14d %14d   %.1f%% to %.1f%%" % (
            megabytes, rows[-1]["before"], rows[-1]["after"],
            100 * share_before, 100 * share_after))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", default=os.path.join("data", "instance.json"))
    parser.add_argument("--out", default=os.path.join("docs", "results.json"))
    args = parser.parse_args()

    instance = WarmSetInstance.load(args.instance)
    summarise(instance)
    frontier, cuts, elapsed = sweep(instance)
    matched = matched_budgets(instance, cuts)
    head = headline(instance, frontier)
    curve = curves(instance, frontier)
    generalisation = held_out(instance)
    unseen = unseen_programs(instance)

    payload = {
        "instance": {
            "programs": instance.program_count,
            "launches": instance.total_launches,
            "files": instance.file_count,
            "total_bytes": instance.total_bytes,
            "excluded_paths": instance.excluded_paths,
            "total_paths": instance.total_paths,
        },
        "sweep": {
            "cuts_solved": frontier.cuts_solved,
            "distinct_sets": len(cuts),
            "seconds": elapsed,
        },
        "frontier": [
            {"mb": cut.bytes_used / MB, "launches": cut.launches} for cut in cuts
        ],
        "matched": matched,
        "curve": curve,
        "headline": head,
        "held_out": generalisation,
        "unseen_programs": unseen,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)
    print()
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
