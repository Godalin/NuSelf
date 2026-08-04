"""LangChain tools for dynamic persona prompts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import component, mutating, observed, readonly, tool
from nuself.agent.errors import AgentError
from nuself.agent.text import TextAgent
from nuself.config.settings import RuntimePaths
from nuself.persona.prompt_repo import PersonaPrompt, PersonaPromptRepository, create_persona_prompt
from nuself.persona.service import PersonaService
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.persona.audit import PERSONA_AUDIT
from nuself.storage.workspace import ScopedWorkspace, WorkspaceCollection
from nuself.trace.service import TraceRecorder


def build_persona_tools(
    project_root: Path | None = None,
    *,
    repository: PersonaService,
    trace_recorder: TraceRecorder,
    text_agent: TextAgent,
) -> tuple[StructuredTool, ...]:
    """Build persona tools that any agent (chat, reason) can use."""

    repo = repository
    persona_agent = text_agent

    executor = FeatureExecutor()

    @tool(
        name="persona_craft",
        description="Create or update a reusable thinking persona with a name and custom prompt.",
    )
    @component("persona")
    @mutating
    @observed
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

        persona = create_persona_prompt(name, prompt)
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
        _record_prompt_trace(
            persona,
            project_root=project_root,
            recorder=trace_recorder,
        )
        result = f"Created thinking persona '{name}' (id={persona.id}). Use persona_think to consult it."
        return result

    @tool(
        name="persona_list",
        description="List available thinking personas with id and name. Pass include_disabled=True to show disabled ones.",
    )
    @component("persona")
    @readonly
    @observed
    def persona_list(include_disabled: bool = False) -> str:
        """List available thinking personas with id and name. Pass include_disabled=True to show disabled ones."""
        all_prompts = repo.list()
        prompts = all_prompts if include_disabled else [p for p in all_prompts if not p.disabled]
        if not prompts:
            if all_prompts:
                result = "All thinking personas are disabled. Use persona_enable tool or :persona enable to reactivate one."
            else:
                result = "No thinking personas available. Use persona_craft to create one."
        else:
            lines = ["Available thinking personas:"]
            for p in prompts:
                tag = " [disabled]" if p.disabled else ""
                lines.append(f"  - {p.name} (id={p.id}){tag}")
            result = "\n".join(lines)
        return result

    @tool(
        name="persona_think",
        description="Consult a thinking persona by name or id and get its response to a question.",
    )
    @component("persona")
    @readonly
    @observed
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

        if prompt.disabled:
            return f"Persona '{prompt.name}' is disabled. Use persona_enable tool or CLI to reactivate it."

        messages = [
            SystemMessage(content=prompt.prompt),
            HumanMessage(content=question),
        ]
        try:
            response = persona_agent.invoke(messages)
        except AgentError as exc:
            return (
                f"Error consulting persona '{prompt.name}': "
                f"{diagnostic_exception_message(exc)}"
            )

        return response

    @tool(
        name="persona_disable",
        description="Disable a thinking persona by name or id. Disabled personas are hidden from persona_list and cannot be consulted.",
    )
    @component("persona")
    @mutating
    @observed
    def persona_disable(persona: str) -> str:
        """Disable a thinking persona by name or id. Disabled personas are hidden from persona_list and cannot be consulted."""
        persona = persona.strip()
        if not persona:
            return "Error: persona must be a non-empty string (name or id)"
        prompt = repo.resolve(persona)
        if prompt is None:
            return f"No persona found for '{persona}'."
        if prompt.disabled:
            return f"Persona '{prompt.name}' is already disabled."
        repo.set_disabled(prompt.id, True)
        _record_prompt_disabled_trace(
            prompt,
            project_root=project_root,
            recorder=trace_recorder,
        )
        return f"Disabled persona: {prompt.name}"

    @tool(
        name="persona_enable",
        description="Enable a thinking persona by name or id. Enabled personas appear in persona_list and can be consulted.",
    )
    @component("persona")
    @mutating
    @observed
    def persona_enable(persona: str) -> str:
        """Enable a thinking persona by name or id. Enabled personas appear in persona_list and can be consulted."""
        persona = persona.strip()
        if not persona:
            return "Error: persona must be a non-empty string (name or id)"
        prompt = repo.resolve(persona)
        if prompt is None:
            return f"No persona found for '{persona}'."
        if not prompt.disabled:
            return f"Persona '{prompt.name}' is already enabled."
        repo.set_disabled(prompt.id, False)
        _record_prompt_enabled_trace(
            prompt,
            project_root=project_root,
            recorder=trace_recorder,
        )
        return f"Enabled persona: {prompt.name}"

    return (
        materialize_tool(persona_craft, executor=executor),
        materialize_tool(persona_list, executor=executor),
        materialize_tool(persona_think, executor=executor),
        materialize_tool(persona_disable, executor=executor),
        materialize_tool(persona_enable, executor=executor),
    )


def _record_prompt_trace(
    prompt: PersonaPrompt,
    *,
    project_root: Path | None = None,
    recorder: TraceRecorder,
) -> None:
    def record() -> object:
        return recorder.record_persona_prompt_created(
            persona_prompt_id=prompt.id,
            name=prompt.name,
        )

    PERSONA_AUDIT.observe(
        record,
        event="trace_recording_failed",
        project_root=project_root,
        metadata={"persona_prompt_id": prompt.id, "action": "create"},
    )


def _record_prompt_disabled_trace(
    prompt: PersonaPrompt,
    *,
    project_root: Path | None = None,
    recorder: TraceRecorder,
) -> None:
    def record() -> object:
        return recorder.record_persona_disabled(
            persona_prompt_id=prompt.id,
            name=prompt.name,
            participants=["agent"],
        )

    PERSONA_AUDIT.observe(
        record,
        event="trace_recording_failed",
        project_root=project_root,
        metadata={"persona_prompt_id": prompt.id, "action": "disable"},
    )


def _record_prompt_enabled_trace(
    prompt: PersonaPrompt,
    *,
    project_root: Path | None = None,
    recorder: TraceRecorder,
) -> None:
    def record() -> object:
        return recorder.record_persona_enabled(
            persona_prompt_id=prompt.id,
            name=prompt.name,
            participants=["agent"],
        )

    PERSONA_AUDIT.observe(
        record,
        event="trace_recording_failed",
        project_root=project_root,
        metadata={"persona_prompt_id": prompt.id, "action": "enable"},
    )


def build_reason_persona_tools(
    *,
    paths: RuntimePaths,
    global_repository: PersonaService,
    trace_recorder: TraceRecorder,
    get_thread_workspace: Callable[[], ScopedWorkspace],
    text_agent: TextAgent,
) -> tuple[StructuredTool, ...]:
    """Build persona tools scoped to a reason thread.

    *get_thread_workspace* is called on each tool invocation to resolve the
    current thread's private workspace, allowing the same tool instances to be
    reused across threads.

    - ``persona_craft`` stores in the thread's private workspace only.
    - ``persona_list`` merges global + local personas.
    - ``persona_think`` resolves from thread first, then global.
    """

    def _thread_repo() -> PersonaService:
        return PersonaService(
            PersonaPromptRepository(
                WorkspaceCollection(
                    get_thread_workspace(),
                    namespace="persona_prompts",
                ),
                paths,
            )
        )

    global_repo = global_repository
    persona_agent = text_agent
    executor = FeatureExecutor()

    @tool(
        name="persona_craft",
        description="Create or update a thinking persona scoped to the current reason thread.",
    )
    @component("persona")
    @mutating
    @observed
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
        persona = create_persona_prompt(name, prompt)
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
        _record_prompt_trace(
            persona,
            project_root=paths.authority_root,
            recorder=trace_recorder,
        )
        result = f"Created thinking persona '{name}' (id={persona.id}, scoped to this reason thread)."
        return result

    @tool(
        name="persona_list",
        description="List global and current reason-thread thinking personas, optionally filtered by scope.",
    )
    @component("persona")
    @readonly
    @observed
    def _list(scope: str = "", include_disabled: bool = False) -> str:
        repo = _thread_repo()
        thread_prompts = repo.list()
        raw_global = global_repo.list()
        global_prompts = [p for p in raw_global if include_disabled or not p.disabled]
        local_list = thread_prompts if scope in ("", "local") else ()
        global_list = global_prompts if scope in ("", "global") else ()
        all_prompts = list(global_list) + list(local_list)
        if not all_prompts:
            if raw_global and not include_disabled and scope in ("", "global"):
                result = "All global personas are disabled. Use persona_enable tool or CLI to reactivate one."
            else:
                result = "No thinking personas available. Use persona_craft to create one."
        else:
            lines = ["Available thinking personas:"]
            for p in all_prompts:
                tag = " [local]" if scope == "" and repo.get(p.id) is not None else ""
                tag += " [disabled]" if p.disabled else ""
                lines.append(f"  - {p.name} (id={p.id}){tag}")
            result = "\n".join(lines)
        return result

    @tool(
        name="persona_think",
        description="Consult a thinking persona, resolving thread-local before global by default.",
    )
    @component("persona")
    @readonly
    @observed
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
        if prompt is None and scope in ("", "global"):
            prompt = global_repo.resolve(persona)
        if prompt is not None and prompt.disabled and scope in ("", "global"):
            return f"Persona '{prompt.name}' is disabled. Use persona_enable tool or CLI to reactivate it."
        if prompt is None:
            available: list[str] = []
            available.extend(p.name for p in global_repo.list())
            available.extend(p.name for p in thread_repo_inst.list())
            if available:
                return f"No persona found for '{persona}'. Available: {', '.join(available)}"
            return f"No persona found for '{persona}'. Use persona_craft to create one first."

        messages = [
            SystemMessage(content=prompt.prompt),
            HumanMessage(content=question),
        ]
        try:
            result = persona_agent.invoke(messages)
        except AgentError as exc:
            return (
                "persona_think failed: "
                f"{diagnostic_exception_message(exc)}"
            )
        return result

    @tool(
        name="persona_disable",
        description="Disable a global thinking persona by name or id.",
    )
    @component("persona")
    @mutating
    @observed
    def _disable(persona: str) -> str:
        """Disable a global thinking persona by name or id. Disabled personas are hidden from persona_list and cannot be consulted."""
        persona = persona.strip()
        if not persona:
            return "Error: persona must be a non-empty string (name or id)"
        prompt = global_repo.resolve(persona)
        if prompt is None:
            return f"No global persona found for '{persona}'."
        if prompt.disabled:
            return f"Persona '{prompt.name}' is already disabled."
        global_repo.set_disabled(prompt.id, True)
        _record_prompt_disabled_trace(
            prompt,
            project_root=paths.authority_root,
            recorder=trace_recorder,
        )
        return f"Disabled persona: {prompt.name}"

    @tool(
        name="persona_enable",
        description="Enable a global thinking persona by name or id.",
    )
    @component("persona")
    @mutating
    @observed
    def _enable(persona: str) -> str:
        """Enable a global thinking persona by name or id. Enabled personas appear in persona_list and can be consulted."""
        persona = persona.strip()
        if not persona:
            return "Error: persona must be a non-empty string (name or id)"
        prompt = global_repo.resolve(persona)
        if prompt is None:
            return f"No global persona found for '{persona}'."
        if not prompt.disabled:
            return f"Persona '{prompt.name}' is already enabled."
        global_repo.set_disabled(prompt.id, False)
        _record_prompt_enabled_trace(
            prompt,
            project_root=paths.authority_root,
            recorder=trace_recorder,
        )
        return f"Enabled persona: {prompt.name}"

    return (
        materialize_tool(_craft, executor=executor),
        materialize_tool(_list, executor=executor),
        materialize_tool(_think, executor=executor),
        materialize_tool(_disable, executor=executor),
        materialize_tool(_enable, executor=executor),
    )
