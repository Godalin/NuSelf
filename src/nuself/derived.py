"""Rebuildable JSON projections of authoritative storage records."""

from __future__ import annotations

from pathlib import Path

from nuself.config import RuntimePaths
from nuself.storage import write_json_atomic


def write_derived_index(
    paths: RuntimePaths, filename: str, records: list[object]
) -> Path:
    path = paths.authority_root / "derived" / filename
    write_json_atomic(path, {"version": 1, "records": records})
    return path
