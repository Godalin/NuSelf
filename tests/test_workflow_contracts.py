"""Static release-engineering contracts for GitHub Actions workflows."""

from __future__ import annotations

from pathlib import Path
import re


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
