from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.release import check_release, check_release_git


def _write_release_metadata(
    root: Path,
    *,
    project_version: str = "0.3.0",
    fallback_version: str = "0.3.0",
    changelog_version: str = "0.3.0",
) -> None:
    (root / "src" / "nuself").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "nuself"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    (root / "src" / "nuself" / "__init__.py").write_text(
        f'__version__ = "{fallback_version}"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"## v{changelog_version} - 2026-07-29\n",
        encoding="utf-8",
    )


def test_release_gate_accepts_exact_metadata(tmp_path: Path) -> None:
    _write_release_metadata(tmp_path)

    check_release(tmp_path, "v0.3.0")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"project_version": "0.3.1"}, "pyproject"),
        ({"fallback_version": "0.3.1"}, "runtime fallback"),
        ({"changelog_version": "0.3.1"}, "changelog"),
    ],
)
def test_release_gate_rejects_metadata_mismatch(
    tmp_path: Path,
    overrides: dict[str, str],
    message: str,
) -> None:
    _write_release_metadata(tmp_path, **overrides)

    with pytest.raises(ValueError, match=message):
        check_release(tmp_path, "v0.3.0")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repository(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.name", "NuSelf Test")
    _git(root, "config", "user.email", "test@nuself.invalid")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "base")
    _git(root, "branch", "-M", "main")


def test_release_git_gate_accepts_annotated_tag_on_main(
    tmp_path: Path,
) -> None:
    _init_repository(tmp_path)
    _git(tmp_path, "tag", "-a", "v0.3.0", "-m", "Release 0.3.0")

    check_release_git(
        tmp_path,
        "v0.3.0",
        main_ref="refs/heads/main",
    )


def test_release_git_gate_rejects_lightweight_tag(
    tmp_path: Path,
) -> None:
    _init_repository(tmp_path)
    _git(tmp_path, "tag", "v0.3.0")

    with pytest.raises(ValueError, match="annotated"):
        check_release_git(
            tmp_path,
            "v0.3.0",
            main_ref="refs/heads/main",
        )


def test_release_git_gate_rejects_tag_outside_main(
    tmp_path: Path,
) -> None:
    _init_repository(tmp_path)
    _git(tmp_path, "switch", "-c", "release-candidate")
    (tmp_path / "tracked.txt").write_text("release\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "unmerged release")
    _git(tmp_path, "tag", "-a", "v0.3.0", "-m", "Release 0.3.0")

    with pytest.raises(ValueError, match="ancestor of main"):
        check_release_git(
            tmp_path,
            "v0.3.0",
            main_ref="refs/heads/main",
        )
