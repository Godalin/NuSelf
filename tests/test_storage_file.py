import json
from pathlib import Path
import stat
import threading
from types import SimpleNamespace

import pytest

import nuself.storage as storage
from nuself.logs import read_log_events
from nuself.storage import (
    AtomicWriteCleanupError,
    FileStorageBackend,
    write_json_atomic,
    write_text_atomic,
)


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


def test_write_text_atomic_replaces_complete_destination(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "state.txt"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")

    write_text_atomic(path, "new\n")

    assert path.read_text(encoding="utf-8") == "new\n"
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
