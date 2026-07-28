# Reflection Spec

## Architecture

The reflection subsystem has two layers:

1. **ReflectionRepository** (`private/reflections/`) — durable store for reflection ideas
2. ** reflection.log** — audit trail of scheduler events

Reflection ideas are first-class domain objects. They are **not** notification intents.

## ReflectionEntry

Stored as one JSON file per entry in `private/reflections/{id}.json`.

| Field | Type | Description |
|---|---|---|
| `id` | string | `reflection-candidate-{timestamp}-{microsecond}` |
| `title` | string | Idea title (max 80 chars) |
| `body` | string | 2-4 sentences describing the idea |
| `candidate_type` | string | `question` \| `connection` \| `contradiction` \| `action` \| `profile_update` |
| `confidence` | float | 0.0–1.0 |
| `novelty` | float | 0.0–1.0 |
| `urgency` | float | 0.0–1.0 |
| `interruption_cost` | float | 0.0–1.0 |
| `composite_score` | float | Final gate score |
| `status` | string | `pending` \| `dismissed` \| `archived` |
| `discussion_approved` | bool \| null | `null` if no discussion happened |
| `discussion_trace` | list[str] | Raw persona discussion lines |
| `deep_link` | string | `nuself://thread/reflections` |
| `created_at` | string | ISO timestamp |
| `reviewed_at` | string \| null | Set when dismissed or archived |

### Status Semantics

| Status | Meaning |
|---|---|
| `pending` | Produced by scheduler; user has not acted on it |
| `dismissed` | User explicitly dismissed (`nuself inbox reflection dismiss`) |
| `archived` | User explicitly archived (`nuself inbox reflection archive`) |

## Pipeline Flow

```
reflect()
  ├─ schedule_blocked              (if quiet hours, cooldown, interval, or daily cap blocks)
  ├─ cycle_started                 (audit log)
  ├─ organizer_started             (best-effort pending reflection cleanup)
  ├─ candidate_generation_skipped  (if no context)
  ├─ candidate_generation_failed   (if LLM errors)
  ├─ cycle_no_candidates           (if LLM returns empty)
  ├─ LLMRelevanceGate.score(best)
  │   └─ cycle_filtered            (if !passes)
  ├─ persona_discussion            (if score ≥ persona_discussion_threshold)
  │   └─ cycle_discussion_rejected (if !approved)
  └─ ReflectionRepository.add()    ( ReflectionEntry created )
       ├─ TraceRecorder.record_reflection_created()  ← kind="reflection"
       └─ auto_notify? → NotificationOutbox.add(brief notify)
```

## Trace Recording

Every published reflection must create a `ThoughtTrace` with `kind="reflection"`. This provides provenance for the reflection's existence so users can trace why it was created.

The trace is recorded by `ReflectionScheduler.reflect()` immediately after `ReflectionRepository.add()` succeeds.

Trace fields:

| ThoughtTrace Field | Value |
|---|---|
| `kind` | `"reflection"` |
| `title` | Reflection title |
| `summary` | Reflection body (2-4 sentences) |
| `inputs` | `[]` — generated proactively, not from user input |
| `evidence_refs` | `[]` (no direct evidence chain in v0.2.0) |
| `outputs` | `["reflection:{entry.id}"]` |
| `participants` | `["reflection"]` |
| `thread_id` | Key used for link building or cross-referencing, e.g. `"reflections"` |
| `visibility` | `"private"` |
| `decision_points` | `["Relevance gate passed: composite=... threshold=...", "Persona discussion approved/rejected"]` |
| `metadata` | `{"candidate_type": ..., "composite_score": ..., "discussion_approved": ...}` |

## LLMRelevanceGate Scoring

The gate is LLM-driven (L2 judgment). The LLM receives the candidate, recent reflection history, and cooldown state, then returns a structured JSON judgment:

```json
{
  "novelty": 0.0-1.0,
  "confidence": 0.0-1.0,
  "urgency": 0.0-1.0,
  "interruption_cost": 0.0-1.0,
  "composite": 0.0-1.0,
  "passes": true|false,
  "reason": "explanation of the judgment"
}
```

- All floats are clamped to `[0, 1]`.
- `passes` is the LLM's holistic judgment, not a derived formula.
- The Pydantic response models are the authoritative parse boundary. Boolean
  fields must be JSON booleans, candidate types must be declared
  `IdeaCandidateType` values, and a malformed item invalidates its complete
  candidate-generation batch. A handwritten dict parser must not coerce or
  partially accept output after schema validation fails.
- On any LLM/JSON/parsing failure, fallback to `passes=false`, `composite=0.0`, `reason="llm_fallback"`.
- `cooldown_ok` remains L1 deterministic: checked before the LLM call using `config.scheduler.cooldown_seconds`.

## Gate Thresholds

| Threshold | Default | Purpose |
|---|---|---|
| `relevance_threshold` | `0.35` | Minimum composite to enter the pipeline at all |
| `persona_discussion_threshold` | `0.55` | Composite at or above this triggers competitive persona discussion |
| `composite_threshold` | `0.4` | Minimum average persona score to approve after discussion |
| `blocking_threshold` | `0.35` | Score below this triggers a blocking veto |
| `override_threshold` | `0.7` | Score above this counts as strong support |

Candidates below `persona_discussion_threshold` but passing the gate proceed directly to `ReflectionRepository` without discussion.

## Pending Organization

There is no pending reflection count limit. Pending reflection growth is controlled by organization, not by blocking new reflection cycles.

`ReflectionOrganizer` periodically scans pending entries, groups similar ideas, keeps the highest-scoring representative pending, folds short duplicate summaries into its body, and archives duplicate entries. Organization is best-effort: failure to organize must log an error and must not block the reflection cycle.

First implementation uses deterministic text similarity over title/body tokens. LLM-assisted cleanup can be added later, but the scheduler must not depend on an LLM to avoid unbounded duplicate growth.

## Schedule Limits

The scheduler must enforce the configured deterministic schedule gates before candidate generation:

| Setting | Default | Behavior |
|---|---:|---|
| `reflection.scheduler.interval_seconds` | `3600` | Minimum elapsed time since the last published reflection before another cycle may run. Jitter may adjust the effective interval. |
| `reflection.scheduler.cooldown_seconds` | `300` | Hard minimum elapsed time since the last published reflection. |
| `reflection.scheduler.quiet_start_hour` | `22` | Start hour for local-system-time quiet hours. |
| `reflection.scheduler.quiet_end_hour` | `7` | End hour for local-system-time quiet hours. |
| `reflection.scheduler.daily_cap` | `5` | Maximum published reflections per local-system-date. |
| `reflection.scheduler.jitter_percent` | `20` | Percent jitter applied to the interval gate. |

Quiet hours and daily caps are interpreted in the current system timezone. Internal persisted timestamps remain timezone-aware ISO timestamps.

If any schedule gate blocks a cycle, `reflect()` returns `false` before candidate generation and writes `schedule_blocked` with `status=skipped` and a short `reason` metadata value.

### Schedule State

The latest published-reflection state is stored at
`private/runtime/last_reflection.json`. It is a versioned authoritative runtime
record containing:

- `schema_version`: supported record version;
- `timestamp`: timezone-aware ISO timestamp of the latest publication;
- `daily_count`: non-negative integer publication count for `daily_date`;
- `daily_date`: valid local-system ISO date;
- optional string `title` and `body` metadata.

All scheduler and relevance-gate reads use one strict decode boundary. Missing
state means no reflection has yet been published. Malformed, partial, or
unsupported state must not be treated as missing: the scheduler fails closed,
writes a payload-safe `schedule_state_corrupt` warning, and reports
`schedule_blocked` with `reason="state_corrupt"`. The relevance gate treats the
cooldown as active when the same state is corrupt. Successful publication
updates the complete record through atomic file replacement.

The two `schedule_state_corrupt` projections use shared failure reporting.
Diagnostic persistence failure emits a terminal warning but cannot make
`should_reflect()` raise, change the scheduler's `state_corrupt` block, or make
the relevance gate treat cooldown as available.

Trace recording after reflection persistence and best-effort pending-reflection
organization are auxiliary effects. Their `trace_recording_failed` and
`organizer_failed` projections also use shared reporting. Failure of either
effect or its diagnostic cannot remove the persisted reflection, interrupt
later schedule-state/outbox/cycle completion work, or introduce a hidden
retry. Repository, schedule-state write, and outbox failures remain
authoritative.

## Optional Notify Bridge

If `reflection.auto_notify` is `true`, a brief `OutboxEntry` is created **pointing to** the reflection:

- `title`: `"New reflection: {reflection.title}"`
- `body`: `"A new reflection idea is available. View it with: nuself inbox reflection show {id}"`
- `idempotency_key`: `"notify-{reflection.id}"`

Default is `false` — no outbox entry created.

## Audit Log Events

The scheduler still emits these events into `reflection.log`:

| Event | Status | Visibility |
|---|---|---|
| `schedule_blocked` | `skipped` | `nuself dev logs --component reflection` |
| `cycle_started` | `started` | `nuself dev logs --component reflection` |
| `organizer_completed` | `completed` | `nuself dev logs --component reflection` |
| `persona_discussion` | `approved` / `rejected` | `nuself dev logs --component reflection` |
| `cycle_discussion_rejected` | `completed` | `nuself dev logs --component reflection` |
| `cycle_completed` | `completed` | `nuself dev logs --component reflection` |

## CLI Contracts

```
nuself inbox reflection list [--status pending|dismissed|archived] [--json]
nuself inbox reflection show <id_or_index> [--json]
nuself inbox reflection dismiss <id_or_index>
nuself inbox reflection archive <id_or_index>
nuself inbox reflection promote <id_or_index>
nuself inbox reflection organize
```

- `list` default: shows **all** statuses.
- Plain-text `list` output uses the visible `[index]` as the operational handle and does **not** print long `reflection-candidate-*` entry IDs. `show`, `--json`, and id-based actions still expose/accept the full entry ID.
- Plain-text `list` and `show` output follows the shared CLI record renderer: one header line with `key=value` metadata, then body text and discussion trace on subsequent indented lines. `list` treats the reflection title as the body text, keeps status/type/score/timestamps in the metadata header, puts the square-bracket index first, and preserves colored square-bracket tags such as `[reflection]` and `status=[pending]` for scanability.
- `--status`: filters to one status.
- `show` / `dismiss` / `archive` / `promote` accept either an entry ID or the 0-based visible index from `list`.
- `promote`: creates a reason thread from the selected pending reflection, writes reason and promotion trace records, and leaves the source reflection pending.
- `organize`: runs pending reflection organization once and prints how many groups and entries were merged.

REPL `:inbox reflection` lists **only pending** entries. `:inbox reflection list` lists **all** entries.
