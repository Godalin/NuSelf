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
| `dismissed` | User explicitly dismissed (`nuself reflection dismiss`) |
| `archived` | User explicitly archived (`nuself reflection archive`) |

## Pipeline Flow

```
reflect()
  ├─ cycle_started                 (audit log)
  ├─ candidate_generation_skipped  (if no context)
  ├─ candidate_generation_failed   (if LLM errors)
  ├─ cycle_no_candidates           (if LLM returns empty)
  ├─ LLMRelevanceGate.score(best)
  │   └─ cycle_filtered            (if !passes)
  ├─ persona_discussion            (if score ≥ persona_discussion_threshold)
  │   └─ cycle_discussion_rejected (if !approved)
  └─ ReflectionRepository.add()    ( ReflectionEntry created )
       └─ auto_notify? → NotificationOutbox.add(brief notify)
```

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

## Optional Notify Bridge

If `reflection.auto_notify` is `true`, a brief `OutboxEntry` is created **pointing to** the reflection:

- `title`: `"New reflection: {reflection.title}"`
- `body`: `"A new reflection idea is available. View it with: nuself reflection show {id}"`
- `idempotency_key`: `"notify-{reflection.id}"`

Default is `false` — no outbox entry created.

## Audit Log Events

The scheduler still emits these events into `reflection.log`:

| Event | Status | Visibility |
|---|---|---|
| `cycle_started` | `started` | `nuself logs --component reflection` |
| `persona_discussion` | `approved` / `rejected` | `nuself logs --component reflection` |
| `cycle_discussion_rejected` | `completed` | `nuself logs --component reflection` |
| `cycle_completed` | `completed` | `nuself logs --component reflection` |

## CLI Contracts

```
nuself reflection list [--status pending|dismissed|archived] [--json]
nuself reflection show <id_or_index> [--by-index] [--json]
nuself reflection dismiss <id_or_index> [--by-index]
nuself reflection archive <id_or_index> [--by-index]
```

- `list` default: shows **all** statuses.
- `--status`: filters to one status.
- `show` / `dismiss` / `archive` accept either an entry ID or a `--by-index` flag (0-based from `list`).

REPL `:reflection` lists **only pending** entries. `:reflection list` lists **all** entries.
