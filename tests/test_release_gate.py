from __future__ import annotations

from pathlib import Path

import pytest

from nuself.release_gate import check_release


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
