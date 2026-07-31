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


def test_conversation_runtime_does_not_compose_authority() -> None:
    path = _SOURCE_ROOT / "agent" / "chat" / "runtime.py"
    forbidden_prefixes = ("nuself.application", "nuself.storage")
    assert [
        imported
        for imported in _imports(path)
        if imported.startswith(forbidden_prefixes)
    ] == []


def test_thread_store_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "agent" / "chat" / "thread.py"
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
    }
    assert {
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


def test_persona_definition_loader_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "persona" / "definition.py"
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
    }
    assert [
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    ] == []


def test_chat_tool_collection_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "agent" / "tools" / "__init__.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
        ("nuself.application", "compose_trace_services"),
    }

    assert {
        imported for imported in _from_imports(path) if imported in forbidden
    } == set()


def test_process_surfaces_use_application_chat_factory() -> None:
    paths = (
        _SOURCE_ROOT / "cli" / "chat.py",
        _SOURCE_ROOT / "daemon" / "state.py",
    )

    forbidden = {
        "nuself.agent.chat",
        "nuself.memory.curator",
    }

    assert all(
        not forbidden.intersection(_imports(path))
        for path in paths
    )


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


def test_reflection_orchestration_does_not_resolve_authority() -> None:
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    paths = (
        _SOURCE_ROOT / "reflection" / "scheduler.py",
        _SOURCE_ROOT / "reflection" / "organizer.py",
        _SOURCE_ROOT / "reflection" / "service.py",
    )
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {imported}"
        for path in paths
        for imported in _from_imports(path)
        if imported in forbidden
    ]

    assert violations == []


def test_reflection_schedule_state_is_not_defined_by_scheduler() -> None:
    scheduler = ast.parse(
        (_SOURCE_ROOT / "reflection" / "scheduler.py").read_text(
            encoding="utf-8"
        )
    )
    classes = {
        node.name
        for node in scheduler.body
        if isinstance(node, ast.ClassDef)
    }

    assert "ReflectionScheduleState" not in classes
    assert (
        _SOURCE_ROOT / "reflection" / "schedule_state.py"
    ).is_file()


def test_reflection_relevance_is_a_separate_responsibility() -> None:
    scheduler = ast.parse(
        (_SOURCE_ROOT / "reflection" / "scheduler.py").read_text(
            encoding="utf-8"
        )
    )
    public_classes = {
        node.name
        for node in scheduler.body
        if isinstance(node, ast.ClassDef)
        and not node.name.startswith("_")
    }

    assert "LLMRelevanceGate" not in public_classes
    assert "RelevanceScoreOutput" not in public_classes
    assert (
        _SOURCE_ROOT / "reflection" / "relevance.py"
    ).is_file()


def test_reflection_candidates_depend_on_thread_context_port() -> None:
    path = _SOURCE_ROOT / "reflection" / "candidates.py"

    assert not {
        imported
        for imported in _imports(path)
        if imported == "nuself.agent.chat"
        or imported.startswith("nuself.agent.chat.")
    }


def test_reflection_service_does_not_compose_infrastructure() -> None:
    path = _SOURCE_ROOT / "reflection" / "service.py"
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
        ("nuself.reason.service", "ReasonService"),
        ("nuself.trace.repository", "TraceRepository"),
    }
    assert [
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    ] == []


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


def test_persona_definition_loading_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "persona" / "definition.py"
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
    }
    assert {
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


def test_persona_tools_do_not_resolve_or_compose_authority() -> None:
    path = _SOURCE_ROOT / "persona" / "tools.py"
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
        ("nuself.application", "compose_trace_services"),
    }
    assert {
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


def test_reason_advancement_does_not_resolve_or_compose_authority() -> None:
    paths = (
        _SOURCE_ROOT / "reason" / "advancer.py",
        _SOURCE_ROOT / "reason" / "scheduler.py",
    )
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
        ("nuself.application", "compose_reason_service"),
    }
    assert {
        (path.relative_to(_SOURCE_ROOT), imported)
        for path in paths
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


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


def test_notification_delivery_is_not_implemented_in_package_root() -> None:
    root = ast.parse(
        (_SOURCE_ROOT / "notification" / "__init__.py").read_text(
            encoding="utf-8"
        )
    )
    root_classes = {
        node.name for node in root.body if isinstance(node, ast.ClassDef)
    }

    assert "NotificationDeliveryLoop" not in root_classes
    assert (
        _SOURCE_ROOT / "notification" / "delivery.py"
    ).is_file()


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


def test_memory_intake_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "memory" / "intake.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }

    assert {
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


def test_memory_optimizer_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "memory" / "optimizer.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    assert {
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


def test_memory_curator_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "memory" / "curator.py"
    forbidden = {
        ("nuself.storage", "get_default_backend"),
        ("nuself.config", "runtime_paths"),
    }
    assert {
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


def test_reason_service_does_not_compose_infrastructure() -> None:
    path = _SOURCE_ROOT / "reason" / "service.py"
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
        ("nuself.trace.repository", "TraceRepository"),
    }
    assert [
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    ] == []


def test_reason_consumers_require_injected_service() -> None:
    for relative in ("reason/output.py", "reason/scheduler.py"):
        source = (_SOURCE_ROOT / relative).read_text(encoding="utf-8")
        assert "reason_service or ReasonService" not in source
        assert "service or ReasonService" not in source


def test_memory_curator_contract_is_separate_from_orchestration() -> None:
    source = (_SOURCE_ROOT / "memory" / "curator.py").read_text(
        encoding="utf-8"
    )
    for declaration in (
        "class MemoryCuratorSettings",
        "class MemoryCuratorCursor",
        "class MemoryCuratorResult",
        "class CuratorActionsOutput",
    ):
        assert declaration not in source


def test_conversation_runtime_does_not_resolve_authority() -> None:
    path = _SOURCE_ROOT / "agent" / "chat" / "runtime.py"
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "get_default_backend"),
    }
    assert {
        imported
        for imported in _from_imports(path)
        if imported in forbidden
    } == set()


def test_log_warning_contracts_are_separate_from_log_engine() -> None:
    source = (_SOURCE_ROOT / "logs.py").read_text(encoding="utf-8")
    assert "def _build_log_terminal_warning_registry" not in source
    assert "runtime.log_warning_contracts" in source


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
