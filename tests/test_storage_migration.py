"""Tests for storage migration (FileStorageBackend → SqliteStorageBackend)."""

from __future__ import annotations

from pathlib import Path

from nuself.storage import (
    COLLECTION_NAMES,
    StorageBackend,
    create_file_backend,
    create_sqlite_backend,
    migrate_all,
    migrate_collection,
)


def _file_backend(tmp_path: Path) -> StorageBackend:
    return create_file_backend(root=tmp_path)


def _sqlite_backend(tmp_path: Path) -> StorageBackend:
    return create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")


def test_migrate_empty_collection(tmp_path: Path) -> None:
    src = _file_backend(tmp_path)
    dst = _sqlite_backend(tmp_path)
    count = migrate_collection(src, dst, "memory_entries")
    assert count == 0
    assert dst.collection("memory_entries").list() == ()


def test_migrate_single_collection(tmp_path: Path) -> None:
    src = _file_backend(tmp_path)
    src.collection("memory_entries").put("mem_001", {"id": "mem_001", "title": "Test"})

    dst = _sqlite_backend(tmp_path)
    count = migrate_collection(src, dst, "memory_entries")
    assert count == 1

    items = dst.collection("memory_entries").list()
    assert len(items) == 1
    assert items[0]["id"] == "mem_001"
    assert items[0]["title"] == "Test"


def test_migrate_all(tmp_path: Path) -> None:
    src = _file_backend(tmp_path)
    src.collection("memory_entries").put("mem_001", {"id": "mem_001", "type": "belief"})
    src.collection("reason_threads").put("rt_001", {"id": "rt_001", "status": "active"})
    src.collection("profile_items").put("pf_001", {"id": "pf_001", "type": "preference"})

    dst = _sqlite_backend(tmp_path)
    result = migrate_all(src, dst, clear_dst=True)
    assert result["memory_entries"] == 1
    assert result["reason_threads"] == 1
    assert result["profile_items"] == 1

    assert len(dst.collection("memory_entries").list()) == 1
    assert len(dst.collection("reason_threads").list()) == 1
    assert len(dst.collection("profile_items").list()) == 1


def test_migrate_clear_dst(tmp_path: Path) -> None:
    src = _file_backend(tmp_path)
    src.collection("memory_entries").put("mem_001", {"id": "mem_001", "value": "from_src"})

    dst = _sqlite_backend(tmp_path)
    dst.collection("memory_entries").put("mem_old", {"id": "mem_old", "value": "stale"})

    count = migrate_collection(src, dst, "memory_entries", clear_dst=True)
    assert count == 1

    items = dst.collection("memory_entries").list()
    assert len(items) == 1
    assert items[0]["id"] == "mem_001"


def test_migrate_all_no_empty_results(tmp_path: Path) -> None:
    """migrate_all should only include collections that had items."""
    src = _file_backend(tmp_path)
    src.collection("memory_entries").put("mem_001", {"id": "mem_001"})

    dst = _sqlite_backend(tmp_path)
    result = migrate_all(src, dst)
    assert "memory_entries" in result
    # other collections had 0 items, should not appear
    for name in COLLECTION_NAMES:
        if name != "memory_entries":
            assert name not in result


def test_migrate_preserves_all_fields(tmp_path: Path) -> None:
    src = _file_backend(tmp_path)
    src.collection("persona_prompts").put(
        "pp_001",
        {
            "id": "pp_001",
            "name": "helper",
            "content": "You are helpful.",
            "disabled": False,
            "created_at": "2026-01-01T00:00:00",
        },
    )

    dst = _sqlite_backend(tmp_path)
    migrate_collection(src, dst, "persona_prompts")

    item = dst.collection("persona_prompts").get("pp_001")
    assert item is not None
    assert item["name"] == "helper"
    assert item["content"] == "You are helpful."
    assert item["disabled"] is False


def test_migrate_multiple_items(tmp_path: Path) -> None:
    src = _file_backend(tmp_path)
    col = src.collection("trace_nodes")
    for i in range(16):
        col.put(f"tr_{i:04d}", {"id": f"tr_{i:04d}", "index": i})

    dst = _sqlite_backend(tmp_path)
    count = migrate_collection(src, dst, "trace_nodes")
    assert count == 16
    assert len(dst.collection("trace_nodes").list()) == 16
