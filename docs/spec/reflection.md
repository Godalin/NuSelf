# Reflection Spec

## Event Taxonomy

The reflection scheduler emits these events into `reflection.log`:

| Event | Status | Audience | Visibility |
|---|---|---|---|
| `cycle_started` | `started` | Internal audit | `logs --component reflection` only |
| `candidate_generation_skipped` | `skipped` | Internal audit | `logs --component reflection` only |
| `candidate_generation_failed` | `error` | Internal audit | `logs --component reflection` only |
| `cycle_no_candidates` | `completed` | Internal audit | `logs --component reflection` only |
| `cycle_filtered` | `completed` | Internal audit | `logs --component reflection` only |
| `persona_discussion` | `approved` / `rejected` | User outcome | **`reflection list`** AND logs |
| `cycle_discussion_rejected` | `completed` | Internal audit | `logs --component reflection` only |
| `cycle_completed` | `completed` | Internal audit | `logs --component reflection` only |

**`reflection list` displays only `persona_discussion` events by default.** All other events are scheduler internals and belong in `nuself logs --component reflection`.

## Pipeline Flow

```
reflect()
  ├─ cycle_started
  ├─ candidate_generation_skipped  (if no context)
  ├─ candidate_generation_failed   (if LLM errors)
  ├─ cycle_no_candidates           (if LLM returns valid but empty candidates)
  ├─ RelevanceGate.score(best)
  │   └─ cycle_filtered            (if !passes)
  ├─ persona_discussion            (if score ≥ persona_discussion_threshold)
  │   └─ cycle_discussion_rejected (if !approved)
  └─ cycle_completed               (outbox entry created)
```

## RelevanceGate Scoring

Composite = novelty×0.25 + confidence×0.20 + urgency×0.25 − interruption_cost×0.15 + cooldown_ok×0.15

- `passes` if composite ≥ threshold AND NOT (interruption_cost ≥ 0.9 AND urgency < 0.5).
- Reasons: `low_novelty`, `low_confidence`, `high_urgency`, `high_interruption_cost`, `cooldown_active`, `ok`.

## Gate Thresholds

| Threshold | Default | Purpose |
|---|---|---|
| `relevance_threshold` | `0.35` | Minimum composite to enter the pipeline at all |
| `persona_discussion_threshold` | `0.55` | Composite at or above this triggers competitive persona discussion |
| `composite_threshold` | `0.4` | Minimum average persona score to approve after discussion |
| `blocking_threshold` | `0.35` | Score below this triggers a blocking veto |
| `override_threshold` | `0.7` | Score above this counts as strong support |

Candidates below `persona_discussion_threshold` but passing the gate proceed directly to outbox without discussion.

## Outbox Creation

- `id`: `reflection-{YYYYMMDD-HHMMSS}-{microsecond:06d}`
- `idempotency_key`: `reflection-{date.isoformat()}`
- `deep_link`: `nuself://thread/{thread_id}` (defaults to `"reflections"`)
- Deduplication: `NotificationOutbox.add()` returns existing entry if idempotency key already present.

## CLI Contracts

```
nuself reflection list [--tail N] [--include-all] [--json]
nuself reflection show <event_index> [--tail N] [--include-all] [--json]
```

- `list` default: only `persona_discussion` events.
- `--include-all`: reveals all scheduler events.
- `show` indexes into the same filtered list as `list`.
