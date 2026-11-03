import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from warmcut.prefetch import PrefetchError, parse, read_file, unwrap

PREFETCH_DIR = "C:/Windows/Prefetch"


def test_unwrap_passes_through_uncompressed():
    assert unwrap(b"\x1f\x00\x00\x00SCCA") == b"\x1f\x00\x00\x00SCCA"


def test_rejects_missing_signature():
    with pytest.raises(PrefetchError):
        parse(b"\x1f\x00\x00\x00NOPE" + b"\x00" * 400)


def test_rejects_short_body():
    with pytest.raises(PrefetchError):
        parse(b"\x1f\x00\x00\x00SCCA")


@pytest.mark.skipif(not os.path.isdir(PREFETCH_DIR), reason="no local prefetch directory")
def test_reads_every_local_record():
    names = [n for n in os.listdir(PREFETCH_DIR) if n.lower().endswith(".pf")]
    if not names:
        pytest.skip("prefetch directory is empty")
    for name in names:
        trace = read_file(os.path.join(PREFETCH_DIR, name))
        assert trace.image_name
        assert trace.run_count >= 1
        assert trace.file_count == len(trace.paths)
        assert all(path.startswith("\\") for path in trace.paths)
