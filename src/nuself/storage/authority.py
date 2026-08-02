"""Canonical SQLite authority selection and creation lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from nuself.config.settings import runtime_paths
from nuself.private_fs import create_private_file, ensure_private_directory
from nuself.storage.atomic import (
    AtomicWriteCleanupError,
    sync_path,
)
from nuself.storage.contract import ClosableStorageBackend

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nuself.storage.sqlite import SqliteStorageBackend


class SqliteStorageAuthorityError(RuntimeError):
    """The selected SQLite authority could not be opened or initialized."""


def open_sqlite_backend(
    project_root: Path | None = None, *, db_path: Path | None = None
) -> SqliteStorageBackend:
    """Open an existing SQLite backend without creating its database."""
    from nuself.storage.sqlite import SqliteStorageBackend
    paths = runtime_paths(project_root)
    canonical = paths.authority_root / "nuself.sqlite"
    path = db_path if db_path is not None else canonical
    managed = path.absolute() == canonical.absolute()
    return SqliteStorageBackend(
        path,
        project_root=paths.authority_root,
        _managed=managed,
    )


def _create_sqlite_backend(
    project_root: Path | None = None,
    *,
    db_path: Path,
) -> SqliteStorageBackend:
    """Create one unpublished SQLite database for atomic migration."""
    create_private_file(db_path)
    from nuself.storage.sqlite import SqliteStorageBackend

    return SqliteStorageBackend(
        db_path,
        project_root=project_root,
        _initialize=True,
        _managed=True,
        _truncate_on_close=True,
    )


def auto_backend(project_root: Path | None = None) -> ClosableStorageBackend:
    """Open or atomically initialize the selected SQLite authority."""
    paths = runtime_paths(project_root)
    db_path = paths.authority_root / "nuself.sqlite"
    if db_path.exists() or db_path.is_symlink():
        return open_sqlite_backend(project_root=project_root)
    ensure_private_directory(db_path.parent)
    from nuself.storage.sqlite import sqlite_schema_lease

    with sqlite_schema_lease(db_path, managed=True):
        if not (db_path.exists() or db_path.is_symlink()):
            _initialize_sqlite_authority(paths.authority_root)
    if db_path.exists() or db_path.is_symlink():
        return open_sqlite_backend(project_root=project_root)
    raise SqliteStorageAuthorityError(
        "SQLite authority initialization did not publish a database"
    )


def _initialize_sqlite_authority(project_root: Path) -> Path:
    paths = runtime_paths(project_root)
    destination = paths.database_file
    ensure_private_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    temporary = destination.with_name(
        f"{destination.name}.initializing-{uuid4().hex}"
    )
    backend: SqliteStorageBackend | None = None
    published = False
    try:
        backend = _create_sqlite_backend(
            paths.authority_root,
            db_path=temporary,
        )
        backend.close()
        backend = None
        _remove_sqlite_migration_sidecars(temporary)
        sync_path(temporary)
        os.replace(temporary, destination)
        published = True
        sync_path(destination.parent)
        return destination
    except BaseException as primary_error:
        if backend is not None:
            try:
                backend.close()
            except BaseException as cleanup_error:
                raise AtomicWriteCleanupError(
                    temporary,
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
        if not published:
            try:
                _remove_sqlite_migration_artifacts(temporary)
            except BaseException as cleanup_error:
                raise AtomicWriteCleanupError(
                    temporary,
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
        raise


def _remove_sqlite_migration_sidecars(database: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        database.with_name(f"{database.name}{suffix}").unlink(
            missing_ok=True
        )
    database.with_name(f"{database.name}.schema.lock").unlink(
        missing_ok=True
    )


def _remove_sqlite_migration_artifacts(database: Path) -> None:
    database.unlink(missing_ok=True)
    _remove_sqlite_migration_sidecars(database)
