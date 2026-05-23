"""LangChain tools for dynamic persona prompts."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import StructuredTool

from nuself.agent.tool_utils import format_tool_debug_body
from nuself.llm import ChatMessage, default_llm
from nuself.logs import write_log_event
from nuself.persona.prompt_repo import PersonaPrompt, PersonaPromptRepository, create_persona_prompt


def build_persona_tools(project_root: Path | None = None) -> tuple[StructuredTool, ...]:
    """Build persona tools that any agent (chat, reason) can use."""

    repo = PersonaPromptRepository(project_root)

    def persona_craft(name: str, prompt: str) -> str:
        """Create or update a reusable thinking persona.

        Use this when a specific thinking style or domain expertise would help —
        for example, a "systems-architect" that focuses on tradeoffs, or a
        "socratic-tutor" that questions assumptions. Once created, other tools
        like persona_list and persona_think can discover and invoke this persona.
        """
        name = name.strip()
        prompt = prompt.strip()
        if not name:
            return "Error: name must be a non-empty string"
        if not prompt:
            return "Error: prompt must be a non-empty string"
        if len(name) > 40:
            return "Error: name must be 40 characters or fewer"

        persona = create_persona_prompt(name, prompt, project_root=project_root)
        existing = repo.get_by_name(name)
        if existing is not None:
            persona = PersonaPrompt(
                id=existing.id,
                name=name,
                prompt=prompt,
                created_at=existing.created_at,
                updated_at=persona.updated_at,
            )
        repo.save(persona)
        _record_prompt_trace(persona, project_root=project_root)
        result = f"Created thinking persona '{name}' (id={persona.id}). Use persona_think to consult it."
        _log_persona_tool(
            "persona_craft",
            args={"name": name},
            result=result,
            project_root=project_root,
        )
        return result

    def persona_list() -> str:
        """List all available thinking personas with id and name."""
        prompts = repo.list()
        if not prompts:
            result = "No thinking personas available. Use persona_craft to create one."
        else:
            lines = ["Available thinking personas:"]
            for p in prompts:
                lines.append(f"  - {p.name} (id={p.id})")
            result = "\n".join(lines)
        _log_persona_tool("persona_list", args={}, result=result, project_root=project_root)
        return result

    def persona_think(persona: str, question: str) -> str:
        """Consult a thinking persona by name or id and get its response.

        Loads the persona's prompt, calls the language model with the persona
        as system instruction, and returns the persona's thinking.
        """
        persona = persona.strip()
        question = question.strip()
        if not persona:
            return "Error: persona must be a non-empty string (name or id)"
        if not question:
            return "Error: question must be a non-empty string"

        prompt = repo.resolve(persona)
        if prompt is None:
            existing = repo.list()
            names = [p.name for p in existing]
            if names:
                return f"No persona found for '{persona}'. Available: {', '.join(names)}"
            return f"No persona found for '{persona}'. Use persona_craft to create one first."

        messages = [
            ChatMessage(role="system", content=prompt.prompt),
            ChatMessage(role="user", content=question),
        ]
        try:
            llm = default_llm(project_root)
            response = llm.complete(messages).strip()
        except RuntimeError as exc:
            _log_persona_tool("persona_think", args={"persona": prompt.name, "question": question}, project_root=project_root, error=str(exc))
            return f"Error consulting persona '{prompt.name}': {exc}"

        _log_persona_tool("persona_think", args={"persona": prompt.name, "question": question}, result=response, project_root=project_root)
        return response

    return (
        StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            func=persona_craft,
            name="persona_craft",
            description="Create or update a reusable thinking persona with a name and custom prompt.",
        ),
        StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            func=persona_list,
            name="persona_list",
            description="List all available thinking personas with id and name.",
            tags=("readonly",),
        ),
        StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            func=persona_think,
            name="persona_think",
            description="Consult a thinking persona by name or id and get its response to a question.",
            tags=("readonly",),
        ),
    )


def _record_prompt_trace(prompt: PersonaPrompt, *, project_root: Path | None = None) -> None:
    try:
        from nuself.trace.service import TraceRecorder

        TraceRecorder(project_root=project_root).record_persona_prompt_created(
            persona_prompt_id=prompt.id,
            name=prompt.name,
        )
    except RuntimeError:
        pass


def _log_persona_tool(
    tool_name: str,
    *,
    args: dict[str, object],
    result: str | None = None,
    error: str | None = None,
    project_root: Path | None = None,
) -> None:
    try:
        message = format_tool_debug_body(args=args, result=result, error=error)
        full_body = format_tool_debug_body(args=args, result=result, error=error, full=True)
        write_log_event(
            "chat",
            "service_tool_called",
            message,
            project_root=project_root,
            status="failed" if error else "completed",
            error=error,
            metadata={
                "service_component": "persona",
                "tool": tool_name,
                "message_body": full_body,
                **(args or {}),
            },
        )
    except RuntimeError:
        pass
