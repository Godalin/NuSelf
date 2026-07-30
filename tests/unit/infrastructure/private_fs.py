from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path
import stat

import pytest

from nuself.private_fs import ensure_private_directory
from nuself.storage import (
    _create_sqlite_backend,
)


def _create_sqlite_at_project(root: Path | None) -> object:
    if root is None:
        raise ValueError("test project root is required")
    return _create_sqlite_backend(
        root,
        db_path=root / "nuself.sqlite",
    )


@pytest.mark.parametrize("relative", [Path(), Path("runtime"), Path("logs/jobs")])
def test_managed_private_tree_rejects_symlink_without_external_changes(
    tmp_path: Path,
    relative: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external"
    external.mkdir(mode=0o755)
    external.chmod(0o755)
    sentinel = external / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    private = project / "private"
    private.symlink_to(external, target_is_directory=True)

    with pytest.raises(OSError, match="actual directory"):
        ensure_private_directory(private / relative)

    assert private.is_symlink()
    assert stat.S_IMODE(external.stat().st_mode) == 0o755
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(external.iterdir()) == [sentinel]


def test_storage_rejects_redirected_private_root_before_writes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external"
    external.mkdir(mode=0o755)
    external.chmod(0o755)
    authority = project / ".nuself"
    authority.symlink_to(
        external,
        target_is_directory=True,
    )

    with pytest.raises(OSError, match="actual directory"):
        _create_sqlite_at_project(authority)

    assert stat.S_IMODE(external.stat().st_mode) == 0o755
    assert list(external.iterdir()) == []
