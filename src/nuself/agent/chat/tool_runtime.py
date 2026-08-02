"""Tool registration, skill loading, prompt metadata, and call logging."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from langchain_core.tools import BaseTool

from nuself.agent.skill_loader import (
    load_agent_skills,
    render_tool_placeholders,
)
from nuself.agent.middleware import ToolOutcome
from nuself.agent.tool_audit import ToolOutcomeProjection
from nuself.agent.tool_utils import (
    tool_service_component,
)
from nuself.agent.tools.composition import build_langchain_chat_tools
from nuself.agent.tools.decorated import materialize_tool
from nuself.agent.tools.resources import ToolResources
from nuself.decorators import component, observed, readonly, tool
from nuself.runtime.feature_execution import FeatureExecutor
from nuself.runtime.observability import (
    report_observability_projection_failure,
)
from nuself.runtime.events import EventPublisher
from nuself.runtime.event_payloads import RuntimeLogEventPayload


class ConversationToolRuntime:
    """Owns the chat runtime's framework-native tool collection."""

    def __init__(
        self,
        *,
        resources: ToolResources,
        selves_consult: Callable[..., str],
        feature_executor: FeatureExecutor | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._project_root = resources.project_root
        self._feature_executor = feature_executor or FeatureExecutor()
        self._event_publisher = event_publisher
        tools = build_langchain_chat_tools(
            resources=resources,
            selves_consult=selves_consult,
            feature_executor=self._feature_executor,
        )
        self._tools = {tool.name: tool for tool in tools}
        loaded_skills = load_agent_skills()
        tools_by_skill = {
            skill.name: tuple(
                name
                for name in skill.allowed_tools
                if name in self._tools
            )
            for skill in loaded_skills
        }
        self._skills = tuple(
            skill
            for skill in loaded_skills
            if not skill.allowed_tools or tools_by_skill[skill.name]
        )
        self._tools_by_skill = {
            skill.name: tools_by_skill[skill.name] for skill in self._skills
        }
        self._tools["load_skill"] = self._build_skill_loader()

    @property
    def tools(self) -> dict[str, BaseTool]:
        return self._tools

    def prompt_sections(self) -> list[str]:
        lines = [
            "",
            "Available tools:",
            "The following LangChain tools are loaded in the current "
            "NuSelf runtime.",
            "CRITICAL: When the user asks a question that a tool can "
            "answer, you MUST call the tool before generating your final "
            "answer. Always use the tool to get the actual current state.",
            "Tools are bound through LangChain's native tool-calling API.",
            "Do not write visible markers such as "
            '"[Tool call: memory_search]" or JSON tool fields in the '
            "answer body.",
            "The tool will be executed and its result injected back into "
            "context. Only then generate your final answer.",
            "Service skills define when and how to use tools. Use "
            "`load_skill` to load a skill's behavioral policy.",
            "Tools available:",
        ]
        lines.extend(
            f"- {tool.name}({_tool_args_signature(tool)}): "
            f"{tool.description}"
            for tool in self._tools.values()
        )
        return lines

    def log_outcome(self, outcome: ToolOutcome) -> None:
        """Project one immutable middleware tool outcome."""

        tool = self._tools.get(outcome.name)
        if tool is None:
            return
        metadata = tool.metadata or {}
        if metadata.get("observed") is True:
            if self._event_publisher is not None:
                self._event_publisher.publish(
                    producer="chat",
                    name="tool.activity",
                    payload=RuntimeLogEventPayload(
                        message="Tool outcome observed",
                        level=(
                            "error"
                            if outcome.error is not None
                            else "info"
                        ),
                        status=(
                            "failed"
                            if outcome.error is not None
                            else "completed"
                        ),
                        metadata={
                            "service_component": metadata.get(
                                "service_component"
                            ),
                            "operation": outcome.name,
                        },
                    ).to_mapping(),
                )
            return
        service_component = tool_service_component(tool)
        if service_component is None:
            return
        ToolOutcomeProjection(
            component="chat",
            service_component=service_component,
            outcome=outcome,
        ).write(project_root=self._project_root)

    def report_log_failure(self, exc: Exception) -> None:
        """Report a failed tool-log projection without changing tool execution."""

        report_observability_projection_failure(
            exc,
            component="chat",
            failed_event="service_tool_called",
            project_root=self._project_root,
        )

    def _build_skill_loader(self) -> BaseTool:
        skill_lines = "\n".join(
            f"  - {skill.name}: {skill.description}"
            for skill in self._skills
        )

        @tool(
            name="load_skill",
            description=(
                "Load a service skill's behavioral policy. Skills "
                "define when and how the agent should use service "
                f"tools.\n\nAvailable skills:\n{skill_lines}"
            ),
        )
        @component("skill")
        @readonly
        @observed
        def load_skill(skill_name: str) -> str:
            for skill in self._skills:
                if skill.name == skill_name:
                    tools = self._tools_by_skill.get(skill_name, ())
                    body = f"Service skill: {skill.name}"
                    if tools:
                        body += f"\nAllowed tools: {', '.join(tools)}"
                    instructions = render_tool_placeholders(
                        skill.instructions,
                        skill_name=skill_name,
                        tools=tools,
                    )
                    return f"{body}\n\n{instructions}"
            return (
                f"Error: unknown skill '{skill_name}'. "
                f"Available skills:\n{skill_lines}"
            )

        return materialize_tool(
            load_skill,
            executor=self._feature_executor,
        )


def _tool_args_signature(tool: BaseTool) -> str:
    raw_schema = cast(object, getattr(tool, "args"))
    args_schema = (
        cast(dict[object, object], raw_schema)
        if isinstance(raw_schema, dict)
        else {}
    )
    pieces: list[str] = []
    for name, schema in args_schema.items():
        if not isinstance(name, str):
            continue
        type_name = "object"
        default: object | None = None
        if isinstance(schema, dict):
            schema_dict = cast(dict[object, object], schema)
            type_value = schema_dict.get("type")
            if isinstance(type_value, str):
                type_name = type_value
            default = schema_dict.get("default")
        pieces.append(
            f"{name}: {type_name}"
            if default is None
            else f"{name}: {type_name} = {default!r}"
        )
    return ", ".join(pieces)
