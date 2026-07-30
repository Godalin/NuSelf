import json
from pathlib import Path
import stat
import threading
from types import SimpleNamespace

import pytest

import nuself.storage as storage
from nuself.logs import read_log_events
from nuself.private_fs import ensure_private_file
from nuself.storage import (
    AtomicDeleteDurabilityError,
    AtomicWriteCleanupError,
    AtomicWriteDurabilityError,
    FileStorageBackend,
    delete_file_durable,
    write_json_atomic,
    write_text_atomic,
)


@pytest.mark.parametrize(
    "key",
    [
        "",
        ".",
        "..",
        "../outside",
        "nested/record",
        r"nested\record",
        "/tmp/absolute",
        "record\0suffix",
    ],
)
@pytest.mark.parametrize("operation", ["get", "put", "delete"])
def test_file_collection_rejects_path_like_keys(
    tmp_path: Path,
    key: str,
    operation: str,
) -> None:
    collection = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    ).collection("memory_entries")

    with pytest.raises(ValueError, match="collection key"):
        if operation == "get":
            collection.get(key)
        elif operation == "put":
            collection.put(key, {"id": key})
        else:
            collection.delete(key)

    assert not (tmp_path / "outside.json").exists()


@pytest.mark.parametrize("operation", ["get", "put", "delete"])
def test_file_collection_rejects_symlink_records(
    tmp_path: Path,
    operation: str,
) -> None:
    directory = tmp_path / "private" / "memory" / "entries"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text('{"id":"outside"}', encoding="utf-8")
    record = directory / "linked.json"
    record.symlink_to(outside)
    collection = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    ).collection("memory_entries")

    with pytest.raises(ValueError, match="symlink"):
        if operation == "get":
            collection.get("linked")
        elif operation == "put":
            collection.put("linked", {"id": "linked"})
        else:
            collection.delete("linked")

    assert outside.read_text(encoding="utf-8") == '{"id":"outside"}'
    assert record.is_symlink()


def test_file_collection_rejects_symlink_directory(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    collection_dir = tmp_path / "private" / "memory" / "entries"
    collection_dir.parent.mkdir(parents=True)
    collection_dir.symlink_to(outside, target_is_directory=True)
    collection = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    ).collection("memory_entries")

    with pytest.raises(ValueError, match="directory.*symlink"):
        collection.put("record", {"id": "record"})

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("record_id", ["different", None, 7])
def test_file_collection_put_rejects_record_id_mismatch(
    tmp_path: Path,
    record_id: object,
) -> None:
    collection = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    ).collection("memory_entries")

    with pytest.raises(ValueError, match="id.*collection key"):
        collection.put("expected", {"id": record_id})

    assert collection.get("expected") is None


def test_file_collection_lists_direct_records_only_and_rejects_symlink(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "private" / "memory" / "entries"
    nested = directory / "nested"
    nested.mkdir(parents=True)
    (nested / "hidden.json").write_text(
        '{"id":"hidden"}',
        encoding="utf-8",
    )
    outside = tmp_path / "outside.json"
    outside.write_text('{"id":"outside"}', encoding="utf-8")
    (directory / "linked.json").symlink_to(outside)
    collection = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    ).collection("memory_entries")

    with pytest.raises(ValueError, match="symlink"):
        collection.list()

    (directory / "linked.json").unlink()
    assert collection.list() == ()


@pytest.mark.parametrize(
    ("raw", "error_type"),
    [
        ("{", json.JSONDecodeError),
        ("[]", ValueError),
        ('{"value": NaN}', ValueError),
    ],
)
def test_file_collection_lists_isolate_corrupt_json_but_get_surfaces_it(
    tmp_path: Path,
    raw: str,
    error_type: type[Exception],
) -> None:
    backend = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    )
    collection = backend.collection("memory_entries")
    collection.put("healthy", {"id": "healthy", "title": "Readable"})
    corrupt_path = tmp_path / "private" / "memory" / "entries" / "corrupt.json"
    corrupt_path.write_text(raw, encoding="utf-8")

    assert collection.list() == ({"id": "healthy", "title": "Readable"},)
    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "memory_entries",
        "record_id": "corrupt",
    }
    with pytest.raises(error_type):
        collection.get("corrupt")


def test_file_backend_transaction_is_reentrant_in_one_thread(
    tmp_path: Path,
) -> None:
    backend = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    )
    collection = backend.collection("memory_entries")

    with backend.transaction():
        collection.put("outer", {"id": "outer"})
        with backend.transaction():
            collection.put("inner", {"id": "inner"})

    assert collection.get("outer") == {"id": "outer"}
    assert collection.get("inner") == {"id": "inner"}


@pytest.mark.parametrize(
    "operation",
    ["collection", "get", "put", "delete", "list", "find", "transaction"],
)
def test_closed_file_backend_and_existing_collections_reject_access(
    tmp_path: Path,
    operation: str,
) -> None:
    backend = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    )
    collection = backend.collection("memory_entries")
    collection.put("record", {"id": "record"})
    backend.close()

    with pytest.raises(RuntimeError, match="backend is closed"):
        if operation == "collection":
            backend.collection("memory_entries")
        elif operation == "get":
            collection.get("record")
        elif operation == "put":
            collection.put("new", {"id": "new"})
        elif operation == "delete":
            collection.delete("record")
        elif operation == "list":
            collection.list()
        elif operation == "find":
            collection.find(id="record")
        else:
            with backend.transaction():
                pass

    assert (
        tmp_path / "private" / "memory" / "entries" / "record.json"
    ).is_file()


def test_write_text_atomic_replaces_complete_destination(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")

    write_text_atomic(path, "new\n")

    assert path.read_text(encoding="utf-8") == "new\n"
    assert list(path.parent.glob("*.tmp")) == []


def test_delete_file_durable_unlinks_before_directory_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.json"
    path.parent.mkdir()
    path.write_text("state", encoding="utf-8")
    operations: list[str] = []
    original_unlink = Path.unlink

    def record_unlink(
        target: Path,
        missing_ok: bool = False,
    ) -> None:
        operations.append("unlink")
        original_unlink(target, missing_ok=missing_ok)

    def record_sync(directory: Path) -> None:
        assert not path.exists()
        assert directory == path.parent
        operations.append("directory_sync")

    monkeypatch.setattr(Path, "unlink", record_unlink)
    monkeypatch.setattr(storage, "_sync_directory", record_sync)

    assert delete_file_durable(path) is True
    assert operations == ["unlink", "directory_sync"]


def test_delete_file_durable_missing_is_explicit_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_calls = 0

    def unexpected_sync(directory: Path) -> None:
        nonlocal sync_calls
        sync_calls += 1

    monkeypatch.setattr(storage, "_sync_directory", unexpected_sync)

    assert delete_file_durable(tmp_path / "missing.json") is False
    assert sync_calls == 0


def test_delete_file_durable_reports_visible_uncertain_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("state", encoding="utf-8")
    sync_error = OSError("directory sync unavailable")

    def fail_sync(directory: Path) -> None:
        assert directory == tmp_path
        assert not path.exists()
        raise sync_error

    monkeypatch.setattr(storage, "_sync_directory", fail_sync)

    with pytest.raises(AtomicDeleteDurabilityError) as captured:
        delete_file_durable(path)

    assert captured.value.deleted_path == path
    assert captured.value.sync_error is sync_error
    assert captured.value.__cause__ is sync_error
    assert not path.exists()


def test_file_collection_delete_propagates_uncertain_durability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = FileStorageBackend(
        tmp_path / "private",
        project_root=tmp_path,
    ).collection("memory_entries")
    collection.put("record", {"id": "record"})

    def fail_sync(directory: Path) -> None:
        raise OSError(f"cannot sync {directory.name}")

    monkeypatch.setattr(storage, "_sync_directory", fail_sync)

    with pytest.raises(AtomicDeleteDurabilityError):
        collection.delete("record")

    assert collection.get("record") is None


def test_write_text_atomic_syncs_content_before_replace_and_directory_after(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    operations: list[str] = []
    original_write_text = Path.write_text
    original_replace = Path.replace

    def record_write(
        target: Path,
        text: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        operations.append("write")
        return original_write_text(
            target,
            text,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    def record_file_sync(target: Path) -> None:
        assert target.suffix == ".tmp"
        operations.append("file_sync")

    def record_replace(source: Path, target: Path) -> Path:
        operations.append("replace")
        return original_replace(source, target)

    def record_directory_sync(target: Path) -> None:
        assert target == path.parent
        operations.append("directory_sync")

    monkeypatch.setattr(Path, "write_text", record_write)
    monkeypatch.setattr(storage, "_sync_file", record_file_sync)
    monkeypatch.setattr(Path, "replace", record_replace)
    monkeypatch.setattr(storage, "_sync_directory", record_directory_sync)

    write_text_atomic(path, "durable")

    assert operations == [
        "write",
        "file_sync",
        "replace",
        "directory_sync",
    ]


def test_write_text_atomic_file_sync_failure_preserves_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")

    def fail_file_sync(target: Path) -> None:
        raise OSError(f"file sync failed: {target.name}")

    monkeypatch.setattr(storage, "_sync_file", fail_file_sync)

    with pytest.raises(OSError, match="file sync failed"):
        write_text_atomic(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert list(path.parent.glob("*.tmp")) == []


def test_write_text_atomic_directory_sync_failure_reports_visible_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")
    sync_error = OSError("directory sync failed")

    def fail_directory_sync(target: Path) -> None:
        raise sync_error

    monkeypatch.setattr(storage, "_sync_directory", fail_directory_sync)

    with pytest.raises(AtomicWriteDurabilityError) as captured:
        write_text_atomic(path, "new")

    error = captured.value
    assert error.destination_path == path
    assert error.sync_error is sync_error
    assert error.__cause__ is sync_error
    assert path.read_text(encoding="utf-8") == "new"
    assert list(path.parent.glob("*.tmp")) == []


def test_write_text_atomic_hardens_directory_and_file_before_content_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "private" / "traces" / "trace.json"
    path.parent.mkdir(parents=True, mode=0o755)
    path.parent.chmod(0o755)
    path.write_text("old", encoding="utf-8")
    path.chmod(0o644)
    original_write_text = Path.write_text
    temporary_modes: list[int] = []

    def capture_temporary_mode(
        target: Path,
        text: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if target.suffix == ".tmp":
            temporary_modes.append(stat.S_IMODE(target.stat().st_mode))
        return original_write_text(
            target,
            text,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "write_text", capture_temporary_mode)

    write_text_atomic(path, "private content")

    assert temporary_modes == [0o600]
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8") == "private content"


def test_private_file_boundary_rejects_non_file_without_chmod(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "private" / "not-a-file"
    invalid.mkdir(parents=True, mode=0o755)
    invalid.chmod(0o755)

    with pytest.raises(
        OSError,
        match="private file path must be a regular file",
    ):
        ensure_private_file(invalid)

    assert stat.S_IMODE(invalid.stat().st_mode) == 0o755


def test_write_json_atomic_rejects_invalid_value_before_touching_destination(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "state.json"
    write_json_atomic(path, {"value": "old"})

    with pytest.raises(TypeError, match="floats must be finite"):
        write_json_atomic(path, {"value": float("nan")})

    assert json.loads(path.read_text(encoding="utf-8")) == {"value": "old"}
    assert list(path.parent.glob("*.tmp")) == []


def test_write_text_atomic_failure_preserves_destination_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")
    original_replace = Path.replace

    def fail_destination_replace(
        source: Path,
        target: Path,
    ) -> Path:
        if target == path:
            raise OSError("replace failed")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_destination_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_text_atomic(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert list(path.parent.glob("*.tmp")) == []


def test_write_text_atomic_does_not_remove_unowned_temp_name_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")
    collision = path.with_name(f"{path.name}.collision.tmp")
    collision.write_text("not owned by this write", encoding="utf-8")
    monkeypatch.setattr(
        storage,
        "uuid4",
        lambda: SimpleNamespace(hex="collision"),
    )

    with pytest.raises(FileExistsError):
        write_text_atomic(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert collision.read_text(encoding="utf-8") == "not owned by this write"


def test_write_text_atomic_partial_write_failure_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")
    original_write_text = Path.write_text

    def fail_after_partial_write(
        target: Path,
        text: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        written = original_write_text(
            target,
            text,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )
        if target.suffix == ".tmp":
            raise OSError("write failed")
        return written

    monkeypatch.setattr(Path, "write_text", fail_after_partial_write)

    with pytest.raises(OSError, match="write failed"):
        write_text_atomic(path, "partial")

    assert path.read_text(encoding="utf-8") == "old"
    assert list(path.parent.glob("*.tmp")) == []


def test_write_text_atomic_interruption_cleans_owned_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")

    def interrupt_write(
        target: Path,
        text: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_text", interrupt_write)

    with pytest.raises(KeyboardInterrupt):
        write_text_atomic(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert list(path.parent.glob("*.tmp")) == []


def test_write_text_atomic_retains_replace_and_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")
    original_replace = Path.replace
    original_unlink = Path.unlink

    def fail_destination_replace(
        source: Path,
        target: Path,
    ) -> Path:
        if target == path:
            raise OSError("replace failed")
        return original_replace(source, target)

    def fail_temp_cleanup(
        target: Path,
        missing_ok: bool = False,
    ) -> None:
        if target.suffix == ".tmp":
            raise PermissionError("cleanup failed")
        original_unlink(target, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "replace", fail_destination_replace)
    monkeypatch.setattr(Path, "unlink", fail_temp_cleanup)

    with pytest.raises(AtomicWriteCleanupError) as captured:
        write_text_atomic(path, "new")

    error = captured.value
    assert str(error.primary_error) == "replace failed"
    assert str(error.cleanup_error) == "cleanup failed"
    assert error.__cause__ is error.primary_error
    assert error.temporary_path.parent == path.parent
    assert error.temporary_path.name.startswith(f"{path.name}.")
    assert error.temporary_path.suffix == ".tmp"
    assert error.temporary_path.read_text(encoding="utf-8") == "new"
    assert path.read_text(encoding="utf-8") == "old"


def test_write_text_atomic_concurrent_writers_do_not_share_temp_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    values = [f"value-{index}-" + ("x" * 10_000) for index in range(8)]
    barrier = threading.Barrier(len(values))
    errors: list[BaseException] = []

    def write_value(value: str) -> None:
        try:
            barrier.wait()
            write_text_atomic(path, value)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=write_value, args=(value,))
        for value in values
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert path.read_text(encoding="utf-8") in values
    assert list(path.parent.glob("*.tmp")) == []
