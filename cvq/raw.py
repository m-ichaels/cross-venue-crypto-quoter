"""Readers for the recorder's raw files: <root>/<venue>/<YYYY-MM-DD>/<HH>.jsonl.gz, one JSON object per line
{"rx": ns, "venue": str, "kind": "ws"|"snapshot"|"meta", "msg": <payload>}.

A file that is still being written (or whose writer was killed) ends in a torn gzip member or a torn line; both are
read up to the last complete line and the loss is reported, never raised."""
from __future__ import annotations

import glob
import gzip
import json
import os
import zlib
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class ReadStats:
    lines: int = 0
    bad_json: int = 0
    truncated: bool = False
    files: list = field(default_factory=list)


def hour_files(root: str, venue: str) -> list[str]:
    """All hour files of a venue in time order (directory date, then hour)."""
    return sorted(glob.glob(os.path.join(root, venue, "*", "*.jsonl.gz")))


def hour_key(path: str) -> str:
    """'2026-10-07T15' from <root>/<venue>/2026-10-07/15.jsonl.gz"""
    d = os.path.basename(os.path.dirname(path))
    h = os.path.basename(path).split(".")[0]
    return f"{d}T{h}"


def iter_lines(path: str, stats: ReadStats | None = None) -> Iterator[dict]:
    """Yield parsed records from one gzip NDJSON file, tolerating a torn tail."""
    stats = stats if stats is not None else ReadStats()
    stats.files.append(path)
    buf = b""
    try:
        with gzip.open(path, "rb") as fh:
            while True:
                try:
                    chunk = fh.read(1 << 20)
                except (EOFError, zlib.error, OSError):
                    stats.truncated = True
                    break
                if not chunk:
                    break
                buf += chunk
                parts = buf.split(b"\n")
                buf = parts.pop()
                for p in parts:
                    if not p:
                        continue
                    try:
                        yield json.loads(p)
                        stats.lines += 1
                    except ValueError:
                        stats.bad_json += 1
    except (EOFError, zlib.error, OSError):
        stats.truncated = True
    if buf.strip():
        # a complete last line without newline is fine; a torn one is counted
        try:
            yield json.loads(buf)
            stats.lines += 1
        except ValueError:
            stats.bad_json += 1
            stats.truncated = True


def iter_venue(root: str, venue: str, stats: ReadStats | None = None, files: list[str] | None = None) -> Iterator[dict]:
    for p in (files if files is not None else hour_files(root, venue)):
        yield from iter_lines(p, stats)
