"""Reason-owned workflow composition from supplied capabilities."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from nuself.agent.endpoint import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.reason.advancer import ReasonAdvancer, default_reason_advancer
from nuself.reason.prompt import generate_reasoning_prompt
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.persona.service import PersonaService
from nuself.storage.contract import StorageBackend
from nuself.trace.service import TraceRecorder
from nuself.storage.workspace import PrivateWorkspaceStore
from nuself.inbox.service import InboxService

if TYPE_CHECKING:
    from nuself.config.settings import RuntimePaths, SystemConfig


def compose_reason_service(
    paths: "RuntimePaths",
    backend: StorageBackend,
    trace_recorder: TraceRecorder,
    config: "SystemConfig",
    inbox: InboxService,
) -> ReasonService:
    """Compose Reason's authority-scoped service."""

    repository = ReasonRepository(paths, backend=backend)
    workspace = PrivateWorkspaceStore(paths, scope="reason")
    return ReasonService(
        paths.authority_root,
        repository=repository,
        workspace_store=workspace,
        trace_recorder=trace_recorder,
        prompt_generator=compose_reason_prompt_generator(paths, config),
        inbox=inbox,
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
    reason_service: ReasonService,
    persona_service: PersonaService,
    trace_recorder: TraceRecorder,
    config: "SystemConfig",
    *,
    readonly_tools: Sequence[BaseTool] | None = None,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> ReasonAdvancer:
    """Compose model-backed reason advancement from one authority graph."""

    return default_reason_advancer(
        paths=paths,
        reason_service=reason_service,
        persona_service=persona_service,
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
