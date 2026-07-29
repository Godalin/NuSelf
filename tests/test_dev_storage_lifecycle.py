from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from nuself.cli.commands.dev import (
    handle_dev_db_schema,
    handle_dev_migrate,
    handle_dev_storage,
)
from nuself.storage import FileStorageBackend
from nuself.storage_sqlite import SqliteStorageBackend


def test_dev_migrate_uses_atomic_migration_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "private" / "migration.sqlite"
    calls: list[tuple[Path | None, Path | None]] = []

    def migrate(
        project_root: Path | None,
        *,
        db_path: Path | None = None,
    ) -> tuple[dict[str, int], Path]:
        calls.append((project_root, db_path))
        return {"memory_entries": 2}, destination

    monkeypatch.setattr(
        "nuself.cli.commands.dev.migrate_file_backend_atomically",
        migrate,
    )

    assert handle_dev_migrate(
        argparse.Namespace(
            project_root=tmp_path,
            db=destination,
        )
    ) == 0
    assert calls == [(tmp_path, destination)]
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
                db=tmp_path / "migration.sqlite",
            )
        )

    assert captured.value is primary


def test_dev_db_schema_closes_backend_on_early_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SqliteStorageBackend(
        tmp_path / "schema.sqlite",
        project_root=tmp_path,
    )
    monkeypatch.setattr(backend, "collection_names", lambda: ())

    def create_backend(
        project_root: Path | None,
        *,
        db_path: Path | None = None,
    ) -> SqliteStorageBackend:
        del project_root, db_path
        return backend

    monkeypatch.setattr(
        "nuself.cli.commands.dev.create_sqlite_backend",
        create_backend,
    )

    assert handle_dev_db_schema(
        argparse.Namespace(project_root=tmp_path)
    ) == 0
    assert getattr(backend, "_closed") is True


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
