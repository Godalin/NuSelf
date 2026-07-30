from __future__ import annotations

from pathlib import Path
import runpy
from typing import Callable, cast

import pytest

from nuself.domain.memory import MemoryEntry
from nuself.storage import get_default_backend, reset_default_backend
_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrate_legacy_memory_records.py"
)
run = cast(
    Callable[..., int],
    runpy.run_path(str(_SCRIPT))["run"],
)


def _put(authority: Path, record: dict[str, object]) -> None:
    record_id = record["id"]
    assert isinstance(record_id, str)
    get_default_backend(authority).collection("memory_entries").put(
        record_id,
        record,
    )
    reset_default_backend(authority)


def test_dry_run_then_apply_lossless_legacy_memory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    entry = MemoryEntry(type="belief", title="Legacy", body="Preserve me.")
    legacy = entry.to_wire()
    legacy["related_memory_ids"] = []
    legacy["supersedes"] = []
    _put(tmp_path, legacy)

    assert run(tmp_path, apply=False) == 0
    assert "1 migratable, 0 unresolved" in capsys.readouterr().out
    assert (
        get_default_backend(tmp_path)
        .collection("memory_entries")
        .get(entry.id)
        == legacy
    )
    reset_default_backend(tmp_path)

    assert run(tmp_path, apply=True) == 0
    assert "Migrated 1 record(s)." in capsys.readouterr().out
    repaired = (
        get_default_backend(tmp_path)
        .collection("memory_entries")
        .get(entry.id)
    )
    assert repaired is not None
    assert "related_memory_ids" not in repaired
    assert "supersedes" not in repaired
    assert MemoryEntry.from_wire(repaired).body == "Preserve me."


def test_refuses_nonempty_legacy_relations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    entry = MemoryEntry(type="belief", title="Legacy", body="Do not discard.")
    legacy = entry.to_wire()
    legacy["related_memory_ids"] = ["mem_other"]
    _put(tmp_path, legacy)

    assert run(tmp_path, apply=True) == 1
    assert "0 migratable, 1 unresolved" in capsys.readouterr().out
    assert (
        get_default_backend(tmp_path)
        .collection("memory_entries")
        .get(entry.id)
        == legacy
    )


def test_adds_missing_empty_relations(
    tmp_path: Path,
) -> None:
    entry = MemoryEntry(type="belief", title="Older", body="Preserve me.")
    legacy = entry.to_wire()
    del legacy["relations"]
    _put(tmp_path, legacy)

    assert run(tmp_path, apply=True) == 0
    repaired = (
        get_default_backend(tmp_path)
        .collection("memory_entries")
        .get(entry.id)
    )
    assert repaired is not None
    assert repaired["relations"] == {}
    assert MemoryEntry.from_wire(repaired).body == "Preserve me."
