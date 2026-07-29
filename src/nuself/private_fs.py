"""Owner-only filesystem primitives for NuSelf-managed private state."""

from __future__ import annotations

import errno
from pathlib import Path
import stat


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_directory(path: Path) -> None:
    """Create or harden one NuSelf-owned directory."""

    path.mkdir(
        mode=PRIVATE_DIRECTORY_MODE,
        parents=True,
        exist_ok=True,
    )
    path.chmod(PRIVATE_DIRECTORY_MODE)


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

    if not stat.S_ISREG(path.lstat().st_mode):
        raise OSError(
            errno.EINVAL,
            "private file path must be a regular file",
            path,
        )
    path.chmod(PRIVATE_FILE_MODE)
