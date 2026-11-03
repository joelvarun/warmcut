"""The warm-set selection instance.

A WarmSetInstance is a bipartite demand structure: every program carries a
recorded launch count, every file carries a byte cost, and a launch of a program
is fault free only when every file in its startup trace is already resident.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

WINDOWS_PREFIX = "windows/"


@dataclass
class WarmSetInstance:
    file_sizes: list
    file_labels: list
    program_runs: list
    program_files: list
    program_labels: list = field(default_factory=list)
    excluded_paths: int = 0
    total_paths: int = 0

    @property
    def file_count(self) -> int:
        return len(self.file_sizes)

    @property
    def program_count(self) -> int:
        return len(self.program_runs)

    @property
    def total_launches(self) -> int:
        return sum(self.program_runs)

    @property
    def total_bytes(self) -> int:
        return sum(self.file_sizes)

    def launch_demand(self) -> list:
        """Launches that reference each file, used by the frequency baseline."""
        demand = [0] * self.file_count
        for runs, files in zip(self.program_runs, self.program_files):
            for index in files:
                demand[index] += runs
        return demand

    def fault_free_launches(self, warm) -> int:
        """Launches whose whole startup trace is resident in `warm`."""
        resident = warm if isinstance(warm, (set, frozenset)) else set(warm)
        total = 0
        for runs, files in zip(self.program_runs, self.program_files):
            for index in files:
                if index not in resident:
                    break
            else:
                total += runs
        return total

    def bytes_of(self, warm) -> int:
        return sum(self.file_sizes[index] for index in warm)

    def program_bytes(self, program: int) -> int:
        return sum(self.file_sizes[index] for index in self.program_files[program])

    def to_json(self) -> dict:
        return {
            "schema": "warmcut.instance.v1",
            "total_paths": self.total_paths,
            "excluded_paths": self.excluded_paths,
            "files": [
                {"size": size, "label": label}
                for size, label in zip(self.file_sizes, self.file_labels)
            ],
            "programs": [
                {"label": label, "runs": runs, "files": files}
                for label, runs, files in zip(
                    self.program_labels, self.program_runs, self.program_files
                )
            ],
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_json(), handle, separators=(",", ":"))
            handle.write("\n")

    @classmethod
    def load(cls, path: str) -> "WarmSetInstance":
        with open(path, "r", encoding="utf-8") as handle:
            blob = json.load(handle)
        files = blob["files"]
        programs = blob["programs"]
        return cls(
            file_sizes=[entry["size"] for entry in files],
            file_labels=[entry["label"] for entry in files],
            program_runs=[entry["runs"] for entry in programs],
            program_files=[entry["files"] for entry in programs],
            program_labels=[entry["label"] for entry in programs],
            excluded_paths=blob.get("excluded_paths", 0),
            total_paths=blob.get("total_paths", 0),
        )


def build(traces, resolve_size, label_path) -> WarmSetInstance:
    """Turn parsed prefetch traces into an instance.

    `resolve_size` returns the on-disk byte size of an NT path, or None when the
    path no longer resolves (temp files, deleted files, other volumes). Such
    paths cannot be warmed and cannot be read either, so they are dropped and
    counted rather than guessed at.
    """
    sizes = {}
    unresolved = set()
    total_paths = 0
    for trace in traces:
        for path in trace.paths:
            total_paths += 1
            if path in sizes or path in unresolved:
                continue
            size = resolve_size(path)
            if size is None or size <= 0:
                unresolved.add(path)
            else:
                sizes[path] = size

    index_of = {}
    file_sizes = []
    file_labels = []
    program_runs = []
    program_files = []
    program_labels = []
    for number, trace in enumerate(traces):
        kept = sorted({path for path in trace.paths if path in sizes})
        if not kept or trace.run_count <= 0:
            continue
        indices = []
        for path in kept:
            index = index_of.get(path)
            if index is None:
                index = len(file_sizes)
                index_of[path] = index
                file_sizes.append(sizes[path])
                file_labels.append(label_path(path))
            indices.append(index)
        program_runs.append(trace.run_count)
        program_files.append(indices)
        program_labels.append("program-%04d" % number)

    return WarmSetInstance(
        file_sizes=file_sizes,
        file_labels=file_labels,
        program_runs=program_runs,
        program_files=program_files,
        program_labels=program_labels,
        excluded_paths=len(unresolved),
        total_paths=total_paths,
    )
