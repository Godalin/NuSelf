"""Application-owned composition for the reason domain."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from nuself.llm import LangChainLLMEndpoint
from nuself.reason.advancer import ReasonAdvancer, default_reason_advancer
from nuself.workspace import PrivateWorkspaceStore

if TYPE_CHECKING:
    from nuself.application.composition import ApplicationGraph


def compose_reason_advancer(
    application: "ApplicationGraph",
    *,
    readonly_tools: Sequence[BaseTool] | None = None,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> ReasonAdvancer:
    """Compose model-backed reason advancement from one authority graph."""

    return default_reason_advancer(
        paths=application.paths,
        workspace_store=PrivateWorkspaceStore(
            application.paths,
            scope="reason",
        ),
        persona_repository=application.persona_prompts,
        trace_recorder=application.trace.recorder,
        readonly_tools=readonly_tools,
        langchain_models=langchain_models,
    )
