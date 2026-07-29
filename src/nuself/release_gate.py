"""Release metadata consistency checks."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tomllib
from typing import cast


def check_release(root: Path, tag: str) -> None:
    """Require exact tag, package, runtime fallback, and changelog agreement."""

    if not tag.startswith("v") or len(tag) == 1:
        raise ValueError("release tag must have the form v<version>")
    version = tag[1:]
    raw = cast(
        dict[str, object],
        tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        ),
    )
    project = raw.get("project")
    if not isinstance(project, dict):
        raise ValueError("pyproject lacks project metadata")
    project_version = cast(dict[str, object], project).get("version")
    if project_version != version:
        raise ValueError("release tag and pyproject version differ")
    init_text = (root / "src" / "nuself" / "__init__.py").read_text(
        encoding="utf-8"
    )
    fallback = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    if fallback is None or fallback.group(1) != version:
        raise ValueError("runtime fallback and pyproject version differ")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.compile(
        rf"^## v{re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$",
        re.MULTILINE,
    )
    if heading.search(changelog) is None:
        raise ValueError("changelog lacks the dated release heading")


def check_release_git(
    root: Path,
    tag: str,
    *,
    main_ref: str = "refs/remotes/origin/main",
) -> None:
    """Require an annotated release tag whose commit belongs to main."""
    tag_ref = f"refs/tags/{tag}"
    object_type = _git_output(root, "cat-file", "-t", tag_ref)
    if object_type != "tag":
        raise ValueError("release tag must be an annotated tag object")
    commit = _git_output(root, "rev-list", "-n", "1", tag_ref)
    if not commit:
        raise ValueError("release tag does not peel to a commit")
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "merge-base",
            "--is-ancestor",
            commit,
            main_ref,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("release tag commit is not an ancestor of main")


def _git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            "release Git topology cannot be verified: "
            + result.stderr.strip()
        )
    return result.stdout.strip()
