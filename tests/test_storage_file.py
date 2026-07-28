import json
from pathlib import Path

import pytest

from nuself.logs import read_log_events
from nuself.storage import FileStorageBackend, write_text_atomic


@pytest.mark.parametrize(
    ("raw", "error_type"),
    [
        ("{", json.JSONDecodeError),
        ("[]", ValueError),
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
