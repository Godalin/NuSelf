from __future__ import annotations

# pyright: reportPrivateUsage=false

import argparse
from pathlib import Path

import pytest

from nuself.cli import build_parser, main
from nuself.cli.commands.dev import (
    handle_dev_db_schema,
    handle_dev_migrate,
    handle_dev_storage,
)
from nuself.storage import (
    FileStorageBackend,
    auto_backend,
    create_file_backend,
)
from nuself.storage_sqlite import SqliteStorageBackend


def test_dev_migrate_uses_atomic_migration_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "private" / "migration.sqlite"
    calls: list[Path | None] = []

    def migrate(
        project_root: Path | None,
    ) -> tuple[dict[str, int], Path]:
        calls.append(project_root)
        return {"memory_entries": 2}, destination

    monkeypatch.setattr(
        "nuself.cli.commands.dev.migrate_file_backend_atomically",
        migrate,
    )

    assert handle_dev_migrate(
        argparse.Namespace(
            project_root=tmp_path,
        )
    ) == 0
    assert calls == [tmp_path]
    assert "Migrated 2 items across 1 collections" in capsys.readouterr().out


def test_dev_migrate_propagates_atomic_migration_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = RuntimeError("migration failed")

    def fail_migration(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise primary

    monkeypatch.setattr(
        "nuself.cli.commands.dev.migrate_file_backend_atomically",
        fail_migration,
    )

    with pytest.raises(RuntimeError) as captured:
        handle_dev_migrate(
            argparse.Namespace(
                project_root=tmp_path,
            )
        )

    assert captured.value is primary


def test_dev_migrate_rejects_non_authoritative_db_destination() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            ["dev", "migrate", "--db", "private/archive.sqlite"]
        )

    assert captured.value.code == 2


def test_dev_db_schema_reuses_default_backend_without_closing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.storage import _create_sqlite_backend

    backend = _create_sqlite_backend(
        tmp_path,
        db_path=tmp_path / "schema.sqlite",
    )
    monkeypatch.setattr(backend, "collection_names", lambda: ())

    def default_backend(
        _project_root: Path | None,
    ) -> SqliteStorageBackend:
        return backend

    monkeypatch.setattr(
        "nuself.cli.commands.dev.get_default_backend",
        default_backend,
    )

    assert handle_dev_db_schema(
        argparse.Namespace(project_root=tmp_path)
    ) == 0
    assert getattr(backend, "_closed") is False
    backend.close()


def test_dev_db_schema_cannot_publish_sqlite_authority(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = create_file_backend(tmp_path)
    source.collection("memory_entries").put(
        "legacy",
        {"id": "legacy", "title": "Still authoritative"},
    )
    source.close()

    assert main(
        ["--project-root", str(tmp_path), "dev", "db-schema"]
    ) == 1

    assert "Run 'nuself dev migrate' first" in capsys.readouterr().err
    assert not (tmp_path / "private" / "nuself.sqlite").exists()
    reopened = auto_backend(tmp_path)
    assert isinstance(reopened, FileStorageBackend)
    try:
        assert reopened.collection("memory_entries").get("legacy") == {
            "id": "legacy",
            "title": "Still authoritative",
        }
    finally:
        reopened.close()


def test_dev_storage_reuses_default_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FileStorageBackend(tmp_path / "private")
    calls: list[Path | None] = []

    def default_backend(
        project_root: Path | None,
    ) -> FileStorageBackend:
        calls.append(project_root)
        return backend

    monkeypatch.setattr(
        "nuself.cli.commands.dev.get_default_backend",
        default_backend,
    )

    assert handle_dev_storage(
        argparse.Namespace(project_root=tmp_path)
    ) == 0
    assert calls == [tmp_path]
