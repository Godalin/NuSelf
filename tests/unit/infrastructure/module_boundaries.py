"""Executable package dependency rules."""

from __future__ import annotations

import ast
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src" / "nuself"
_OUTER_ADAPTERS = ("nuself.cli", "nuself.daemon", "nuself.repl", "nuself.tui")
_DOMAIN_PACKAGES = (
    "memory",
    "notification",
    "persona",
    "profile",
    "reason",
    "reflection",
    "trace",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return tuple(imported)


def _from_imports(path: Path) -> tuple[tuple[str, str], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.extend(
                (node.module, alias.name) for alias in node.names
            )
    return tuple(imported)


def _package_files(package: str) -> tuple[Path, ...]:
    return tuple(sorted((_SOURCE_ROOT / package).rglob("*.py")))


def _violations(
    packages: tuple[str, ...],
    forbidden: tuple[str, ...],
) -> tuple[str, ...]:
    violations: list[str] = []
    for package in packages:
        for path in _package_files(package):
            for imported in _imports(path):
                if any(
                    imported == prefix or imported.startswith(f"{prefix}.")
                    for prefix in forbidden
                ):
                    violations.append(
                        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
                    )
    return tuple(violations)


def test_runtime_does_not_depend_on_adapters_or_domains() -> None:
    forbidden = _OUTER_ADAPTERS + ("nuself.agent",) + tuple(
        f"nuself.{package}" for package in _DOMAIN_PACKAGES
    )

    assert _violations(("runtime",), forbidden) == ()


def test_domains_do_not_depend_on_outer_adapters() -> None:
    assert _violations(_DOMAIN_PACKAGES, _OUTER_ADAPTERS) == ()


def test_agent_does_not_depend_on_process_or_terminal_adapters() -> None:
    assert _violations(("agent",), _OUTER_ADAPTERS) == ()


def test_chat_tool_runtime_does_not_compose_persistence() -> None:
    path = _SOURCE_ROOT / "agent" / "chat" / "tool_runtime.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
        (
            "nuself.application.reflection",
            "compose_reflection_repository",
        ),
    }

    assert {
        imported for imported in _from_imports(path) if imported in forbidden
    } == set()


def test_migrated_trace_package_does_not_resolve_authority() -> None:
    violations: list[str] = []
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    for path in _package_files("trace"):
        for imported in _from_imports(path):
            if imported in forbidden:
                violations.append(
                    f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
                )

    assert violations == []


def test_migrated_profile_package_does_not_resolve_authority() -> None:
    violations: list[str] = []
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    for path in _package_files("profile"):
        for imported in _from_imports(path):
            if imported in forbidden:
                violations.append(
                    f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
                )

    assert violations == []


def test_migrated_reason_repository_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "reason" / "repository.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
        for imported in _from_imports(path)
        if imported in forbidden
    ]

    assert violations == []


def test_reason_domain_does_not_import_application_composition() -> None:
    assert _violations(("reason",), ("nuself.application",)) == ()


def test_migrated_reflection_repository_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "reflection" / "repository.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
        for imported in _from_imports(path)
        if imported in forbidden
    ]

    assert violations == []


def test_reflection_domain_does_not_import_application_composition() -> None:
    assert _violations(("reflection",), ("nuself.application",)) == ()


def test_migrated_memory_repositories_do_not_resolve_authority() -> None:
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    paths = (
        _SOURCE_ROOT / "memory" / "curator_plan.py",
        _SOURCE_ROOT / "memory" / "repository.py",
        _SOURCE_ROOT / "memory" / "source_repository.py",
    )
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
        for path in paths
        for imported in _from_imports(path)
        if imported in forbidden
    ]

    assert violations == []


def test_migrated_persona_repository_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "persona" / "prompt_repo.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
        for imported in _from_imports(path)
        if imported in forbidden
    ]

    assert violations == []


def test_migrated_notification_outbox_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "notification" / "__init__.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
        for imported in _from_imports(path)
        if imported in forbidden
    ]

    assert violations == []


def test_remaining_persistence_stores_do_not_resolve_authority() -> None:
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    paths = (
        _SOURCE_ROOT / "persona" / "prompt_repo.py",
        _SOURCE_ROOT / "memory" / "curator_plan.py",
    )
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
        for path in paths
        for imported in _from_imports(path)
        if imported in forbidden
    ]

    assert violations == []


def test_memory_domain_does_not_import_application_composition() -> None:
    assert _violations(("memory",), ("nuself.application",)) == ()


def test_memory_persistence_depends_on_profile_port_not_adapter() -> None:
    paths = (
        _SOURCE_ROOT / "memory" / "repository.py",
        _SOURCE_ROOT / "memory" / "source_repository.py",
        _SOURCE_ROOT / "memory" / "query.py",
    )
    violations = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in paths
        if "nuself.profile.repository" in _imports(path)
    ]

    assert violations == []
