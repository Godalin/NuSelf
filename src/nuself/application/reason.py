"""Application-owned composition for the reason domain."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.reason.advancer import ReasonAdvancer, default_reason_advancer

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
        workspace_store=application.reason_workspace,
        persona_repository=application.persona_prompts,
        trace_recorder=application.trace.recorder,
        readonly_tools=readonly_tools,
        langchain_models=(
            langchain_models
            if langchain_models is not None
            else configured_langchain_chat_models(
                application.paths.project_root,
                config=application.config,
            )
        ),
    )
