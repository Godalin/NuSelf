"""Tool registration, skill loading, prompt metadata, and call logging."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

from langchain_core.tools import BaseTool, StructuredTool

from nuself.agent.skills import (
    AgentSkill,
    load_agent_skills,
    render_tool_placeholders,
)
from nuself.agent.middleware import ToolOutcome
from nuself.agent.tool_utils import (
    tool_log_metadata,
    tool_service_component,
)
from nuself.agent.tools import build_langchain_chat_tools
from nuself.logs import write_log_event
from nuself.memory.query import MemoryQueryService
from nuself.reason.output import SectionPlanner
from nuself.reflection.repository import ReflectionRepository
from nuself.runtime.jobs import JobSink
from nuself.runtime.observability import report_observed_failure


class ConversationToolRuntime:
    """Owns the chat runtime's framework-native tool collection."""

    def __init__(
        self,
        *,
        project_root: Path | None,
        query_service: MemoryQueryService,
        selves_consult: Callable[..., str],
        job_sink: JobSink | None = None,
        section_planner: SectionPlanner | None = None,
    ) -> None:
        self._project_root = project_root
        tools = build_langchain_chat_tools(
            query_service=query_service,
            reflection_repository=ReflectionRepository(project_root),
            project_root=project_root,
            selves_consult=selves_consult,
            job_sink=job_sink,
            section_planner=section_planner,
        )
        self._tools = {tool.name: tool for tool in tools}
        self._skills = load_agent_skills()
        self._tools_by_skill = {
            skill.name: _tools_for_skill(skill, self._tools)
            for skill in self._skills
        }
        self._tools["load_skill"] = self._build_skill_loader()

    @property
    def tools(self) -> dict[str, BaseTool]:
        return self._tools

    def prompt_sections(self) -> list[str]:
        return _tool_prompt_sections(self._tools.values())

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def log_outcome(self, outcome: ToolOutcome) -> None:
        """Project one immutable middleware tool outcome."""

        tool = self._tools.get(outcome.name)
        if tool is None:
            return
        service_component = tool_service_component(tool)
        if service_component is None:
            return
        write_log_event(
            "chat",
            "service_tool_called",
            (
                f"{outcome.name} "
                f"{'failed' if outcome.error is not None else 'completed'}"
            ),
            project_root=self._project_root,
            status="failed" if outcome.error is not None else "completed",
            error=outcome.error,
            metadata=tool_log_metadata(
                args=outcome.args,
                result=outcome.result,
                error=outcome.error,
                service_component=service_component,
                tool_name=outcome.name,
            ),
        )

    def report_log_failure(self, exc: Exception) -> None:
        """Report a failed tool-log projection without changing tool execution."""

        report_observed_failure(
            exc,
            component="chat",
            event="tool_log_projection_failed",
            message="Tool outcome could not be projected to structured logs",
            project_root=self._project_root,
            metadata={"error_type": type(exc).__name__},
        )

    def _build_skill_loader(self) -> BaseTool:
        skill_lines = "\n".join(
            f"  - {skill.name}: {skill.description}"
            for skill in self._skills
        )

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

        return StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            name="load_skill",
            description=(
                "Load a service skill's behavioral policy. Skills "
                "define when and how the agent should use service "
                f"tools.\n\nAvailable skills:\n{skill_lines}"
            ),
            func=load_skill,
            tags=("readonly",),
            metadata={"service_component": "skill"},
        )


def _tool_prompt_sections(
    tools: Iterable[BaseTool],
) -> list[str]:
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
    for tool in tools:
        lines.append(
            f"- {tool.name}({_tool_args_signature(tool)}): "
            f"{tool.description}"
        )
    return lines


def _tools_for_skill(
    skill: AgentSkill,
    tools: dict[str, BaseTool],
) -> tuple[str, ...]:
    explicit = tuple(
        name for name in skill.allowed_tools if name in tools
    )
    if explicit:
        return explicit
    service_component = (
        "reasoning" if skill.name == "reason" else skill.name
    )
    return tuple(
        name
        for name, tool in tools.items()
        if tool_service_component(tool) == service_component
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
