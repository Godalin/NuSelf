"""Immutable cross-subsystem agent capability values."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from nuself.llm import LangChainLLMEndpoint


@dataclass(frozen=True)
class AgentCapabilitySnapshot:
    """Stable collection membership shared between agent subsystems."""

    endpoints: tuple[LangChainLLMEndpoint, ...]
    readonly_tools: tuple[BaseTool, ...]
