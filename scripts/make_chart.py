"""Render docs/before_after.png from the numbers docs/results.json already holds."""

from __future__ import annotations

import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#dedcd5"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"

HEADLINE_MB = [250, 500, 1000, 2000, 4000, 8000]


def thousands(value, _position):
    return "%d" % value if value < 1000 else "%.1fk" % (value / 1000)


def panel_bars(axes, results):
    rows = [row for row in results["headline"] if row["mb"] in HEADLINE_MB]
    positions = range(len(rows))
    width = 0.38
    before = [row["before"] for row in rows]
    after = [row["after"] for row in rows]

    axes.bar(
        [p - width / 2 - 0.01 for p in positions], before, width,
        color=BLUE, label="frequency-ranked warming (incumbent)", zorder=3,
    )
    axes.bar(
        [p + width / 2 + 0.01 for p in positions], after, width,
        color=ORANGE, label="warmcut", zorder=3,
    )
    for position, row in zip(positions, rows):
        axes.text(position - width / 2 - 0.01, row["before"] + 90, "%d" % row["before"],
                  ha="center", va="bottom", fontsize=8, color=INK_SOFT)
        axes.text(position + width / 2 + 0.01, row["after"] + 90, "%d" % row["after"],
                  ha="center", va="bottom", fontsize=8, color=INK)
        axes.text(position, max(row["before"], row["after"]) + 620,
                  "%.2fx" % (row["after"] / row["before"]),
                  ha="center", va="bottom", fontsize=9, color=INK, fontweight="bold")

    axes.set_xticks(list(positions))
    axes.set_xticklabels(["%g" % row["mb"] for row in rows])
    axes.set_xlabel("warm cache budget (MB)", fontsize=9, color=INK_SOFT)
    axes.set_ylabel("launches starting with no cold file read", fontsize=9, color=INK_SOFT)
    axes.set_title(
        "Same memory, %d recorded launches: how many start warm"
        % results["instance"]["launches"],
        fontsize=11, color=INK, loc="left", pad=10,
    )
    axes.set_ylim(0, results["instance"]["launches"] * 1.08)
    axes.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK_SOFT)


def panel_curve(axes, results):
    curve = results["curve"]
    megabytes = [row["mb"] for row in curve]
    axes.plot(megabytes, [row["bound"] for row in curve], color=INK_SOFT,
              linewidth=1.2, linestyle=(0, (4, 3)), zorder=2,
              label="certified upper bound on the optimum")
    axes.plot(
        megabytes, [row["warmcut"] for row in curve], color=ORANGE, linewidth=2.0,
        zorder=5, label="warmcut",
        path_effects=[
            path_effects.Stroke(linewidth=4.0, foreground=SURFACE),
            path_effects.Normal(),
        ],
    )
    axes.plot(megabytes, [row["density"] for row in curve], color=AQUA,
              linewidth=2.0, zorder=4, label="density greedy (strongest heuristic)")
    axes.plot(megabytes, [row["frequency"] for row in curve], color=BLUE,
              linewidth=2.0, zorder=3, label="frequency-ranked warming")

    vertices = results["frontier"]
    axes.scatter(
        [v["mb"] for v in vertices if v["mb"] > 0],
        [v["launches"] for v in vertices if v["mb"] > 0],
        s=9, color=ORANGE, zorder=6, linewidths=0,
        label="%d provably optimal cuts" % sum(1 for v in vertices if v["mb"] > 0),
    )
    axes.set_xscale("log")
    axes.set_xlabel("warm cache budget (MB, log scale)", fontsize=9, color=INK_SOFT)
    axes.set_ylabel("launches starting with no cold file read", fontsize=9, color=INK_SOFT)
    axes.set_title(
        "The whole trade off, with the optimum bracketed",
        fontsize=11, color=INK, loc="left", pad=10,
    )
    axes.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK_SOFT)
    axes.set_ylim(0, results["instance"]["launches"] * 1.08)


def style(axes):
    axes.set_facecolor(SURFACE)
    axes.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(GRID)
    axes.tick_params(colors=INK_SOFT, labelsize=8, length=0)
    axes.yaxis.set_major_formatter(FuncFormatter(thousands))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=os.path.join("docs", "results.json"))
    parser.add_argument("--out", default=os.path.join("docs", "before_after.png"))
    args = parser.parse_args()

    with open(args.results, "r", encoding="utf-8") as handle:
        results = json.load(handle)

    figure, (left, right) = plt.subplots(1, 2, figsize=(13.0, 5.4), facecolor=SURFACE)
    panel_bars(left, results)
    panel_curve(right, results)
    for axes in (left, right):
        style(axes)
    figure.suptitle(
        "warmcut: warm-set selection from %d real Windows prefetch traces"
        % results["instance"]["programs"],
        fontsize=13, color=INK, x=0.008, ha="left", y=0.985,
    )
    figure.text(
        0.008, 0.015,
        "A launch counts only when every file in its recorded startup trace is already resident. "
        "%d programs, %d distinct files, %.1f GB if everything were warm."
        % (results["instance"]["programs"], results["instance"]["files"],
           results["instance"]["total_bytes"] / 1e9),
        fontsize=8, color=INK_SOFT, ha="left",
    )
    figure.tight_layout(rect=(0, 0.035, 1, 0.945))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    figure.savefig(args.out, dpi=150, facecolor=SURFACE)
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
