"""LangChain tools for dynamic persona prompts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from langchain_core.tools import StructuredTool

from nuself.llm import ChatMessage, default_llm
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
            return f"Error consulting persona '{prompt.name}': {exc}"

        return response

    return (
        StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            func=persona_craft,
            name="persona_craft",
            description="Create or update a reusable thinking persona with a name and custom prompt.",
            metadata={"service_component": "persona"},
        ),
        StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            func=persona_list,
            name="persona_list",
            description="List all available thinking personas with id and name.",
            tags=("readonly",),
            metadata={"service_component": "persona"},
        ),
        StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            func=persona_think,
            name="persona_think",
            description="Consult a thinking persona by name or id and get its response to a question.",
            tags=("readonly",),
            metadata={"service_component": "persona"},
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


def build_reason_persona_tools(
    *,
    global_project_root: Path | None,
    get_thread_persona_root: Callable[[], Path],
) -> tuple[StructuredTool, ...]:
    """Build persona tools scoped to a reason thread.

    *get_thread_persona_root* is called on each tool invocation to resolve the
    current thread's private persona directory, allowing the same tool instances
    to be reused across threads.

    - ``persona_craft`` stores in the thread's private workspace only.
    - ``persona_list`` merges global + local personas.
    - ``persona_think`` resolves from thread first, then global.
    """

    def _thread_repo() -> PersonaPromptRepository:
        return PersonaPromptRepository(root=get_thread_persona_root())

    global_repo = PersonaPromptRepository(global_project_root) if global_project_root else None

    def _craft(name: str, prompt: str) -> str:
        name = name.strip()
        prompt = prompt.strip()
        if not name:
            return "Error: name must be a non-empty string"
        if not prompt:
            return "Error: prompt must be a non-empty string"
        if len(name) > 40:
            return "Error: name must be 40 characters or fewer"

        repo = _thread_repo()
        persona = create_persona_prompt(name, prompt, project_root=global_project_root)
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
        _record_prompt_trace(persona, project_root=global_project_root)
        result = f"Created thinking persona '{name}' (id={persona.id}, scoped to this reason thread)."
        return result

    def _list(scope: str = "") -> str:
        repo = _thread_repo()
        thread_prompts = repo.list()
        global_prompts = global_repo.list() if global_repo else ()
        local_list = thread_prompts if scope in ("", "local") else ()
        global_list = global_prompts if scope in ("", "global") else ()
        all_prompts = list(global_list) + list(local_list)
        if not all_prompts:
            result = "No thinking personas available. Use persona_craft to create one."
        else:
            lines = ["Available thinking personas:"]
            for p in all_prompts:
                tag = " [local]" if scope == "" and repo.get(p.id) is not None else ""
                lines.append(f"  - {p.name} (id={p.id}){tag}")
            result = "\n".join(lines)
        return result

    def _think(persona: str, question: str, scope: str = "") -> str:
        persona = persona.strip()
        question = question.strip()
        if not persona:
            return "Error: persona must be a non-empty string (name or id)"
        if not question:
            return "Error: question must be a non-empty string"

        thread_repo_inst = _thread_repo()
        prompt: PersonaPrompt | None = None
        if scope in ("", "local"):
            prompt = thread_repo_inst.resolve(persona)
        if prompt is None and scope in ("", "global") and global_repo is not None:
            prompt = global_repo.resolve(persona)
        if prompt is None:
            available: list[str] = []
            if global_repo:
                available.extend(p.name for p in global_repo.list())
            available.extend(p.name for p in thread_repo_inst.list())
            if available:
                return f"No persona found for '{persona}'. Available: {', '.join(available)}"
            return f"No persona found for '{persona}'. Use persona_craft to create one first."

        messages = [
            ChatMessage(role="system", content=prompt.prompt),
            ChatMessage(role="user", content=question),
        ]
        from nuself.llm import default_llm

        llm = default_llm(global_project_root)
        try:
            raw = llm.complete(messages)
        except RuntimeError as exc:
            return f"persona_think failed: {exc}"
        result = raw.strip()
        return result

    from langchain_core.tools import StructuredTool

    return (
        StructuredTool.from_function(func=_craft, name="persona_craft", description="Create or update a thinking persona scoped to the current reason thread. Also consults global personas when listing and thinking.", metadata={"service_component": "persona"}),
        StructuredTool.from_function(func=_list, name="persona_list", description="List available thinking personas (global + current reason thread). Pass scope='local' for only thread-scoped personas, scope='global' for only global ones.", tags=("readonly",), metadata={"service_component": "persona"}),
        StructuredTool.from_function(func=_think, name="persona_think", description="Consult a thinking persona by name or id. Searches local (thread-scoped) first then global by default. Pass scope='local' to search only local, scope='global' to search only global.", tags=("readonly",), metadata={"service_component": "persona"}),
    )
