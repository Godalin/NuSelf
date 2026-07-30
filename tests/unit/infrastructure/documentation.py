"""User-facing documentation structure and link contracts."""

from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[3]
README_LIMIT = 250
USER_DOCUMENTS = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "README.zh-CN.md",
    PROJECT_ROOT / "CONTRIBUTING.md",
    PROJECT_ROOT / "docs" / "configuration.md",
    PROJECT_ROOT / "docs" / "cli.md",
    PROJECT_ROOT / "docs" / "memory.md",
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_readmes_remain_concise_project_front_pages() -> None:
    english = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (PROJECT_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    assert len(english.splitlines()) <= README_LIMIT
    assert len(chinese.splitlines()) <= README_LIMIT

    for heading in (
        "## Status",
        "## Features",
        "## Quick Start",
        "## Common Workflows",
        "## Privacy And Storage",
        "## Current Limitations",
        "## Documentation",
    ):
        assert heading in english

    for heading in (
        "## 当前状态",
        "## 主要能力",
        "## 快速开始",
        "## 常用流程",
        "## 隐私与存储",
        "## 当前限制",
        "## 文档",
    ):
        assert heading in chinese


def test_user_document_local_links_resolve() -> None:
    missing: list[str] = []
    for document in USER_DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                missing.append(
                    f"{document.relative_to(PROJECT_ROOT)} -> {raw_target}"
                )

    assert not missing
