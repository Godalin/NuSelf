from __future__ import annotations

# pyright: reportPrivateUsage=false

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from nuself.agent.errors import AgentModelUnavailableError
from nuself.application.composition import compose_application
from nuself.config.settings import runtime_paths
from nuself.persona.tools import (
    build_persona_tools,
    build_reason_persona_tools,
)
from nuself.storage.workspace import ScopedWorkspace, SqliteStore
from nuself.storage.authority import _create_sqlite_backend
from tests.backend import owned_backend


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


def _persona_dependencies(tmp_path: Path):
    return compose_application(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    )


def test_global_persona_think_uses_injected_text_agent(
    tmp_path: Path,
) -> None:
    agent = _TextAgent()
    application = _persona_dependencies(tmp_path)
    tools = build_persona_tools(
        tmp_path,
        repository=application.personas,
        trace_recorder=application.trace.recorder,
        text_agent=agent,
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
            raise AgentModelUnavailableError(
                f"persona unavailable api_key={agent_secret}"
            )

    application = _persona_dependencies(tmp_path)
    tools = build_persona_tools(
        tmp_path,
        repository=application.personas,
        trace_recorder=application.trace.recorder,
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


@pytest.mark.parametrize("reason_scoped", [False, True])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_persona_think_propagates_untyped_agent_errors(
    tmp_path: Path,
    reason_scoped: bool,
    error_type: type[Exception],
) -> None:
    expected = error_type("raw text agent implementation failure")

    class _UntypedFailureAgent(_TextAgent):
        def invoke(self, messages: Sequence[BaseMessage]) -> str:
            raise expected

    if reason_scoped:
        application = _persona_dependencies(tmp_path)
        database = tmp_path / "private" / "workspace.sqlite"
        database.parent.mkdir(parents=True)
        _create_sqlite_backend(db_path=database).close()
        workspace = ScopedWorkspace(
            SqliteStore(database),
            ("reason", "thread-1"),
        )
        tools = build_reason_persona_tools(
            paths=application.paths,
            global_repository=application.personas,
            trace_recorder=application.trace.recorder,
            get_thread_workspace=lambda: workspace,
            text_agent=_UntypedFailureAgent(),
        )
        craft_args: dict[str, object] = {
            "name": "local-reviewer",
            "prompt": "Review local assumptions.",
        }
        think_args: dict[str, object] = {
            "persona": "local-reviewer",
            "question": "What is missing?",
            "scope": "local",
        }
    else:
        application = _persona_dependencies(tmp_path)
        tools = build_persona_tools(
            tmp_path,
            repository=application.personas,
            trace_recorder=application.trace.recorder,
            text_agent=_UntypedFailureAgent(),
        )
        craft_args = {
            "name": "reviewer",
            "prompt": "Review global assumptions.",
        }
        think_args = {
            "persona": "reviewer",
            "question": "What is missing?",
        }

    _invoke_tool(_tool(tools, "persona_craft"), craft_args)

    with pytest.raises(error_type) as caught:
        _invoke_tool(_tool(tools, "persona_think"), think_args)
    assert caught.value is expected


def test_reason_persona_think_uses_same_injected_text_agent(
    tmp_path: Path,
) -> None:
    application = _persona_dependencies(tmp_path)
    database = tmp_path / "private" / "workspace.sqlite"
    database.parent.mkdir(parents=True)
    _create_sqlite_backend(db_path=database).close()
    workspace = ScopedWorkspace(
        SqliteStore(database),
        ("reason", "thread-1"),
    )
    agent = _TextAgent("thread persona conclusion")
    tools = build_reason_persona_tools(
        paths=application.paths,
        global_repository=application.personas,
        trace_recorder=application.trace.recorder,
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
