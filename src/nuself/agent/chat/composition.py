"""Chat-owned conversation-runtime composition for process surfaces."""

from __future__ import annotations

from nuself.agent.chat.types import (
    ChatAgentSettings,
    ChatResult,
)
from nuself.agent.chat.engine import ConversationGraphRuntime
from nuself.agent.chat.resources import ConversationResources
from nuself.agent.outcome import ToolOutcomeProjection
from nuself.agent.tools.resources import ToolResources
from nuself.agent.chat.response import (
    BasicConversationResponseService,
    ConversationResponseService,
)
from nuself.agent.text import LangChainTextAgent
from nuself.config.settings import RuntimePaths, SystemConfig
from nuself.conversation import ConversationService
from nuself.memory.service import MemoryService
from nuself.persona.service import PersonaService
from nuself.application.projection import load_personas_from_memory
from nuself.reason.output_contracts import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.reflection.service import ReflectionService
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.feature.protocol import ToolEffectPort
from nuself.runtime.job.message import JobSink
from nuself.agent.endpoint import configured_langchain_chat_models
from nuself.agent.endpoint import LangChainLLMEndpoint
from nuself.log.store import runtime_event_log_sink
from nuself.trace.composition import TraceServices
from nuself.source.service import SourceService

__all__ = ["ChatResult", "compose_conversation_runtime"]


def compose_conversation_runtime(
    paths: RuntimePaths,
    config: SystemConfig,
    conversations: ConversationService,
    memory_service: MemoryService,
    source_service: SourceService,
    reflection_service: ReflectionService,
    reason_service: ReasonService,
    trace: TraceServices,
    persona_prompts: PersonaService,
    *,
    job_sink: JobSink | None = None,
    section_planner: SectionPlanner | None = None,
    event_publisher: EventPublisher | None = None,
    response_service: (
        ConversationResponseService | BasicConversationResponseService | None
    ) = None,
    effect_port: ToolEffectPort | None = None,
    tool_outcomes: ToolOutcomeProjection | None = None,
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
            sources=source_service,
            reflections=reflection_service,
            reasons=reason_service,
            traces=trace.query,
            personas=persona_prompts,
            persona_agent=LangChainTextAgent(
                endpoints=models,
                project_root=paths.authority_root,
                component="persona",
            ),
            trace_recorder=trace.recorder,
            job_sink=job_sink,
            section_planner=section_planner,
        ),
        trace_recorder=trace.recorder,
        personas=load_personas_from_memory(
            memory_service,
            project_root=paths.authority_root,
        ),
        conversation_store=conversations,
        reflection_settings=config.reflection,
        language_preference=config.chat.language_preference,
        tool_outcomes=tool_outcomes,
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
        effect_port=effect_port,
    )
