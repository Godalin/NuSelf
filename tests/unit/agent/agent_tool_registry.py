from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

# pyright: reportPrivateUsage=false

from pathlib import Path

from nuself.agent.tools.memory import build_memory_tool_set
from nuself.agent.tools.reason import build_reason_tools
from nuself.agent.tools.reflection import build_reflection_tools
from nuself.agent.tools.selves import build_selves_tools
from nuself.agent.tools.trace import build_trace_tools
from nuself.agent.tools.workspace import build_workspace_tools_from_provider
from nuself.application.composition import compose_application
from nuself.config import runtime_paths
from nuself.memory.service import MemoryService
from nuself.memory.repository import MemoryEntryRepository
from reason_fixtures import ReasonService
from nuself.store import ScopedWorkspace, SqliteStore
from tests.backend import owned_backend
from nuself.trace.repository import TraceRepository
from nuself.trace.service import TraceQueryService
from nuself.workspace import PrivateWorkspaceStore


def _names(tools: tuple[object, ...]) -> set[str]:
    return {str(getattr(tool, "name")) for tool in tools}


def test_subsystem_tool_builders_own_their_registries(
    tmp_path: Path,
) -> None:
    memory_repository = memory_entry_repository(tmp_path)

    memory_tools = build_memory_tool_set(
        service=MemoryService(memory_repository),
        project_root=tmp_path,
    )
    assert _names((*memory_tools.readonly, *memory_tools.write)) == {
        "memory_search",
        "memory_count",
        "memory_archive",
        "memory_update_importance",
    }
    assert _names(
        build_reflection_tools(
            compose_application(
                runtime_paths(tmp_path),
                owned_backend(tmp_path),
            ).reflection.service
        )
    ) == {
        "reflection_list_pending",
        "reflection_count",
        "reflection_dismiss",
        "reflection_archive",
    }
    reason_service = ReasonService(tmp_path)
    reason_workspace = PrivateWorkspaceStore(
        runtime_paths(tmp_path),
        scope="reason",
    )
    base_reason_tools = {
        "reason_list_active",
        "reason_count",
        "reason_show",
        "reason_context",
        "reason_step",
        "reason_propose",
    }
    assert _names(
        build_reason_tools(
            service=reason_service,
            project_root=tmp_path,
            workspace_store=reason_workspace,
        )
    ) == base_reason_tools
    assert _names(
        build_reason_tools(
            service=reason_service,
            project_root=tmp_path,
            workspace_store=reason_workspace,
            job_sink=lambda _message: None,
        )
    ) == {*base_reason_tools, "reason_export"}
    assert _names(
        build_trace_tools(
            TraceQueryService(
                TraceRepository(
                    runtime_paths(tmp_path),
                    backend=owned_backend(tmp_path),
                )
            )
        )
    ) == {
        "trace_search",
        "trace_count",
        "trace_show",
        "trace_related",
    }
    assert _names(
        build_selves_tools(
            lambda topic, mode, context: f"{topic}:{mode}:{context}"
        )
    ) == {"selves_consult"}
    assert build_selves_tools(None) == ()


def test_workspace_tool_builder_owns_workspace_registry(
    tmp_path: Path,
) -> None:
    from nuself.storage import _create_sqlite_backend

    database = tmp_path / "workspace.sqlite"
    _create_sqlite_backend(db_path=database).close()
    workspace = ScopedWorkspace(
        SqliteStore(database),
        ("thread",),
    )

    assert _names(build_workspace_tools_from_provider(lambda: workspace)) == {
        "workspace_put",
        "workspace_get",
        "workspace_search",
        "workspace_delete",
    }
