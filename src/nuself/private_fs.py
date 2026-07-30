"""Owner-only filesystem primitives for NuSelf-managed private state."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import stat


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_directory(path: Path) -> None:
    """Create or harden one NuSelf-owned directory."""

    absolute = path.absolute()
    private_root = next(
        (
            candidate
            for candidate in (absolute, *absolute.parents)
            if (
                candidate.name == "private"
                and candidate.parent != Path(candidate.anchor)
            )
        ),
        None,
    )
    if private_root is None:
        _ensure_single_private_directory(absolute)
        return
    _ensure_managed_private_tree(private_root, absolute)


def _ensure_managed_private_tree(
    private_root: Path,
    destination: Path,
) -> None:
    """Create one private descendant without following managed symlinks."""

    private_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        private_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    except FileExistsError:
        pass
    handle = _open_directory_nofollow(private_root)
    try:
        os.fchmod(handle, PRIVATE_DIRECTORY_MODE)
        current = private_root
        for component in destination.relative_to(private_root).parts:
            try:
                os.mkdir(
                    component,
                    mode=PRIVATE_DIRECTORY_MODE,
                    dir_fd=handle,
                )
            except FileExistsError:
                pass
            child_path = current / component
            child_handle = _open_directory_nofollow(
                Path(component),
                dir_fd=handle,
                display_path=child_path,
            )
            os.close(handle)
            handle = child_handle
            current = child_path
            os.fchmod(handle, PRIVATE_DIRECTORY_MODE)
    finally:
        os.close(handle)


def _ensure_single_private_directory(path: Path) -> None:
    path.mkdir(
        mode=PRIVATE_DIRECTORY_MODE,
        parents=True,
        exist_ok=True,
    )
    handle = _open_directory_nofollow(path)
    try:
        os.fchmod(handle, PRIVATE_DIRECTORY_MODE)
    finally:
        os.close(handle)


def _open_directory_nofollow(
    path: Path,
    *,
    dir_fd: int | None = None,
    display_path: Path | None = None,
) -> int:
    try:
        return os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=dir_fd,
        )
    except OSError as exc:
        if exc.errno not in {errno.ELOOP, errno.ENOTDIR}:
            raise
        rejected = display_path or path
        raise OSError(
            errno.EINVAL,
            "managed private directory path must be an actual directory",
            rejected,
        ) from exc


def create_private_file(path: Path) -> None:
    """Exclusively create one empty owner-only file."""

    ensure_private_directory(path.parent)
    path.touch(mode=PRIVATE_FILE_MODE, exist_ok=False)
    path.chmod(PRIVATE_FILE_MODE)


def ensure_private_file(path: Path) -> None:
    """Create or harden one NuSelf-owned file."""

    ensure_private_directory(path.parent)
    try:
        create_private_file(path)
    except FileExistsError:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise OSError(
                errno.EINVAL,
                "private file path must be a regular file",
                path,
            )
        path.chmod(PRIVATE_FILE_MODE)


def harden_private_file(path: Path) -> None:
    """Require and harden one existing NuSelf-owned regular file."""

    require_private_file(path)
    path.chmod(PRIVATE_FILE_MODE)


def require_private_file(path: Path) -> None:
    """Require one existing regular file without changing it."""

    if not stat.S_ISREG(path.lstat().st_mode):
        raise OSError(
            errno.EINVAL,
            "private file path must be a regular file",
            path,
        )
