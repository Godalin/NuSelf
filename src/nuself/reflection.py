"""Daemon reflection scheduler with cooldowns and quiet hours."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from nuself.config import runtime_paths
from nuself.config_system import ConfigSystem, ReflectionSettings
from nuself.domain.memory import now_iso
from nuself.domain.proactive import IdeaCandidate, IdeaCandidateType, RelevanceScore
from nuself.notification import NotificationOutbox, OutboxEntry
from nuself.persona_discussion_service import SharedPersonaDiscussionService

if TYPE_CHECKING:
    from nuself.llm import ChatLLM


@dataclass(frozen=True)
class ReflectionEvent:
    """Event that can trigger an immediate reflection cycle."""

    event_type: str
    payload: dict[str, object]
    created_at: str


class ReflectionScheduler:
    """Decides when the daemon should run a self-reflection cycle."""

    def __init__(self, project_root: Path | None = None, config: ReflectionSettings | None = None) -> None:
        paths = runtime_paths(project_root)
        self._project_root = paths.project_root

        if config is not None:
            self._config = config
        else:
            system_config = ConfigSystem.load(project_root=project_root)
            self._config = system_config.reflection

        self._last_reflection_path = paths.runtime_dir / "last_reflection.json"
        self._outbox = NotificationOutbox(project_root)
        self._event_queue: list[ReflectionEvent] = []

    def trigger_event(self, event: ReflectionEvent) -> None:
        """Queue an event-triggered reflection request."""
        self._event_queue.append(event)

    def should_reflect(self, now: datetime | None = None) -> bool:
        """Allow reflection to run without time-based restrictions.

        This intentionally removes quiet hours, cooldown, interval, and daily
        cap checks so the scheduler may run whenever the daemon's check loop
        invokes it. The daemon still controls frequency via its
        `reflection_check_interval_seconds` setting.
        """
        return True

    def reflect(self, now: datetime | None = None) -> bool:
        """Run one reflection cycle if conditions pass."""
        from nuself.logs import write_log_event
        
        if now is None:
            now = datetime.now(UTC)
        
        if not self.should_reflect(now):
            return False
        
        write_log_event(
            "reflection",
            "cycle_started",
            "reflection cycle triggered",
            project_root=self._project_root,
            level="info",
            status="started"
        )
        
        # Consume any queued events before generating candidates
        self._event_queue.clear()
        candidates = IdeaCandidateGenerator(self._project_root, config=self._config).generate()
        if not candidates:
            write_log_event(
                "reflection",
                "cycle_no_candidates",
                "reflection cycle generated no candidates",
                project_root=self._project_root,
                level="info",
                status="completed",
                metadata={"reason": "no_candidates"}
            )
            return False
        
        gate = RelevanceGate(self._project_root, config=self._config)
        best = candidates[0]
        score = gate.score(best)
        if not score.passes:
            write_log_event(
                "reflection",
                "cycle_filtered",
                f"best candidate filtered by relevance gate: {best.title}",
                project_root=self._project_root,
                level="info",
                status="completed",
                metadata={"reason": "filtered_by_gate", "score": float(score.composite)}
            )
            return False
        
        # High-value candidates go through competitive persona discussion
        title = best.title
        body = best.body
        if score.composite >= self._config.gate.persona_discussion_threshold:
            result = SharedPersonaDiscussionService(
                project_root=self._project_root,
                config=self._config,
            ).discuss(best)
            self._write_discussion_log(best, score, result, now)
            if not result.approved:
                write_log_event(
                    "reflection",
                    "cycle_discussion_rejected",
                    f"persona discussion rejected candidate: {best.title}",
                    project_root=self._project_root,
                    level="info",
                    status="completed",
                    metadata={"reason": "discussion_rejected"}
                )
                return False
            title = result.revised_title
            body = result.revised_body
        
        intent = self._candidate_to_outbox_entry(best, now, title=title, body=body)
        self._write_last_reflection(now, title=title, body=body)
        self._outbox.add(intent)
        
        write_log_event(
            "reflection",
            "cycle_completed",
            f"reflection cycle published: {title}",
            project_root=self._project_root,
            level="info",
            status="completed",
            metadata={"reason": "published", "score": float(score.composite), "idea_type": best.candidate_type}
        )
        return True

    def _in_quiet_hours(self, now: datetime) -> bool:
        current_hour = now.hour
        start = self._config.scheduler.quiet_start_hour
        end = self._config.scheduler.quiet_end_hour
        if start < end:
            return start <= current_hour < end
        # Wraps around midnight, e.g. 22:00–07:00
        return current_hour >= start or current_hour < end

    def _in_cooldown(self, now: datetime) -> bool:
        last = self._read_last_reflection()
        if last is None:
            return False
        elapsed = (now - last).total_seconds()
        return elapsed < self._config.scheduler.cooldown_seconds

    def _interval_not_elapsed(self, now: datetime) -> bool:
        last = self._read_last_reflection()
        if last is None:
            return False
        jittered = self._jittered_interval()
        elapsed = (now - last).total_seconds()
        return elapsed < jittered

    def _jittered_interval(self) -> int:
        import random

        base = self._config.scheduler.interval_seconds
        jitter = base * self._config.scheduler.jitter_percent // 100
        if jitter == 0:
            return base
        return base + random.randint(-jitter, jitter)

    def _daily_cap_not_reached(self, now: datetime) -> bool:
        count = self._reflection_count_today(now)
        return count < self._config.scheduler.daily_cap

    def _reflection_count_today(self, now: datetime) -> int:
        if not self._last_reflection_path.exists():
            return 0
        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        if not isinstance(raw, dict):
            return 0
        data = cast(dict[str, object], raw)
        count = data.get("daily_count")
        date = data.get("daily_date")
        if not isinstance(count, int) or not isinstance(date, str):
            return 0
        if date == now.date().isoformat():
            return count
        return 0

    def _read_last_reflection(self) -> datetime | None:
        if not self._last_reflection_path.exists():
            return None
        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        data = cast(dict[str, object], raw)
        ts_raw = data.get("timestamp")
        if not isinstance(ts_raw, str):
            return None
        try:
            return datetime.fromisoformat(ts_raw)
        except ValueError:
            return None

    def _write_last_reflection(self, now: datetime, title: str | None = None, body: str | None = None) -> None:
        self._last_reflection_path.parent.mkdir(parents=True, exist_ok=True)
        count = self._reflection_count_today(now) + 1
        payload: dict[str, object] = {
            "timestamp": now.isoformat(),
            "daily_count": count,
            "daily_date": now.date().isoformat(),
        }
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        self._last_reflection_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _candidate_to_outbox_entry(
        self,
        candidate: IdeaCandidate,
        now: datetime,
        title: str | None = None,
        body: str | None = None,
    ) -> OutboxEntry:
        from nuself.notification.deep_link import DeepLink

        thread_id = candidate.suggested_thread_id or "reflections"
        deep_link = DeepLink(action="open_thread", thread_id=thread_id).to_url()
        return OutboxEntry(
            id=f"reflection-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}",
            title=title if title is not None else candidate.title,
            body=body if body is not None else candidate.body,
            status="pending",
            idempotency_key=f"reflection-{now.date().isoformat()}",
            deep_link=deep_link,
        )

    def _write_discussion_log(
        self,
        candidate: IdeaCandidate,
        score: RelevanceScore,
        result: object,
        now: datetime,
    ) -> None:
        from nuself.logs import write_log_event
        from nuself.proactive_persona import PersonaCompetitionResult

        if not isinstance(result, PersonaCompetitionResult):
            return
        metadata: dict[str, object] = {
            "candidate_id": candidate.id,
            "candidate_title": candidate.title,
            "candidate_type": candidate.candidate_type,
            "composite": round(score.composite, 3),
            "approved": result.approved,
            "scores": {k: round(v, 3) for k, v in result.scores.items()},
            "blocking_vetos": list(result.blocking_vetos),
            "winner_persona_ids": list(result.winner_persona_ids),
            "emergent_persona_ids": list(result.emergent_persona_ids),
            "discussion_trace": list(result.discussion_trace),
            "revised_title": result.revised_title,
            "revised_body": result.revised_body,
        }
        status = "approved" if result.approved else "rejected"
        write_log_event(
            "reflection",
            "persona_discussion",
            f"[{status}] {candidate.title} — {result.reason}",
            project_root=self._project_root,
            status=status,
            metadata=metadata,
        )


class RelevanceGate:
    """Multi-dimensional relevance gate for proactive candidates."""

    def __init__(self, project_root: Path | None = None, config: ReflectionSettings | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._last_reflection_path = paths.runtime_dir / "last_reflection.json"

        if config is not None:
            self._config = config
        else:
            system_config = ConfigSystem.load(project_root=project_root)
            self._config = system_config.reflection

    def score(self, candidate: IdeaCandidate) -> RelevanceScore:
        novelty = self._score_novelty(candidate)
        confidence = max(0.0, min(1.0, candidate.confidence))
        urgency = max(0.0, min(1.0, candidate.urgency))
        interruption_cost = max(0.0, min(1.0, candidate.interruption_cost))
        cooldown_ok = self._cooldown_ok()

        composite = (
            novelty * 0.25
            + confidence * 0.20
            + urgency * 0.25
            - interruption_cost * 0.15
            + (1.0 if cooldown_ok else 0.0) * 0.15
        )
        composite = max(0.0, min(1.0, composite))

        reasons: list[str] = []
        if novelty < 0.5:
            reasons.append("low_novelty")
        if confidence < 0.5:
            reasons.append("low_confidence")
        if urgency >= 0.7:
            reasons.append("high_urgency")
        if interruption_cost >= 0.7:
            reasons.append("high_interruption_cost")
        if not cooldown_ok:
            reasons.append("cooldown_active")
        if not reasons:
            reasons.append("ok")

        threshold = self._config.gate.relevance_threshold
        passes = composite >= threshold and not (interruption_cost >= 0.9 and urgency < 0.5)

        return RelevanceScore(
            passes=passes,
            novelty=novelty,
            confidence=confidence,
            urgency=urgency,
            interruption_cost=interruption_cost,
            cooldown_ok=cooldown_ok,
            composite=composite,
            reasons=tuple(reasons),
        )

    def passes(self, candidate: IdeaCandidate) -> bool:
        return self.score(candidate).passes

    def _score_novelty(self, candidate: IdeaCandidate) -> float:
        if not self._last_reflection_path.exists():
            return 1.0
        last_title = self._read_last_title()
        last_body = self._read_last_body()
        # Same title → same topic, skip
        if last_title is not None and candidate.title == last_title:
            return 0.0
        # Partial body overlap → reduced novelty
        if last_body is not None:
            if candidate.body == last_body:
                return 0.1
            if candidate.body in last_body or last_body in candidate.body:
                return 0.5
        return 1.0

    def _cooldown_ok(self) -> bool:
        if not self._last_reflection_path.exists():
            return True
        last = self._read_last_timestamp()
        if last is None:
            return True
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = (now - last).total_seconds()
        return elapsed >= 300  # default cooldown 5 minutes

    def _read_last_body(self) -> str | None:
        if not self._last_reflection_path.exists():
            return None
        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        data = cast(dict[str, object], raw)
        body = data.get("body")
        return body if isinstance(body, str) else None

    def _read_last_title(self) -> str | None:
        if not self._last_reflection_path.exists():
            return None
        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        data = cast(dict[str, object], raw)
        title = data.get("title")
        return title if isinstance(title, str) else None

    def _read_last_timestamp(self) -> datetime | None:
        if not self._last_reflection_path.exists():
            return None
        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        data = cast(dict[str, object], raw)
        ts_raw = data.get("timestamp")
        if not isinstance(ts_raw, str):
            return None
        try:
            return datetime.fromisoformat(ts_raw)
        except ValueError:
            return None


class IdeaCandidateGenerator:
    """Proactively generate new ideas from memory, sources, and conversations.

    The daemon calls this periodically. It reads whatever data exists and uses
    the LLM to produce genuinely new ideas — connections, contradictions,
    questions, and actions that the user hasn't explicitly asked about.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        config: ReflectionSettings | None = None,
    ) -> None:
        from nuself.config import runtime_paths
        from nuself.llm import default_llm

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._llm: ChatLLM = llm or default_llm(self._project_root)
        
        if config is not None:
            self._config_obj = config
            return
        system_config = ConfigSystem.load(project_root=self._project_root)
        self._config_obj = system_config.reflection

    def generate(self, max_candidates: int = 3) -> list[IdeaCandidate]:
        from nuself.logs import write_log_event
        
        context = self._collect_context()
        if context.is_empty():
            write_log_event(
                "reflection",
                "candidate_generation_skipped",
                "no context available for idea generation",
                project_root=self._project_root,
                level="debug",
                status="skipped",
                metadata={"reason": "empty_context"}
            )
            return []
        try:
            return self._generate_with_llm(context, max_candidates)
        except (RuntimeError, ValueError, json.JSONDecodeError) as e:
            write_log_event(
                "reflection",
                "candidate_generation_failed",
                f"failed to generate candidates: {type(e).__name__}",
                project_root=self._project_root,
                level="warning",
                status="error",
                error=str(e)
            )
            return []

    def _collect_context(self) -> _ThinkingContext:
        threads = self._recent_thread_context()
        memories = self._recent_memory_context()
        profile = self._profile_context()
        sources = self._new_source_context()
        return _ThinkingContext(
            threads=threads,
            memories=memories,
            profile=profile,
            sources=sources,
        )

    def _generate_with_llm(self, context: _ThinkingContext, max_candidates: int) -> list[IdeaCandidate]:
        from nuself.llm import ChatMessage

        system_prompt = (
            "You are an independent thinker with access to someone's private memory, "
            "conversation history, reading notes, and personal profile.\n\n"
            "Your job: generate NEW ideas that the person hasn't explicitly asked about. "
            "Look for:\n"
            "- Contradictions between different memories or stated beliefs\n"
            "- Connections between seemingly unrelated topics\n"
            "- Unexplored questions suggested by the data\n"
            "- Actionable insights or recommendations\n"
            "- Patterns the person might not have noticed\n\n"
            "Do NOT summarize or rephrase existing content. "
            "Do NOT produce generic observations. "
            "Each idea must be genuinely novel — something the person would not have thought of on their own.\n\n"
            "Return a JSON object with a 'candidates' array (1 to 3 items). Each candidate:\n"
            '{\n'
            '  "title": "short title (max 80 chars)",\n'
            '  "body": "2-4 sentences describing the new idea",\n'
            '  "candidate_type": "question|connection|contradiction|action|profile_update",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "novelty": 0.0-1.0,\n'
            '  "urgency": 0.0-1.0,\n'
            '  "interruption_cost": 0.0-1.0\n'
            '}\n\n'
            "Return ONLY the JSON object. No markdown fences."
        )

        user_message = context.to_prompt()
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]
        raw = self._llm.complete(messages)
        return self._parse_candidates(raw, max_candidates)

    def _parse_candidates(self, raw: str, max_candidates: int) -> list[IdeaCandidate]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()
        parsed: object = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")
        data = cast(dict[str, object], parsed)
        raw_candidates = data.get("candidates")
        if not isinstance(raw_candidates, list):
            raise ValueError("LLM response missing 'candidates' array")
        candidates_list = cast(list[object], raw_candidates)

        valid_types = {"question", "connection", "contradiction", "action", "profile_update", "share_bundle"}
        results: list[IdeaCandidate] = []
        for item in candidates_list[:max_candidates]:
            if not isinstance(item, dict):
                continue
            c = cast(dict[str, object], item)
            title = c.get("title")
            body = c.get("body")
            if not isinstance(title, str) or not isinstance(body, str):
                continue
            candidate_type = c.get("candidate_type", "question")
            if not isinstance(candidate_type, str) or candidate_type not in valid_types:
                candidate_type = "question"
            results.append(IdeaCandidate(
                id=f"candidate-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{datetime.now(UTC).microsecond:06d}",
                title=title[:80],
                body=body,
                candidate_type=cast(IdeaCandidateType, candidate_type),
                confidence=_clamp_float(c.get("confidence"), 0.5),
                novelty=_clamp_float(c.get("novelty"), 0.5),
                urgency=_clamp_float(c.get("urgency"), 0.3),
                interruption_cost=_clamp_float(c.get("interruption_cost"), 0.2),
                evidence_refs=(),
                suggested_thread_id=None,
                source_summary="llm-generated",
                created_at=now_iso(),
            ))
        if not results:
            raise ValueError("LLM returned no valid candidates")
        return results

    def _recent_thread_context(self, max_threads: int = 5, max_messages: int = 10) -> str:
        from nuself.agent.chat import ThreadStore

        store = ThreadStore(self._project_root)
        lines: list[str] = []
        for thread_id in reversed(store.list()[-max_threads:]):
            state = store.load(thread_id)
            lines.append(f"Thread {thread_id}:")
            for msg in state.messages[-max_messages:]:
                lines.append(f"  {msg.role}: {msg.content[:120]}")
        return "\n".join(lines)

    def _recent_memory_context(self, max_entries: int = 8) -> str:
        from nuself.memory.repository import MemoryEntryRepository

        repo = MemoryEntryRepository(self._project_root)
        lines: list[str] = []
        for entry in repo.list()[-max_entries:]:
            lines.append(f"- [{entry.type}] {entry.title}: {entry.body[:120]}")
        return "\n".join(lines)

    def _profile_context(self, max_items: int = 10) -> str:
        from nuself.profile.repository import ProfileItemRepository

        repo = ProfileItemRepository(self._project_root)
        lines: list[str] = []
        for item in repo.list()[:max_items]:
            tags = f" (tags: {', '.join(item.tags)})" if item.tags else ""
            lines.append(f"- [{item.type}] {item.title}{tags}: {item.body[:120]}")
        return "\n".join(lines)

    def _new_source_context(self, max_sources: int = 5) -> str:
        from nuself.memory.source_repository import SourceRepository

        repo = SourceRepository(self._project_root)
        lines: list[str] = []
        for doc in repo.list_documents()[-max_sources:]:
            lines.append(f"- {doc.title or doc.id}")
        return "\n".join(lines)


@dataclass(frozen=True)
class _ThinkingContext:
    """All available material for proactive idea generation."""

    threads: str
    memories: str
    profile: str
    sources: str

    def is_empty(self) -> bool:
        return not (self.threads or self.memories or self.profile or self.sources)

    def to_prompt(self) -> str:
        sections: list[str] = []
        if self.memories:
            sections.append(f"## Memory entries\n{self.memories}")
        if self.threads:
            sections.append(f"## Recent conversations\n{self.threads}")
        if self.profile:
            sections.append(f"## Personal profile\n{self.profile}")
        if self.sources:
            sections.append(f"## Source documents\n{self.sources}")
        return "\n\n".join(sections)


def _clamp_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return default
