"""Executable package dependency rules for the current architecture."""

from __future__ import annotations

import ast
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src" / "nuself"
_OUTER_ADAPTERS = ("nuself.cli", "nuself.daemon", "nuself.tui")
_DOMAIN_PACKAGES = (
    "memory",
    "inbox",
    "delivery",
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
    allowed: set[str] = set()
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


def test_tool_effect_transport_and_agent_boundaries_are_approval_neutral() -> None:
    checked = (
        *_package_files("daemon"),
        _SOURCE_ROOT / "agent" / "chat" / "response.py",
        _SOURCE_ROOT / "agent" / "tools" / "decorated.py",
    )
    violations = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in checked
        if _module_matches(
            "nuself.runtime.feature.approval",
            _imports(path),
        )
    ]
    assert violations == []


def test_feature_executor_and_agent_middleware_do_not_own_effect_logging() -> None:
    executor = _SOURCE_ROOT / "runtime" / "feature" / "execution.py"
    executor_names = {
        node.id
        for node in ast.walk(_tree(executor))
        if isinstance(node, ast.Name)
    }
    assert not executor_names & {
        "ApprovalEffect",
        "ObservationEffect",
        "AuditEffect",
    }

    middleware = _SOURCE_ROOT / "agent" / "middleware.py"
    assert not any(
        module.startswith("nuself.log")
        or module.startswith("nuself.runtime.event")
        for module in _imports(middleware)
    )


def test_domain_tool_builders_do_not_construct_feature_executors() -> None:
    builder_paths = tuple(
        path
        for path in (_SOURCE_ROOT / "agent" / "tools").glob("*.py")
        if path.stem
        not in {"__init__", "composition", "decorated", "resources"}
    ) + (_SOURCE_ROOT / "persona" / "tools.py",)
    violations = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in builder_paths
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FeatureExecutor"
            for node in ast.walk(_tree(path))
        )
    ]
    assert violations == []


def test_tool_resources_contains_no_materialized_langchain_tools() -> None:
    resources = _SOURCE_ROOT / "agent" / "tools" / "resources.py"
    assert not _module_matches("langchain_core.tools", _imports(resources))
    assert "BaseTool" not in resources.read_text(encoding="utf-8")


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


def test_application_graph_exposes_services_not_persistence() -> None:
    path = _SOURCE_ROOT / "application" / "composition.py"
    graph = next(
        node
        for node in _tree(path).body
        if isinstance(node, ast.ClassDef)
        and node.name == "ApplicationGraph"
    )
    forbidden = {
        "ConversationStore",
        "DeliveryStore",
        "MemoryRepositories",
        "PrivateWorkspaceStore",
    }
    exposed = {
        node.annotation.id
        for node in graph.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.annotation, ast.Name)
    }
    assert exposed.isdisjoint(forbidden)
    assert not any(name.endswith("Repository") for name in exposed)


def test_concrete_repositories_do_not_cross_runtime_package_boundaries() -> None:
    violations: list[str] = []
    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        source_package = path.relative_to(_SOURCE_ROOT).parts[0]
        for module, name in _from_imports(path):
            if not name.endswith("Repository"):
                continue
            parts = module.split(".")
            imported_package = parts[1] if len(parts) > 1 else ""
            if source_package == imported_package:
                continue
            if path.name == "composition.py":
                continue
            violations.append(
                f"{path.relative_to(_SOURCE_ROOT)} -> {module}.{name}"
            )
    assert violations == []


def test_application_graph_is_a_finite_typed_composition_result() -> None:
    graph = next(
        node
        for node in _tree(_SOURCE_ROOT / "application" / "composition.py").body
        if isinstance(node, ast.ClassDef) and node.name == "ApplicationGraph"
    )
    fields = {
        node.target.id: node.annotation.id
        for node in graph.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and isinstance(node.annotation, ast.Name)
    }
    assert fields == {
        "paths": "RuntimePaths",
        "config": "SystemConfig",
        "conversations": "ConversationService",
        "conversation_history": "ConversationHistoryService",
        "memory": "MemoryService",
        "profiles": "ProfileService",
        "memory_workflows": "MemoryWorkflowService",
        "sources": "SourceService",
        "source_importer": "SourceImporter",
        "inbox": "InboxService",
        "deliveries": "DeliveryService",
        "personas": "PersonaService",
        "reason": "ReasonService",
        "reflection": "ReflectionService",
        "trace": "TraceServices",
        "data": "DataAdminService",
        "chat_completion": "ChatCompletionService",
    }
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in graph.body
    )
    assert any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "dataclass"
        and any(
            keyword.arg == "frozen"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in decorator.keywords
        )
        for decorator in graph.decorator_list
    )


def test_application_graph_names_single_services_by_domain() -> None:
    graph = next(
        node
        for node in _tree(_SOURCE_ROOT / "application" / "composition.py").body
        if isinstance(node, ast.ClassDef) and node.name == "ApplicationGraph"
    )
    fields = {
        node.target.id: node.annotation.id
        for node in graph.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and isinstance(node.annotation, ast.Name)
    }
    assert {
        name: fields[name]
        for name in ("memory", "reason", "reflection")
    } == {
        "memory": "MemoryService",
        "reason": "ReasonService",
        "reflection": "ReflectionService",
    }
    assert {"memory_service", "reason_service", "reflection_service"}.isdisjoint(
        fields
    )
    assert "memory_candidates" not in fields


def test_service_classes_live_in_single_word_modules() -> None:
    violations = [
        str(path.relative_to(_SOURCE_ROOT))
        for path in _SOURCE_ROOT.rglob("*.py")
        if "_" in path.stem
        and any(
            isinstance(node, ast.ClassDef)
            and (node.name.endswith("Service") or node.name.endswith("Services"))
            for node in _tree(path).body
        )
    ]
    assert violations == []


def test_persona_tool_builders_name_service_dependencies() -> None:
    functions = {
        node.name: node
        for node in _tree(_SOURCE_ROOT / "persona" / "tools.py").body
        if isinstance(node, ast.FunctionDef)
    }
    global_names = {
        argument.arg
        for argument in functions["build_persona_tools"].args.kwonlyargs
    }
    reason_names = {
        argument.arg
        for argument in functions["build_reason_persona_tools"].args.kwonlyargs
    }
    assert "service" in global_names
    assert "repository" not in global_names
    assert "global_service" in reason_names
    assert "global_repository" not in reason_names


def test_process_and_agent_adapters_do_not_import_persistence_types() -> None:
    forbidden = {
        "ConversationStore",
        "DeliveryStore",
        "MemoryCandidateRepository",
        "MemoryEntryRepository",
        "MemoryRepositories",
        "PersonaPromptRepository",
        "PrivateWorkspaceStore",
        "ProfileItemRepository",
        "ReflectionRepository",
    }
    paths = _package_files("cli", "daemon", "agent", "evaluation")
    violations = [
        f"{path.relative_to(_SOURCE_ROOT)} -> {module}.{name}"
        for path in paths
        for module, name in _from_imports(path)
        if name in forbidden
    ]
    assert violations == []


def test_cross_domain_services_receive_foreign_capabilities() -> None:
    rules = {
        "reflection/scheduler.py": {
            "nuself.persona.discussion",
            "nuself.trace.service",
        },
        "reflection/service.py": {
            "nuself.reason.service",
            "nuself.trace.repository",
        },
        "memory/repository.py": {"nuself.profile.repository"},
        "memory/service.py": {
            "nuself.profile.repository",
            "nuself.source.repository",
            "nuself.source.service",
        },
        "source/repository.py": {
            "nuself.memory.repository",
            "nuself.profile.repository",
        },
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
        "nuself.storage.filesystem",
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


def test_nuself_root_contains_no_substantive_modules() -> None:
    assert tuple(
        sorted(path.name for path in _SOURCE_ROOT.glob("*.py"))
    ) == ("__init__.py",)
    assert (
        _SOURCE_ROOT / "config" / "__init__.py"
    ).read_text(encoding="utf-8") == ""
    assert (
        _SOURCE_ROOT / "evaluation" / "__init__.py"
    ).read_text(encoding="utf-8") == ""
