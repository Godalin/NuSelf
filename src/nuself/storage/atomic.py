"""Durable private atomic file replacement."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from nuself.private_fs import create_private_file, ensure_private_directory
from nuself.runtime.messages import encode_json_value


class AtomicWriteCleanupError(RuntimeError):
    """An atomic write failed and its temporary artifact could not be removed."""

    def __init__(
        self,
        temporary_path: Path,
        *,
        primary_error: BaseException,
        cleanup_error: BaseException,
    ) -> None:
        super().__init__(
            "atomic write failed and temporary cleanup failed: "
            f"{temporary_path}"
        )
        self.temporary_path = temporary_path
        self.primary_error = primary_error
        self.cleanup_error = cleanup_error


class AtomicWriteDurabilityError(RuntimeError):
    """A replacement is visible but its directory entry may not be durable."""

    def __init__(
        self,
        destination_path: Path,
        *,
        sync_error: BaseException,
    ) -> None:
        super().__init__(
            "atomic destination replaced but directory synchronization failed: "
            f"{destination_path}"
        )
        self.destination_path = destination_path
        self.sync_error = sync_error


def write_text_atomic(path: Path, text: str) -> None:
    """Privately replace UTF-8 text without exposing partial destination data."""

    ensure_private_directory(path.parent)
    tmp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temporary_created = False
    try:
        create_private_file(tmp_path)
        temporary_created = True
        tmp_path.write_text(text, encoding="utf-8")
        sync_path(tmp_path)
        tmp_path.replace(path)
        temporary_created = False
        try:
            sync_path(path.parent)
        except BaseException as sync_error:
            raise AtomicWriteDurabilityError(
                path,
                sync_error=sync_error,
            ) from sync_error
    except BaseException as primary_error:
        if temporary_created:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            except BaseException as cleanup_error:
                raise AtomicWriteCleanupError(
                    tmp_path,
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
        raise


def sync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    encoded = encode_json_value(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    )
    write_text_atomic(
        path,
        encoded + "\n",
    )
