"""Chat-owned conversation-runtime composition for process surfaces."""

from __future__ import annotations

from nuself.agent.chat.types import (
    ChatAgentSettings,
    ChatResult,
)
from nuself.agent.chat.engine import ConversationGraphRuntime
from nuself.agent.chat.resources import ConversationResources
from nuself.agent.tools.resources import ToolResources
from nuself.agent.chat.response import ConversationResponseService
from nuself.agent.text import LangChainTextAgent
from nuself.config import RuntimePaths, SystemConfig
from nuself.conversation import ConversationStore
from nuself.memory.service import MemoryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.persona.tools import build_persona_tools
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.application.projection import load_personas_from_memory
from nuself.reason.output_contracts import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.reflection.service import ReflectionService
from nuself.runtime.events import EventPublisher
from nuself.runtime.frontend import ApprovalPort
from nuself.runtime.jobs import JobSink
from nuself.llm import configured_langchain_chat_models
from nuself.llm import LangChainLLMEndpoint
from nuself.logs import runtime_event_log_sink
from nuself.trace.composition import TraceServices
from nuself.workspace import PrivateWorkspaceStore

__all__ = ["ChatResult", "compose_conversation_runtime"]


def compose_conversation_runtime(
    paths: RuntimePaths,
    config: SystemConfig,
    conversations: ConversationStore,
    memory_service: MemoryService,
    memory_entries: MemoryEntryRepository,
    reflection_service: ReflectionService,
    reason_service: ReasonService,
    reason_workspace: PrivateWorkspaceStore,
    trace: TraceServices,
    persona_prompts: PersonaPromptRepository,
    *,
    job_sink: JobSink | None = None,
    section_planner: SectionPlanner | None = None,
    event_publisher: EventPublisher | None = None,
    response_service: ConversationResponseService | None = None,
    approval_port: ApprovalPort | None = None,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> ConversationGraphRuntime:
    """Build chat from one authority graph plus surface-owned adapters."""

    models = (
        langchain_models
        if langchain_models is not None
        else configured_langchain_chat_models(
            paths.authority_root,
            config=config,
        )
    )
    resources = ConversationResources(
        tools=ToolResources(
            project_root=paths.authority_root,
            memory=memory_service,
            reflections=reflection_service,
            reasons=reason_service,
            reason_workspace=reason_workspace,
            traces=trace.query,
            persona_tools=tuple(
                build_persona_tools(
                    paths.authority_root,
                    repository=persona_prompts,
                    trace_recorder=trace.recorder,
                    text_agent=LangChainTextAgent(
                        endpoints=models,
                        project_root=paths.authority_root,
                        component="persona",
                    ),
                )
            ),
            job_sink=job_sink,
            section_planner=section_planner,
        ),
        trace_recorder=trace.recorder,
        personas=load_personas_from_memory(
            memory_entries,
            project_root=paths.authority_root,
        ),
        conversation_store=conversations,
        reflection_settings=config.reflection,
        language_preference=config.chat.language_preference,
    )
    publisher = event_publisher
    if publisher is None:
        publisher = EventPublisher()
        publisher.attach_projection(
            runtime_event_log_sink(paths.authority_root)
        )
    return ConversationGraphRuntime(
        resources,
        langchain_models=models,
        settings=ChatAgentSettings(
            recent_messages=config.chat.context.recent_messages,
            summary_trigger_messages=(
                config.chat.context.summary_trigger_messages
            ),
            summary_target_chars=config.chat.context.summary_target_chars,
        ),
        event_publisher=publisher,
        response_service=response_service,
        approval_port=approval_port,
    )
