"""Application-owned artifact summaries for Trace provenance queries."""

from __future__ import annotations

from nuself.conversation import ConversationService
from nuself.memory.service import MemoryService
from nuself.profile.service import ProfileService
from nuself.reason.service import ReasonService
from nuself.reflection.service import ReflectionService
from nuself.source.service import SourceService
from nuself.trace.provenance import ProvenanceService
from nuself.trace.service import TraceQueryService


class ApplicationArtifactResolver:
    """Resolve artifact summaries without crossing repository boundaries."""

    def __init__(
        self,
        *,
        conversations: ConversationService,
        memory: MemoryService,
        profiles: ProfileService,
        sources: SourceService,
        reason: ReasonService,
        reflection: ReflectionService,
    ) -> None:
        self._conversations = conversations
        self._memory = memory
        self._profiles = profiles
        self._sources = sources
        self._reason = reason
        self._reflection = reflection

    def resolve(self, artifact_ref: str) -> str | None:
        try:
            if artifact_ref.startswith(("conversation_turn:", "conversation_range:")):
                turn = self._conversations.resolve_turn(artifact_ref)
                if turn is None:
                    return None
                return (
                    f"user: {turn.user_content} | "
                    f"assistant: {turn.assistant_content}"
                )
            if artifact_ref.startswith("memory:"):
                entry = self._memory.get_entry(artifact_ref.removeprefix("memory:"))
                return f"{entry.title}: {entry.body}"
            if artifact_ref.startswith("profile:"):
                item = self._profiles.get_item(artifact_ref.removeprefix("profile:"))
                return f"{item.title}: {item.body}"
            if artifact_ref.startswith("source:"):
                document = self._sources.get(artifact_ref.removeprefix("source:"))
                return document.title or document.id
            if artifact_ref.startswith("reason:"):
                thread = self._reason.show_thread(artifact_ref.removeprefix("reason:"))
                return f"{thread.topic}: {thread.working_summary}"
            if artifact_ref.startswith("reflection:"):
                entry = self._reflection.get_entry(
                    artifact_ref.removeprefix("reflection:")
                )
                return f"{entry.title}: {entry.body}"
        except (KeyError, ValueError):
            return None
        return None


def compose_provenance_service(
    traces: TraceQueryService,
    *,
    conversations: ConversationService,
    memory: MemoryService,
    profiles: ProfileService,
    sources: SourceService,
    reason: ReasonService,
    reflection: ReflectionService,
) -> ProvenanceService:
    """Compose traversal with public artifact-summary services."""

    return ProvenanceService(
        traces,
        artifact_resolver=ApplicationArtifactResolver(
            conversations=conversations,
            memory=memory,
            profiles=profiles,
            sources=sources,
            reason=reason,
            reflection=reflection,
        ),
    )
