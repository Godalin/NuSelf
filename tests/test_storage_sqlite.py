"""Tests for SqliteStorageBackend and SqliteCollection."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.storage import create_sqlite_backend
from nuself.storage_sqlite import COLLECTION_NAMES, SqliteStorageBackend


def test_create_sqlite_backend_creates_db(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    assert isinstance(backend, SqliteStorageBackend)
    assert db_path.exists()


@pytest.mark.parametrize("name", COLLECTION_NAMES)
def test_all_known_collections_available(tmp_path: Path, name: str) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection(name)
    assert col.list() == ()


def test_unknown_collection_raises(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    with pytest.raises(ValueError, match="unknown collection"):
        backend.collection("nonexistent")


def test_put_and_get(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001", "title": "Test", "value": 42})
    result = col.get("mem_001")
    assert result is not None
    assert result["id"] == "mem_001"
    assert result["title"] == "Test"
    assert result["value"] == 42


def test_get_missing_returns_none(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    assert col.get("nonexistent") is None


def test_put_overwrites(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001", "value": 1})
    col.put("mem_001", {"id": "mem_001", "value": 2})
    result = col.get("mem_001")
    assert result is not None
    assert result["value"] == 2


def test_delete(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001"})
    col.delete("mem_001")
    assert col.get("mem_001") is None


def test_delete_missing_does_not_raise(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.delete("nonexistent")  # should not raise


def test_list_empty(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    assert col.list() == ()


def test_list_multiple(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("a", {"id": "a", "order": 1})
    col.put("b", {"id": "b", "order": 2})
    items = col.list()
    assert len(items) == 2
    ids = {item["id"] for item in items}
    assert ids == {"a", "b"}


def test_find_no_filters_returns_all(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("a", {"id": "a", "type": "x"})
    col.put("b", {"id": "b", "type": "y"})
    assert len(col.find()) == 2


def test_find_with_filters(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("a", {"id": "a", "type": "belief", "status": "active"})
    col.put("b", {"id": "b", "type": "concept", "status": "active"})
    col.put("c", {"id": "c", "type": "belief", "status": "archived"})

    beliefs = col.find(type="belief")
    assert len(beliefs) == 2

    active_beliefs = col.find(type="belief", status="active")
    assert len(active_beliefs) == 1
    assert active_beliefs[0]["id"] == "a"


def test_collections_are_independent(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    entries = backend.collection("memory_entries")
    candidates = backend.collection("memory_candidates")
    entries.put("mem_001", {"id": "mem_001"})
    assert candidates.get("mem_001") is None
    assert entries.get("mem_001") is not None


def test_reuses_same_db(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend1 = create_sqlite_backend(db_path=db_path)
    backend1.collection("memory_entries").put("mem_001", {"id": "mem_001", "data": "hello"})

    backend2 = create_sqlite_backend(db_path=db_path)
    result = backend2.collection("memory_entries").get("mem_001")
    assert result is not None
    assert result["data"] == "hello"


def test_thread_safe_put(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")

    def put_item(i: int) -> None:
        col.put(f"key_{i}", {"id": f"key_{i}", "value": i})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(put_item, range(32)))

    items = col.list()
    assert len(items) == 32


def test_find_filters_work_with_nested(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("reason_threads")
    col.put("rt_001", {"id": "rt_001", "status": "active", "topic": "Test"})
    col.put("rt_002", {"id": "rt_002", "status": "resolved", "topic": "Done"})

    result = col.find(status="active")
    assert len(result) == 1
    assert result[0]["id"] == "rt_001"
