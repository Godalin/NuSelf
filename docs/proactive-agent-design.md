# Proactive Agent Design — Milestone 10

## Context

This design turns the existing skeleton (`reflection.py`, `notification/`, daemon background threads) into a real proactive agent that can surface worthwhile ideas without becoming noisy.

## Current Baseline vs. Gap

| Component                | Current State                                                                                                                                                                         | Gap to Milestone 10 |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| `ReflectionScheduler`    | Randomized jitter, daily cap, quiet hours, cooldown, event triggers. Background thread in daemon polls. Configurable via `private/config.yaml` under `reflection.*`.                  | Done.               |
| `IdeaCandidateGenerator` | Uses LLM to scan recent threads, private memory, and new sources. Generates structured candidates with types, confidence, and evidence. Falls back to local candidate on LLM failure. | Done.               |
| `RelevanceGate`          | Multi-dimensional scoring: novelty, confidence, urgency, cooldown, interruption cost. Uses `config.relevance_threshold` from YAML config.                                             | Done.               |
| `NotificationOutbox`     | File-backed with idempotency, statuses, and CRUD. Daemon writes intents here without calling adapters directly.                                                                       | Done.               |
| `DeepLink`               | Supports both `open_thread` and `new_thread` actions.                                                                                                                                 | Done.               |
| `Adapters`               | `NotificationDeliveryLoop` polls pending outbox entries and dispatches through configured adapters.                                                                                   | Done.               |
| `Daemon`                 | `reflect()` writes to outbox only; delivery thread handles adapters separately. Discussion traces persisted to reflection log.                                                        | Done.               |

## Design Decisions

### 1. Keep Outbox as the Single Source of Truth

All proactive agent nodes write `NotificationIntent` (outbox entries) to the file-backed outbox. No agent node ever calls an adapter directly. The daemon runs a `NotificationDeliveryLoop` that polls pending entries and dispatches them.

### 2. Structured Idea Candidates

Replace the plain `str` body with a typed `IdeaCandidate` dataclass. The generator returns a list of candidates; the scheduler picks the highest-scoring one (or batches related ones).

### 3. Relevance Gate as Scorer, Not Boolean Filter

The gate returns a `RelevanceScore` with per-dimension floats and a final `passes` boolean. This lets us tune thresholds with config and log why candidates were dropped.

### 4. Randomized Low-Frequency Reflection

The scheduler adds a jitter factor (±20% of interval) and a daily cap (max reflections per day). This prevents predictable timing and limits noise.

### 5. Event Triggers via Lightweight Hooks

Instead of a full event bus, expose a `ReflectionTrigger` interface. The memory curator and source ingestion can call `trigger_event(type, payload)` when they produce high-signal changes. The scheduler checks both time-based and event-based conditions.

### 6. Deep Link Creates New Threads

Add `nuself://new-thread?title=...&seed=...&candidate_id=...`. The REPL / CLI deep-link handler resolves this by creating a thread with the candidate title and seed message, then opening it.

## Data Models

### IdeaCandidate

```python
@dataclass(frozen=True)
class IdeaCandidate:
    id: str
    title: str
    body: str
    candidate_type: Literal[
        "contradiction",
        "connection",
        "question",
        "action",
        "profile_update",
        "share_bundle",
    ]
    confidence: float        # 0.0–1.0
    novelty: float           # 0.0–1.0
    urgency: float           # 0.0–1.0
    interruption_cost: float # 0.0–1.0, higher = more disruptive
    evidence_refs: tuple[str, ...]
    suggested_thread_id: str | None  # None → create new thread
    source_summary: str
    created_at: str = field(default_factory=now_iso)
```

### RelevanceScore

```python
@dataclass(frozen=True)
class RelevanceScore:
    passes: bool
    novelty: float
    confidence: float
    urgency: float
    interruption_cost: float
    cooldown_ok: bool
    composite: float         # weighted sum for ranking
    reasons: tuple[str, ...]
```

### ReflectionEvent

```python
@dataclass(frozen=True)
class ReflectionEvent:
    event_type: Literal["new_memory", "new_source", "thread_milestone", "manual"]
    payload: dict[str, object]
    created_at: str = field(default_factory=now_iso)
```

### NotificationIntent (extends OutboxEntry)

Reuse existing `OutboxEntry`. Add optional `candidate_id` and `priority` fields to metadata for richer delivery policy.

## Module Interface Design

### Enhanced ReflectionScheduler

```python
class ReflectionScheduler:
    def __init__(self, project_root: Path | None = None) -> None: ...
    
    def should_reflect(self, now: datetime | None = None) -> bool: ...
    def reflect(self, now: datetime | None = None) -> bool: ...
    def trigger_event(self, event: ReflectionEvent) -> None: ...
    
    # internal
    def _time_trigger_ready(self, now: datetime) -> bool: ...
    def _event_trigger_ready(self) -> bool: ...
    def _daily_cap_not_reached(self, now: datetime) -> bool: ...
```

### Enhanced IdeaCandidateGenerator

```python
class IdeaCandidateGenerator:
    def __init__(self, project_root: Path | None = None, *, llm: ChatLLM | None = None) -> None: ...
    
    def generate(self, max_candidates: int = 3) -> list[IdeaCandidate]: ...
    
    # internal scanning
    def _recent_thread_context(self) -> str: ...
    def _recent_memory_context(self) -> str: ...
    def _new_source_context(self) -> str: ...
```

### Enhanced RelevanceGate

```python
class RelevanceGate:
    def __init__(self, project_root: Path | None = None) -> None: ...
    
    def score(self, candidate: IdeaCandidate) -> RelevanceScore: ...
    def passes(self, candidate: IdeaCandidate) -> bool: ...
```

### NotificationDeliveryLoop

```python
class NotificationDeliveryLoop:
    def __init__(
        self,
        project_root: Path | None = None,
        adapters: list[NotificationAdapter] | None = None,
    ) -> None: ...
    
    def run_once(self) -> int: ...  # returns count delivered
```

### Enhanced DeepLink

```python
@dataclass(frozen=True)
class DeepLink:
    action: Literal["open_thread", "new_thread"]
    thread_id: str | None
    title: str | None
    message: str | None
    candidate_id: str | None
    
    @classmethod
    def parse(cls, url: str) -> "DeepLink": ...
    def to_url(self) -> str: ...
    
    @classmethod
    def for_new_thread(cls, title: str, seed_message: str, candidate_id: str) -> "DeepLink": ...
```

## Competitive Persona Discussion

High-value candidates (composite score above threshold) do not go straight to the outbox. They enter a **randomized competitive persona debate**:

1. **Random Persona Selection**: From the available persona pool, randomly select 2–4 participants. No fixed mappings by candidate type—each reflection gets a different internal jury.
2. **Competitive Scoring**: Each selected persona scores the candidate (0.0–1.0) and provides a short rationale. Personas may contradict each other. For example, `historian_self` might upscore a memory connection while `skeptic_self` downscores it as speculative.
3. **Blocking Veto**: Any persona may issue a blocking concern (score < 0.3 with a strong rationale). If a blocking veto occurs, the candidate is dropped unless at least two other personas strongly override it (score > 0.8).
4. **Synthesizer Arbitration**: `synthesizer_self` reviews the competing scores and rewrites the title and body to reflect the most compelling perspective. The synthesizer may also merge multiple related candidates into a single notification if several pass together.
5. **Outcome**: Only synthesizer-approved candidates become outbox entries. Dropped candidates are logged with reasons for later tuning.

This keeps the proactive agent unpredictable and internally honest—ideas must survive internal dissent before reaching the user.

## Daemon Integration

```python
class DaemonState:
    # existing threads ...
    
    def start_background_notification_delivery(self) -> None: ...
    def stop_background_notification_delivery(self) -> None: ...
    
    def _run_background_notification_delivery(self) -> None:
        while not self.shutdown_requested.wait(delivery_interval):
            try:
                self.notification_delivery_loop.run_once()
            except RuntimeError:
                continue
```

The `ReflectionScheduler.reflect()` method should:
1. Generate candidates
2. Score each through `RelevanceGate`
3. For high-scoring candidates, run competitive persona discussion
4. Pick synthesizer-approved candidates
5. Write `NotificationIntent` entries to the outbox
6. **Not** call any adapter directly

## Implementation Steps

We implement in small, testable slices:

1. **Add `IdeaCandidate` and `RelevanceScore` models** with wire serialization tests.
2. **Enhance `IdeaCandidateGenerator`** to use LLM over thread/memory/source context. Add fixture-based tests.
3. **Enhance `RelevanceGate`** with multi-dimensional scoring. Add threshold and composite score tests.
4. **Enhance `ReflectionScheduler`** with jitter, daily cap, and event triggers. Add fake-time tests.
5. **Add `NotificationDeliveryLoop`** that polls outbox and dispatches through adapters. Add fake-adapter tests.
6. **Decouple daemon**: make `reflect()` write to outbox only; start delivery thread. Add integration tests.
7. **Enhance `DeepLink`** with `new_thread` action. Add parse/round-trip tests.
8. **Wire deep links into CLI/REPL** so `nuself attach --deep-link ...` can resolve new-thread intents.

## Test Strategy

- **Scheduler**: fake `datetime` fixtures; prove jitter, daily cap, quiet hours, cooldown, and event triggers.
- **Generator**: fixture memory/threads/sources; prove candidates have expected types and evidence refs.
- **Gate**: fixture candidates; prove low-value, duplicate, urgent, and cooldown cases.
- **Delivery loop**: fake adapters; prove graph nodes never send directly, outbox records attempts/failures/success.
- **Deep links**: fixture URLs; prove resolution creates or opens threads correctly.

## Completion Criteria

- [x] `IdeaCandidate` and `RelevanceScore` are typed, serializable, and tested.
- [x] `IdeaCandidateGenerator` scans threads, memory, and sources; produces structured candidates.
- [x] `RelevanceGate` scores across novelty, confidence, urgency, interruption cost, and cooldown.
- [x] `ReflectionScheduler` supports randomized intervals, daily caps, quiet hours, cooldowns, and event triggers.
- [x] `NotificationDeliveryLoop` polls pending outbox entries and dispatches through configured adapters.
- [x] Daemon `reflect()` writes to outbox only; adapters are called only from the delivery loop.
- [x] `DeepLink` supports both `open_thread` and `new_thread` actions.
- [x] All new code passes `uv run pytest` and `uvx pyright`.
- [x] `README.md` and `README.zh-CN.md` TODOs updated for proactive agent features.
