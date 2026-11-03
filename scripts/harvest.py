"""Rebuild data/instance.json from this machine's own prefetch directory.

C:/Windows/Prefetch is readable without elevation on a normal Windows 11
install. Paths are redacted before they are written: everything under the
Windows directory is kept verbatim because it is identical on every machine,
and every other path is replaced by an opaque identifier. Image names are
replaced by ordinals, so the committed instance carries the real structure,
the real byte costs and the real launch counts, and no personal data.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warmcut import instance as instance_module
from warmcut.prefetch import PrefetchError, read_file

PREFETCH_DIR = "C:/Windows/Prefetch"


def nt_to_local(path: str) -> str:
    """Map a prefetch NT path to a drive path, or None when not mappable."""
    marker = path.find("}")
    if marker < 0 or marker + 2 >= len(path):
        return None
    return "C:/" + path[marker + 2 :].replace("\\", "/")


def size_resolver():
    cache = {}

    def resolve(path: str):
        local = nt_to_local(path)
        if local is None:
            return None
        if local in cache:
            return cache[local]
        try:
            size = os.path.getsize(local)
        except OSError:
            size = None
        cache[local] = size
        return size

    return resolve


SID = re.compile(r"s-1-5-[0-9-]{6,}")
LONG_HEX = re.compile(r"[0-9a-f]{24,}")


def labeller():
    opaque = {}

    def label(path: str) -> str:
        local = nt_to_local(path) or path
        lowered = local.lower()
        universal = (
            lowered.startswith("c:/windows/")
            and not SID.search(lowered)
            and not LONG_HEX.search(lowered)
        )
        if universal:
            return instance_module.WINDOWS_PREFIX + lowered[len("c:/windows/") :]
        key = lowered
        if key not in opaque:
            opaque[key] = "redacted/file-%05d" % len(opaque)
        return opaque[key]

    return label


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefetch-dir", default=PREFETCH_DIR)
    parser.add_argument("--out", default=os.path.join("data", "instance.json"))
    args = parser.parse_args()

    if not os.path.isdir(args.prefetch_dir):
        print("no prefetch directory at %s" % args.prefetch_dir)
        return 2

    traces = []
    failures = 0
    names = sorted(
        name for name in os.listdir(args.prefetch_dir) if name.lower().endswith(".pf")
    )
    for name in names:
        try:
            traces.append(read_file(os.path.join(args.prefetch_dir, name)))
        except (PrefetchError, OSError):
            failures += 1

    print("prefetch records read: %d of %d (%d unreadable)" % (len(traces), len(names), failures))
    built = instance_module.build(traces, size_resolver(), labeller())
    print(
        "programs %d  launches %d  files %d  bytes %.1f MB  dropped paths %d of %d"
        % (
            built.program_count,
            built.total_launches,
            built.file_count,
            built.total_bytes / 1e6,
            built.excluded_paths,
            built.total_paths,
        )
    )
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    built.save(args.out)
    print("wrote %s (%.0f KB)" % (args.out, os.path.getsize(args.out) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
