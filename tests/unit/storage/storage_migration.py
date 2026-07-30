"""Tests for storage migration (FileStorageBackend → SqliteStorageBackend)."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

import multiprocessing
from multiprocessing.context import SpawnContext
from multiprocessing.synchronize import Event
from pathlib import Path
import shutil
import threading

import pytest

import nuself.storage as storage
from nuself.agent.chat import ThreadStore
from nuself.config import ConfigSystem
from nuself.memory.repository import MemoryEntryRepository
from nuself.notification import NotificationOutbox
from nuself.reason.repository import ReasonRepository
from nuself.storage import (
    _create_sqlite_backend as create_sqlite_backend,
    AtomicWriteDurabilityError,
    COLLECTION_NAMES,
    FileStorageAuthorityError,
    FileStorageBackend,
    SqliteStorageAuthorityError,
    StorageMigrationValidationError,
    StorageBackend,
    auto_backend,
    create_file_backend,
    migrate_file_backend_atomically,
    migrate_all,
    migrate_collection,
)
from nuself.storage_sqlite import SqliteStorageBackend


def _spawn_context() -> SpawnContext:
    return multiprocessing.get_context("spawn")


def _hold_file_storage_authority(
    project_root: str,
    ready: Event,
    release: Event,
) -> None:
    backend = create_file_backend(Path(project_root))
    ready.set()
    try:
        if not release.wait(timeout=30):
            raise RuntimeError("parent did not release file backend")
    finally:
        backend.close()


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


def test_atomic_file_migration_publishes_only_validated_database(
    tmp_path: Path,
) -> None:
    source = create_file_backend(tmp_path)
    source.collection("memory_entries").put(
        "mem_atomic",
        {"id": "mem_atomic", "title": "Atomic"},
    )
    source.close()

    result, database = migrate_file_backend_atomically(tmp_path)

    assert result == {"memory_entries": 1}
    assert database == tmp_path / "private" / "nuself.sqlite"
    assert database.is_file()
    assert not list(database.parent.glob("nuself.sqlite.migrating-*"))
    destination = storage.open_sqlite_backend(db_path=database)
    try:
        assert destination.collection("memory_entries").get(
            "mem_atomic"
        ) == {
            "id": "mem_atomic",
            "title": "Atomic",
        }
    finally:
        destination.close()


def test_atomic_file_migration_failure_never_publishes_partial_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = create_file_backend(tmp_path)
    source.collection("memory_entries").put(
        "mem_atomic",
        {"id": "mem_atomic"},
    )
    source.close()
    original = migrate_collection

    def fail_after_first_collection(
        src: StorageBackend,
        dst: StorageBackend,
        name: str,
        *,
        clear_dst: bool = False,
    ) -> int:
        if name == "memory_candidates":
            raise OSError("injected migration failure")
        return original(src, dst, name, clear_dst=clear_dst)

    monkeypatch.setattr(
        "nuself.storage.migrate_collection",
        fail_after_first_collection,
    )

    with pytest.raises(OSError, match="injected migration failure"):
        migrate_file_backend_atomically(tmp_path)

    private = tmp_path / "private"
    assert not (private / "nuself.sqlite").exists()
    assert not list(private.glob("nuself.sqlite.migrating-*"))


def test_atomic_file_migration_refuses_existing_destination(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "private" / "nuself.sqlite"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"existing authoritative bytes")

    with pytest.raises(FileExistsError, match="already exists"):
        migrate_file_backend_atomically(tmp_path)

    assert destination.read_bytes() == b"existing authoritative bytes"


def test_atomic_file_migration_refuses_orphan_final_sidecar(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "private" / "nuself.sqlite-wal"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_bytes(b"orphaned migration state")

    with pytest.raises(FileExistsError, match="sidecar"):
        migrate_file_backend_atomically(tmp_path)

    assert sidecar.read_bytes() == b"orphaned migration state"
    assert not (sidecar.parent / "nuself.sqlite").exists()


def test_auto_backend_ignores_unpublished_migration_database(
    tmp_path: Path,
) -> None:
    temporary = (
        tmp_path
        / "private"
        / "nuself.sqlite.migrating-interrupted"
    )
    temporary.parent.mkdir(parents=True)
    temporary.write_bytes(b"not published")

    backend = auto_backend(tmp_path)

    assert isinstance(backend, FileStorageBackend)


def test_file_backend_rejects_published_sqlite_authority(
    tmp_path: Path,
) -> None:
    database = storage._create_sqlite_backend(
        tmp_path,
        db_path=tmp_path / "private" / "nuself.sqlite",
    )
    database.close()

    with pytest.raises(
        SqliteStorageAuthorityError,
        match="SQLite authority",
    ):
        create_file_backend(tmp_path)


def test_auto_backend_rechecks_authority_after_shared_lease_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_shared_lease = threading.Event()
    resume_shared_lease = threading.Event()
    original_open = storage._open_file_authority
    selected: list[StorageBackend] = []
    errors: list[BaseException] = []

    def pause_before_shared_lease(
        private_root: Path,
        *,
        exclusive: bool,
    ) -> object:
        if not exclusive:
            before_shared_lease.set()
            if not resume_shared_lease.wait(timeout=10):
                raise RuntimeError("test did not resume shared lease")
        return original_open(private_root, exclusive=exclusive)

    monkeypatch.setattr(
        storage,
        "_open_file_authority",
        pause_before_shared_lease,
    )

    def select_backend() -> None:
        try:
            selected.append(auto_backend(tmp_path))
        except BaseException as exc:
            errors.append(exc)

    selector = threading.Thread(target=select_backend)
    selector.start()
    assert before_shared_lease.wait(timeout=10)

    _, destination = migrate_file_backend_atomically(tmp_path)
    assert destination.is_file()
    resume_shared_lease.set()
    selector.join(timeout=10)

    assert not selector.is_alive()
    assert errors == []
    assert len(selected) == 1
    assert not isinstance(selected[0], FileStorageBackend)
    selected[0].close()  # type: ignore[attr-defined]


def test_atomic_file_migration_rejects_missing_record_id(
    tmp_path: Path,
) -> None:
    source = create_file_backend(tmp_path)
    source.collection("memory_entries").put(
        "missing_id",
        {"title": "Must not be skipped"},
    )
    source.close()

    with pytest.raises(
        StorageMigrationValidationError,
        match="matching its filename",
    ):
        migrate_file_backend_atomically(tmp_path)

    private = tmp_path / "private"
    assert not (private / "nuself.sqlite").exists()
    assert not list(private.glob("nuself.sqlite.migrating-*"))


def test_atomic_file_migration_rejects_corrupt_source_record(
    tmp_path: Path,
) -> None:
    record = tmp_path / "private" / "memory" / "entries" / "corrupt.json"
    record.parent.mkdir(parents=True)
    record.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError):
        migrate_file_backend_atomically(tmp_path)

    assert not (tmp_path / "private" / "nuself.sqlite").exists()
    assert not list(
        (tmp_path / "private").glob("nuself.sqlite.migrating-*")
    )


def test_atomic_file_migration_rejects_nested_source_path(
    tmp_path: Path,
) -> None:
    nested = (
        tmp_path
        / "private"
        / "memory"
        / "entries"
        / "unexpected-directory"
    )
    nested.mkdir(parents=True)

    with pytest.raises(ValueError, match="regular file"):
        migrate_file_backend_atomically(tmp_path)

    assert not (tmp_path / "private" / "nuself.sqlite").exists()


def test_atomic_file_migration_reports_visible_uncertain_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = create_file_backend(tmp_path)
    source.collection("memory_entries").put(
        "mem_atomic",
        {"id": "mem_atomic"},
    )
    source.close()
    destination = tmp_path / "private" / "nuself.sqlite"

    def fail_directory_sync(path: Path) -> None:
        assert path == destination.parent
        raise OSError("injected directory sync failure")

    monkeypatch.setattr(
        "nuself.storage._sync_directory",
        fail_directory_sync,
    )

    with pytest.raises(
        AtomicWriteDurabilityError,
        match="destination replaced but directory synchronization failed",
    ):
        migrate_file_backend_atomically(tmp_path)

    assert destination.is_file()
    assert not list(
        destination.parent.glob("nuself.sqlite.migrating-*")
    )


def test_atomic_file_migration_rejects_active_file_runtime(
    tmp_path: Path,
) -> None:
    context = _spawn_context()
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_file_storage_authority,
        args=(str(tmp_path), ready, release),
    )
    process.start()
    try:
        assert ready.wait(timeout=30)

        with pytest.raises(
            FileStorageAuthorityError,
            match="migration",
        ):
            migrate_file_backend_atomically(tmp_path)

        assert not (tmp_path / "private" / "nuself.sqlite").exists()
    finally:
        release.set()
        process.join(timeout=30)
        if process.is_alive():
            process.terminate()
            process.join(timeout=30)
    assert process.exitcode == 0


def test_migrate_normalizes_legacy_candidate_payload_relations(
    tmp_path: Path,
) -> None:
    source = _file_backend(tmp_path / "source")
    source.collection("memory_candidates").put(
        "candidate_legacy",
        {
            "id": "candidate_legacy",
            "relations": {"supports": ["mem_current"]},
            "related_memory_ids": ["mem_related"],
            "payload": {
                "relations": {"supersedes": ["mem_current"]},
                "supersedes": ["mem_older", "mem_current"],
            },
        },
    )
    destination = _sqlite_backend(tmp_path / "destination")

    migrate_collection(source, destination, "memory_candidates")

    migrated = destination.collection("memory_candidates").get(
        "candidate_legacy"
    )
    assert migrated == {
        "id": "candidate_legacy",
        "relations": {
            "supports": ["mem_current"],
            "related_to": ["mem_related"],
        },
        "payload": {
            "relations": {
                "supersedes": ["mem_current", "mem_older"],
            },
        },
    }


def test_migrate_preserves_malformed_legacy_relation_shape(
    tmp_path: Path,
) -> None:
    source = _file_backend(tmp_path / "source")
    source.collection("memory_entries").put(
        "mem_invalid",
        {
            "id": "mem_invalid",
            "relations": "invalid",
            "supersedes": ["mem_old"],
        },
    )
    destination = _sqlite_backend(tmp_path / "destination")

    migrate_collection(source, destination, "memory_entries")

    assert destination.collection("memory_entries").get("mem_invalid") == {
        "id": "mem_invalid",
        "relations": "invalid",
        "supersedes": ["mem_old"],
    }


def test_real_v025_private_fixture_migrates_and_reads_in_current_runtime(
    tmp_path: Path,
) -> None:
    fixture = (
        Path(__file__).parents[2]
        / "fixtures"
        / "migrations"
        / "v0.2.5"
        / "private"
    )
    private_root = tmp_path / "private"
    shutil.copytree(fixture, private_root)
    with pytest.warns(
        RuntimeWarning,
        match="deprecated_v025_langmem_adapter",
    ):
        config = ConfigSystem.load(project_root=tmp_path)
    assert config.experimental.vector_index is False

    result, database = migrate_file_backend_atomically(tmp_path)
    assert database == private_root / "nuself.sqlite"
    destination = auto_backend(tmp_path)

    assert result == {
        "memory_entries": 1,
        "reason_threads": 1,
        "notification_outbox": 1,
    }
    memory = MemoryEntryRepository(
        tmp_path,
        backend=destination,
    ).get("mem_v025")
    assert memory.importance == 0.0
    assert memory.title == "Legacy durable belief"
    assert memory.relations == {
        "supersedes": ("mem_older",),
        "related_to": ("mem_related",),
    }
    notification = NotificationOutbox(
        tmp_path,
        backend=destination,
    ).get("out_v025")
    assert notification.context.request_id is None
    assert notification.required_adapters == ()
    assert notification.deliveries == {}
    reason = ReasonRepository(
        tmp_path,
        backend=destination,
    ).get_thread("reason_v025")
    assert reason.topic == "Preserve old reasoning state"
    thread = ThreadStore(tmp_path).load("default")
    assert thread.next_message_index == 2
    assert [message.role for message in thread.messages] == [
        "user",
        "assistant",
    ]
    assert isinstance(destination, SqliteStorageBackend)
    destination.close()
    with pytest.raises(
        SqliteStorageAuthorityError,
        match="SQLite authority",
    ):
        create_file_backend(tmp_path)
