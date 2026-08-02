"""Executable package dependency rules for the current architecture."""

from __future__ import annotations

import ast
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src" / "nuself"
_OUTER_ADAPTERS = ("nuself.cli", "nuself.daemon", "nuself.tui")
_DOMAIN_PACKAGES = (
    "memory",
    "notification",
    "persona",
    "profile",
    "reason",
    "reflection",
    "trace",
)
_LEGACY_STATIC_TYPING_NAMES = {
    "Generic",
    "ParamSpec",
    "TypeAlias",
    "TypeVar",
    "TypeVarTuple",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> tuple[str, ...]:
    imported: list[str] = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return tuple(imported)


def _from_imports(path: Path) -> tuple[tuple[str, str], ...]:
    imported: list[tuple[str, str]] = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.extend((node.module, alias.name) for alias in node.names)
    return tuple(imported)


def _package_files(*packages: str) -> tuple[Path, ...]:
    return tuple(
        path
        for package in packages
        for path in sorted((_SOURCE_ROOT / package).rglob("*.py"))
    )


def _module_matches(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in prefixes
    )


def _import_violations(
    packages: tuple[str, ...],
    forbidden: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        f"{path.relative_to(_SOURCE_ROOT)} -> {module}"
        for path in _package_files(*packages)
        for module in _imports(path)
        if _module_matches(module, forbidden)
    )


def _class_method(
    path: Path,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef:
    return next(
        node
        for class_node in _tree(path).body
        if isinstance(class_node, ast.ClassDef)
        and class_node.name == class_name
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def test_source_uses_native_generic_and_alias_syntax() -> None:
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {name}"
        for path in _SOURCE_ROOT.rglob("*.py")
        for module, name in _from_imports(path)
        if module == "typing" and name in _LEGACY_STATIC_TYPING_NAMES
    ]
    assert violations == []


def test_package_dependency_matrix() -> None:
    rules = (
        (
            ("runtime",),
            _OUTER_ADAPTERS
            + ("nuself.agent",)
            + tuple(f"nuself.{package}" for package in _DOMAIN_PACKAGES),
        ),
        (_DOMAIN_PACKAGES, _OUTER_ADAPTERS),
        (("agent",), _OUTER_ADAPTERS),
        (("application",), ("nuself.tui",)),
        (("memory",), ("nuself.application", "nuself.conversation")),
        (("reason", "reflection"), ("nuself.application",)),
        (("persona",), ("nuself.memory",)),
    )
    violations = [
        violation
        for packages, forbidden in rules
        for violation in _import_violations(packages, forbidden)
    ]
    assert violations == []


def test_domain_packages_do_not_resolve_storage_authority() -> None:
    allowed = {"notification/eval.py"}
    forbidden = {
        ("nuself.config", "runtime_paths"),
        ("nuself.storage", "auto_backend"),
    }
    violations = [
        f"{relative} -> {module}.{name}"
        for path in _package_files(*_DOMAIN_PACKAGES)
        if (relative := str(path.relative_to(_SOURCE_ROOT))) not in allowed
        for module, name in _from_imports(path)
        if (module, name) in forbidden
    ]
    assert violations == []


def test_package_roots_are_import_light() -> None:
    roots = _DOMAIN_PACKAGES + ("runtime", "application")
    violations = [
        str(path.relative_to(_SOURCE_ROOT))
        for package in roots
        if _imports(path := _SOURCE_ROOT / package / "__init__.py")
    ]
    if _imports(_SOURCE_ROOT / "agent" / "chat" / "__init__.py"):
        violations.append("agent/chat/__init__.py")
    assert violations == []


def test_process_adapters_only_open_storage_for_infrastructure_commands() -> None:
    allowed = {
        "cli/commands/dev.py",
        "cli/commands/pack.py",
        "cli/commands/scope.py",
    }
    violations = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in _package_files("cli")
        if ("nuself.storage", "auto_backend") in _from_imports(path)
        and str(path.relative_to(_SOURCE_ROOT)) not in allowed
    ]
    assert violations == []


def test_langchain_tool_materialization_has_one_owner() -> None:
    owners = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in _SOURCE_ROOT.rglob("*.py")
        if any(
            isinstance(node, ast.Attribute)
            and node.attr == "from_function"
            and isinstance(node.value, ast.Name)
            and node.value.id == "StructuredTool"
            for node in ast.walk(_tree(path))
        )
    ]
    assert owners == ["agent/tools/decorated.py"]


def test_chat_uses_framework_agent_and_bounded_composition() -> None:
    engine = _SOURCE_ROOT / "agent" / "chat" / "engine.py"
    response = _SOURCE_ROOT / "agent" / "chat" / "response.py"
    tool_runtime = _SOURCE_ROOT / "agent" / "chat" / "tool_runtime.py"

    assert "langgraph.graph" not in _imports(engine)
    assert ("langchain.agents", "create_agent") in _from_imports(response)

    def collaborator_count(node: ast.FunctionDef) -> int:
        return (
            len(node.args.posonlyargs)
            + len(node.args.args)
            + len(node.args.kwonlyargs)
            - 1
        )

    assert collaborator_count(
        _class_method(engine, "ConversationGraphRuntime", "__init__")
    ) <= 7
    assert collaborator_count(
        _class_method(tool_runtime, "ConversationToolRuntime", "__init__")
    ) <= 4


def test_chat_runtime_does_not_compose_authority_or_observability() -> None:
    chat_paths = (
        _SOURCE_ROOT / "agent" / "chat" / "engine.py",
        _SOURCE_ROOT / "agent" / "chat" / "tool_runtime.py",
    )
    paths = chat_paths + (_SOURCE_ROOT / "conversation" / "store.py",)
    forbidden_modules = ("nuself.application", "nuself.storage")
    forbidden_symbols = {
        ("nuself.config", "runtime_paths"),
        ("nuself.log.store", "runtime_event_log_sink"),
    }
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {module}"
        for path in chat_paths
        for module in _imports(path)
        if _module_matches(module, forbidden_modules)
    ]
    violations.extend(
        f"{path.relative_to(_SOURCE_ROOT)} -> {module}.{name}"
        for path in paths
        for module, name in _from_imports(path)
        if (module, name) in forbidden_symbols
    )
    assert violations == []
    assert "EventPublisher()" not in paths[0].read_text(encoding="utf-8")


def test_application_composition_uses_domain_factories() -> None:
    tree = _tree(_SOURCE_ROOT / "application" / "composition.py")
    constructed = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert constructed.isdisjoint(
        {
            "ReasonRepository",
            "ReasonService",
            "ReflectionRepository",
            "ReflectionOrganizer",
            "ReflectionService",
        }
    )


def test_cross_domain_services_receive_foreign_capabilities() -> None:
    rules = {
        "reflection/scheduler.py": {
            "nuself.notification.outbox",
            "nuself.persona.discussion",
            "nuself.trace.service",
        },
        "reflection/service.py": {
            "nuself.reason.service",
            "nuself.trace.repository",
        },
        "memory/repository.py": {"nuself.profile.repository"},
        "memory/source_repository.py": {"nuself.profile.repository"},
        "memory/service.py": {"nuself.profile.repository"},
    }
    violations = [
        f"{relative} -> {module}"
        for relative, forbidden in rules.items()
        for module in _imports(_SOURCE_ROOT / relative)
        if module in forbidden
    ]
    assert violations == []


def test_reflection_candidates_use_conversation_history_api() -> None:
    path = _SOURCE_ROOT / "reflection" / "candidates.py"
    source = path.read_text(encoding="utf-8")
    forbidden = ("nuself.agent.chat",)
    assert not any(_module_matches(module, forbidden) for module in _imports(path))
    assert "ConversationStore" not in source
    assert "ConversationState" not in source


def test_reason_consumers_require_injected_service() -> None:
    for relative in ("reason/output.py", "reason/scheduler.py"):
        source = (_SOURCE_ROOT / relative).read_text(encoding="utf-8")
        assert "reason_service or ReasonService" not in source
        assert "service or ReasonService" not in source


def test_log_model_is_independent_from_persistence() -> None:
    model = _SOURCE_ROOT / "log" / "record.py"
    assert not {
        "nuself.config",
        "nuself.log.store",
        "nuself.private_fs",
    }.intersection(_imports(model))

    consumers = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in _SOURCE_ROOT.rglob("*.py")
        if path.name != "store.py"
        and ("nuself.log.store", "LogEvent") in _from_imports(path)
    ]
    assert consumers == []


def test_storage_package_has_precise_owners_without_facades() -> None:
    storage = _SOURCE_ROOT / "storage"
    assert (storage / "__init__.py").read_text(encoding="utf-8") == ""
    assert not (_SOURCE_ROOT / "storage.py").exists()
    assert not (_SOURCE_ROOT / "storage_sqlite.py").exists()
    assert not (_SOURCE_ROOT / "storage_audit.py").exists()
    assert not (_SOURCE_ROOT / "store.py").exists()
    assert not (_SOURCE_ROOT / "workspace.py").exists()
    assert "nuself.storage.pack" not in _imports(storage / "sqlite.py")
    assert "nuself.storage.sqlite" in _imports(storage / "pack.py")


def test_live_provider_matrix_is_not_production_code() -> None:
    assert not (_SOURCE_ROOT / "live_testing.py").exists()
    assert (
        Path(__file__).parents[2] / "live" / "matrix.py"
    ).is_file()
