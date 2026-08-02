"""Reason-owned workflow composition from supplied capabilities."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.reason.advancer import ReasonAdvancer, default_reason_advancer
from nuself.reason.prompt import generate_reasoning_prompt
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.storage import StorageBackend
from nuself.trace.service import TraceRecorder
from nuself.workspace import PrivateWorkspaceStore

if TYPE_CHECKING:
    from nuself.config import RuntimePaths, SystemConfig


def compose_reason_service(
    paths: "RuntimePaths",
    backend: StorageBackend,
    trace_recorder: TraceRecorder,
    config: "SystemConfig",
) -> tuple[ReasonService, PrivateWorkspaceStore]:
    """Compose Reason's authority-scoped service and workspace."""

    repository = ReasonRepository(paths, backend=backend)
    workspace = PrivateWorkspaceStore(paths, scope="reason")
    return (
        ReasonService(
            paths.authority_root,
            repository=repository,
            workspace_store=workspace,
            trace_recorder=trace_recorder,
            prompt_generator=compose_reason_prompt_generator(paths, config),
        ),
        workspace,
    )


def compose_reason_prompt_generator(
    paths: "RuntimePaths",
    config: "SystemConfig",
) -> Callable[..., str]:
    """Bind lazy model-backed prompt generation to one application authority."""

    def generate(
        topic: str,
        *,
        mandates: tuple[str, ...] = (),
        active_items: tuple[dict[str, object], ...] = (),
    ) -> str:
        return generate_reasoning_prompt(
            topic,
            mandates=mandates,
            active_items=active_items,
            project_root=paths.authority_root,
            endpoints=configured_langchain_chat_models(
                paths.authority_root,
                config=config,
            ),
        )

    return generate


def compose_reason_advancer(
    paths: "RuntimePaths",
    workspace_store: PrivateWorkspaceStore,
    persona_repository: PersonaPromptRepository,
    trace_recorder: TraceRecorder,
    config: "SystemConfig",
    *,
    readonly_tools: Sequence[BaseTool] | None = None,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> ReasonAdvancer:
    """Compose model-backed reason advancement from one authority graph."""

    return default_reason_advancer(
        paths=paths,
        workspace_store=workspace_store,
        persona_repository=persona_repository,
        trace_recorder=trace_recorder,
        readonly_tools=readonly_tools,
        langchain_models=(
            langchain_models
            if langchain_models is not None
            else configured_langchain_chat_models(
                paths.authority_root,
                config=config,
            )
        ),
    )
