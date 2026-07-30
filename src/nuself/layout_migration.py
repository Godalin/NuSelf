"""Explicit publication of a legacy checkout-local NuSelf layout."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import shutil
import stat
from collections.abc import Generator
from uuid import uuid4

from nuself.private_fs import (
    PRIVATE_DIRECTORY_MODE,
    PRIVATE_FILE_MODE,
    ensure_managed_directory,
)
from nuself.scope import NuSelfScope
from nuself.storage import (
    COLLECTION_NAMES,
    FileStorageBackend,
    auto_backend,
    open_sqlite_backend,
    reset_default_backend,
)
from nuself.storage_sqlite import SqliteStorageBackend

_SQLITE_TRANSIENT_SUFFIXES = ("-wal", "-shm", "-journal")
_TRANSIENT_FILENAMES = frozenset(
    {
        ".storage-authority.lock",
        "nuself.lock",
        "nuself.pid",
        "nuself.sock",
    }
)


class LayoutMigrationError(RuntimeError):
    """Raised before a legacy layout can become the selected authority."""


def migrate_legacy_layout(
    source: Path,
    target_scope: NuSelfScope,
) -> Path:
    """Validate, stage, and atomically publish one legacy layout."""

    source_root = source.expanduser().absolute()
    target_root = target_scope.root
    _validate_source_tree(source_root)
    target_root.parent.mkdir(parents=True, exist_ok=True)
    with _target_migration_lease(target_root):
        if target_root.exists() or target_root.is_symlink():
            raise FileExistsError(
                f"migration target already exists: {target_root}"
            )
        stage = target_root.with_name(
            f".{target_root.name}.migrating-{uuid4().hex}"
        )
        published = False
        try:
            ensure_managed_directory(stage, stage)
            _copy_legacy_tree(source_root, stage)
            _validate_staged_authority(stage)
            os.replace(stage, target_root)
            published = True
            _sync_directory(target_root.parent)
            return target_root
        finally:
            reset_default_backend(stage)
            if not published and stage.exists() and not stage.is_symlink():
                shutil.rmtree(stage)


def _validate_source_tree(source: Path) -> None:
    try:
        source_mode = source.lstat().st_mode
    except FileNotFoundError as exc:
        raise LayoutMigrationError(
            f"legacy layout does not exist: {source}"
        ) from exc
    if not stat.S_ISDIR(source_mode):
        raise LayoutMigrationError(
            f"legacy layout must be an actual directory: {source}"
        )
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        for name in (*directories, *files):
            path = root_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise LayoutMigrationError(
                    f"legacy layout contains a symlink: {path}"
                )
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise LayoutMigrationError(
                    f"legacy layout contains a special file: {path}"
                )


def _copy_legacy_tree(source: Path, stage: Path) -> None:
    source_database = source / "nuself.sqlite"
    for root, directories, files in os.walk(source):
        relative_root = Path(root).relative_to(source)
        destination_root = stage / relative_root
        ensure_managed_directory(stage, destination_root)
        for directory in directories:
            ensure_managed_directory(stage, destination_root / directory)
        for name in files:
            source_path = Path(root) / name
            if name in _TRANSIENT_FILENAMES or name.endswith(".lock"):
                continue
            if source_path == source_database:
                continue
            if (
                source_path.parent == source
                and any(
                    name == f"nuself.sqlite{suffix}"
                    for suffix in _SQLITE_TRANSIENT_SUFFIXES
                )
            ):
                continue
            destination = destination_root / name
            shutil.copyfile(source_path, destination)
            destination.chmod(PRIVATE_FILE_MODE)

    if source_database.is_file():
        source_backend = open_sqlite_backend(db_path=source_database)
        try:
            source_backend.backup_to(
                stage / "nuself.sqlite",
                managed=True,
            )
        finally:
            source_backend.close()


def _validate_staged_authority(stage: Path) -> None:
    for root, directories, files in os.walk(stage):
        Path(root).chmod(PRIVATE_DIRECTORY_MODE)
        for directory in directories:
            (Path(root) / directory).chmod(PRIVATE_DIRECTORY_MODE)
        for file in files:
            (Path(root) / file).chmod(PRIVATE_FILE_MODE)
    backend = auto_backend(stage)
    try:
        for name in COLLECTION_NAMES:
            backend.collection(name).list()
    finally:
        if isinstance(backend, FileStorageBackend | SqliteStorageBackend):
            backend.close()
        else:
            raise TypeError("unknown staged storage backend")
        reset_default_backend(stage)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _target_migration_lease(target: Path) -> Generator[None]:
    lock_path = target.with_name(f"{target.name}.migration.lock")
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, PRIVATE_FILE_MODE)
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
