from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from nuself.persona.tools import (
    build_persona_tools,
    build_reason_persona_tools,
)
from nuself.store import ScopedWorkspace, SqliteStore


class _TextAgent:
    def __init__(self, result: str = "persona conclusion") -> None:
        self._result = result
        self.calls: list[Sequence[BaseMessage]] = []

    def invoke(self, messages: Sequence[BaseMessage]) -> str:
        self.calls.append(messages)
        return self._result


def _tool(tools: tuple[BaseTool, ...], name: str) -> BaseTool:
    return next(tool for tool in tools if tool.name == name)


def _invoke_tool(tool: BaseTool, args: dict[str, object]) -> object:
    invoke = cast(
        Callable[[dict[str, object]], Any],
        getattr(tool, "invoke"),
    )
    return invoke(args)


def test_global_persona_think_uses_injected_text_agent(
    tmp_path: Path,
) -> None:
    agent = _TextAgent()
    tools = build_persona_tools(tmp_path, text_agent=agent)
    _invoke_tool(
        _tool(tools, "persona_craft"),
        {
            "name": "reviewer",
            "prompt": "Review assumptions carefully.",
        },
    )

    result = _invoke_tool(
        _tool(tools, "persona_think"),
        {
            "persona": "reviewer",
            "question": "What is missing?",
        },
    )

    assert result == "persona conclusion"
    assert len(agent.calls) == 1
    assert isinstance(agent.calls[0][0], SystemMessage)
    assert agent.calls[0][0].text == "Review assumptions carefully."
    assert isinstance(agent.calls[0][1], HumanMessage)
    assert agent.calls[0][1].text == "What is missing?"


def test_persona_think_sanitizes_agent_failure(
    tmp_path: Path,
) -> None:
    agent_secret = "persona-secret-value"

    class _FailingTextAgent(_TextAgent):
        def invoke(self, messages: Sequence[BaseMessage]) -> str:
            self.calls.append(messages)
            raise RuntimeError(
                f"persona unavailable api_key={agent_secret}"
            )

    tools = build_persona_tools(
        tmp_path,
        text_agent=_FailingTextAgent(),
    )
    _invoke_tool(
        _tool(tools, "persona_craft"),
        {
            "name": "reviewer",
            "prompt": "Review assumptions carefully.",
        },
    )

    result = _invoke_tool(
        _tool(tools, "persona_think"),
        {
            "persona": "reviewer",
            "question": "What is missing?",
        },
    )

    assert result == (
        "Error consulting persona 'reviewer': "
        "persona unavailable api_key=***"
    )
    assert agent_secret not in str(result)


def test_reason_persona_think_uses_same_injected_text_agent(
    tmp_path: Path,
) -> None:
    workspace = ScopedWorkspace(
        SqliteStore(tmp_path / "private" / "workspace.sqlite"),
        ("reason", "thread-1"),
    )
    agent = _TextAgent("thread persona conclusion")
    tools = build_reason_persona_tools(
        global_project_root=tmp_path,
        get_thread_workspace=lambda: workspace,
        text_agent=agent,
    )
    _invoke_tool(
        _tool(tools, "persona_craft"),
        {
            "name": "local-reviewer",
            "prompt": "Focus on local thread constraints.",
        },
    )

    result = _invoke_tool(
        _tool(tools, "persona_think"),
        {
            "persona": "local-reviewer",
            "question": "Review this step.",
            "scope": "local",
        },
    )

    assert result == "thread persona conclusion"
    assert len(agent.calls) == 1
    assert agent.calls[0][0].text == "Focus on local thread constraints."
    assert agent.calls[0][1].text == "Review this step."
