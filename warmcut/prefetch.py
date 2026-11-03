"""Reader for Windows prefetch (.pf) files, SCCA format versions 23, 26, 30, 31.

Windows 10 and 11 store prefetch files MAM-compressed. The only decompressor for
the XPRESS-HUFFMAN variant that is guaranteed present on the machine is the one
inside ntdll, so it is called through ctypes rather than reimplemented.
"""

from __future__ import annotations

import ctypes
import os
import struct
from dataclasses import dataclass

COMPRESSION_FORMAT_XPRESS_HUFF = 0x0004

_HEADER_SIZE = 0x54
_FILE_INFO_FIELDS = "<9I"
_METRICS_ENTRY_SIZE = 32
_RUN_COUNT_OFFSET = 0xC8

SUPPORTED_VERSIONS = (23, 26, 30, 31)


class PrefetchError(Exception):
    """Raised when a .pf file cannot be parsed."""


@dataclass
class PrefetchTrace:
    """One prefetch record: the files an image touched during startup."""

    source: str
    image_name: str
    version: int
    run_count: int
    blocks_loaded: int
    paths: list

    @property
    def file_count(self) -> int:
        return len(self.paths)


def _ntdll():
    return ctypes.WinDLL("ntdll")


def decompress_xpress_huff(payload: bytes, out_size: int) -> bytes:
    """Decompress an XPRESS-HUFFMAN buffer using RtlDecompressBufferEx."""
    ntdll = _ntdll()
    workspace = ctypes.c_ulong(0)
    fragment = ctypes.c_ulong(0)
    status = ntdll.RtlGetCompressionWorkSpaceSize(
        ctypes.c_ushort(COMPRESSION_FORMAT_XPRESS_HUFF),
        ctypes.byref(workspace),
        ctypes.byref(fragment),
    )
    if status != 0:
        raise PrefetchError("RtlGetCompressionWorkSpaceSize failed: 0x%08x" % (status & 0xFFFFFFFF))
    work = ctypes.create_string_buffer(workspace.value)
    out = ctypes.create_string_buffer(out_size)
    written = ctypes.c_ulong(0)
    status = ntdll.RtlDecompressBufferEx(
        ctypes.c_ushort(COMPRESSION_FORMAT_XPRESS_HUFF),
        out,
        ctypes.c_ulong(out_size),
        ctypes.c_char_p(payload),
        ctypes.c_ulong(len(payload)),
        ctypes.byref(written),
        work,
    )
    if status != 0:
        raise PrefetchError("RtlDecompressBufferEx failed: 0x%08x" % (status & 0xFFFFFFFF))
    return out.raw[: written.value]


def unwrap(raw: bytes) -> bytes:
    """Strip the MAM container if present and return raw SCCA bytes."""
    if raw[:3] != b"MAM":
        return raw
    if len(raw) < 8:
        raise PrefetchError("truncated MAM header")
    out_size = struct.unpack_from("<I", raw, 4)[0]
    return decompress_xpress_huff(raw[8:], out_size)


def parse(raw: bytes, source: str = "") -> PrefetchTrace:
    """Parse one prefetch record into a PrefetchTrace."""
    body = unwrap(raw)
    if len(body) < _RUN_COUNT_OFFSET + 4:
        raise PrefetchError("body too short")
    version = struct.unpack_from("<I", body, 0)[0]
    if body[4:8] != b"SCCA":
        raise PrefetchError("missing SCCA signature")
    if version not in SUPPORTED_VERSIONS:
        raise PrefetchError("unsupported SCCA version %d" % version)

    image_name = body[0x10:0x4C].decode("utf-16-le", "replace").split("\x00")[0]
    (
        metrics_offset,
        metrics_count,
        trace_offset,
        trace_count,
        strings_offset,
        strings_size,
        _volumes_offset,
        _volumes_count,
        _volumes_size,
    ) = struct.unpack_from(_FILE_INFO_FIELDS, body, _HEADER_SIZE)

    if strings_offset + strings_size > len(body):
        raise PrefetchError("filename string area out of range")
    blob = body[strings_offset : strings_offset + strings_size]
    paths = [p for p in blob.decode("utf-16-le", "replace").split("\x00") if p]

    expected = trace_offset - metrics_offset
    if metrics_count and expected != metrics_count * _METRICS_ENTRY_SIZE:
        raise PrefetchError("unexpected file metrics stride")
    if metrics_count and len(paths) != metrics_count:
        raise PrefetchError("string count %d does not match metrics count %d" % (len(paths), metrics_count))

    run_count = struct.unpack_from("<I", body, _RUN_COUNT_OFFSET)[0]
    return PrefetchTrace(
        source=source,
        image_name=image_name,
        version=version,
        run_count=run_count,
        blocks_loaded=trace_count,
        paths=paths,
    )


def read_file(path: str) -> PrefetchTrace:
    with open(path, "rb") as handle:
        return parse(handle.read(), source=os.path.basename(path))
