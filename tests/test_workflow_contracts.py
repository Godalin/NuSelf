"""Static release-engineering contracts for GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path
import re
import tomllib
from typing import cast


WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
FULL_SHA_ACTION = re.compile(
    r"^\s*(?:-\s*)?uses:\s+[^@\s]+@([0-9a-f]{40})"
    r"(?:\s+#\s+\S+)?\s*$",
    re.MULTILINE,
)
ACTIVE_ACTION = re.compile(
    r"^\s*(?:-\s*)?uses:\s+(\S+)",
    re.MULTILINE,
)


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_all_executable_actions_are_pinned_to_full_sha() -> None:
    for name in ("ci.yml", "release.yml"):
        workflow = _workflow(name)
        references = ACTIVE_ACTION.findall(workflow)
        pinned = FULL_SHA_ACTION.findall(workflow)
        assert references
        assert len(pinned) == len(references), references


def test_release_generates_checksums_and_build_provenance() -> None:
    release = _workflow("release.yml")

    assert "attestations: write" in release
    assert "id-token: write" in release
    assert "sha256sum * > SHA256SUMS" in release
    assert "uses: actions/attest@" in release
    assert 'subject-path: "dist/*"' in release
    assert "files: dist/*" in release


def test_ci_and_release_use_exact_locked_toolchain() -> None:
    for name in ("ci.yml", "release.yml"):
        workflow = _workflow(name)
        assert "python -m pip install uv==0.11.21" in workflow
        assert "uv sync --locked --group dev" in workflow
        assert "uv run --locked pyright --outputjson" in workflow
        assert "uvx pyright" not in workflow


def test_release_reruns_full_gate_with_complete_git_history() -> None:
    release = _workflow("release.yml")

    assert "fetch-depth: 0" in release
    assert 'python scripts/check_release.py --tag "${GITHUB_REF_NAME}"' in release
    assert "uv run --locked pyright --outputjson" in release
    assert "uv run --locked pytest -q" in release
    assert release.index("Verify release metadata") < release.index(
        "Build distributions"
    )


def test_project_pins_uv_and_pyright_exactly() -> None:
    root = WORKFLOWS.parent.parent
    data = cast(
        dict[str, object],
        tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        ),
    )
    tool = cast(dict[str, object], data["tool"])
    uv_config = cast(dict[str, object], tool["uv"])
    groups = cast(dict[str, object], data["dependency-groups"])
    dev = cast(list[object], groups["dev"])

    assert uv_config["required-version"] == "==0.11.21"
    assert "pyright==1.1.411" in dev
