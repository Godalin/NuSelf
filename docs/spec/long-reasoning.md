# Long-Run Reasoning Spec

Status: TODO. This spec describes the intended subsystem. It is not implemented yet.

## Purpose

Long-run reasoning maintains durable, incremental reasoning around a small number of explicit user-approved questions.

It must not replace reflection. Reflection discovers candidate ideas; long-run reasoning sustains work on selected questions.

## Non-Goals For First Implementation

- No autonomous creation of reasoning threads from ordinary chat.
- No always-on high-frequency background thinking.
- No automatic notification for every reasoning step.
- No replacement of memory curation or reflection.

## Storage Contract

TODO: implement a file-backed repository under:

```text
private/reasoning/threads/{thread_id}.json
private/reasoning/steps/{thread_id}/{step_id}.json
```

Machine-readable records store timezone-aware ISO timestamps. Human-readable CLI output renders timestamps in the current system timezone per `cli-interaction.md`.

## ReasoningThread

TODO: define a typed domain model with these fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable thread id |
| `question` | string | User-approved long-run question |
| `status` | string | `active`, `paused`, `resolved`, or `archived` |
| `working_summary` | string | Current compact state of the reasoning |
| `hypotheses` | list[string] | Current live hypotheses |
| `open_questions` | list[string] | Subquestions still unresolved |
| `evidence_refs` | list[string] | Memory, source, thread, reflection, or step refs |
| `priority` | string | `normal` or `high` for first implementation |
| `last_advanced_at` | string \| null | Last successful advance timestamp |
| `next_review_after` | string \| null | Earliest scheduler review time |
| `created_at` | string | Creation timestamp |
| `updated_at` | string | Last state update timestamp |

## ReasoningStep

TODO: define a typed domain model with these fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable step id |
| `thread_id` | string | Parent reasoning thread |
| `kind` | string | `progress`, `no_change`, `question`, `synthesis`, `contradiction`, or `resolution` |
| `summary` | string | User-readable step summary |
| `delta` | string | What changed since the previous step |
| `new_hypotheses` | list[string] | Added hypotheses |
| `retired_hypotheses` | list[string] | Retired hypotheses |
| `new_open_questions` | list[string] | Added subquestions |
| `evidence_refs` | list[string] | Evidence used by this step |
| `confidence` | float \| null | Optional confidence estimate |
| `created_at` | string | Step timestamp |

## State Transitions

TODO: implement these transitions:

| From | Action | To |
|---|---|---|
| none | `start` | `active` |
| `active` | `pause` | `paused` |
| `paused` | `resume` | `active` |
| `active`, `paused` | `resolve` | `resolved` |
| `active`, `paused`, `resolved` | `archive` | `archived` |

Archived threads are hidden from default list output but remain addressable by id.

## Advance Contract

TODO: implement manual advance first.

```text
advance(thread)
  ├─ load thread
  ├─ reject unless status=active
  ├─ retrieve linked and relevant context
  ├─ generate a structured ReasoningStep
  ├─ update working_summary, hypotheses, open_questions, evidence_refs
  ├─ update last_advanced_at and next_review_after
  └─ persist atomically
```

Each non-`no_change` step must explain the `delta` from the prior state. A step that cannot identify meaningful movement should use `kind=no_change` and should not notify by default.

## CLI Contract

TODO: add commands:

```text
nuself reason list [--status active|paused|resolved|archived|all] [--json]
nuself reason show <id_or_index> [--by-index] [--json]
nuself reason start "<question>"
nuself reason advance <id_or_index> [--by-index]
nuself reason pause <id_or_index> [--by-index]
nuself reason resume <id_or_index> [--by-index]
nuself reason resolve <id_or_index> [--by-index]
nuself reason archive <id_or_index> [--by-index]
```

Human-readable output must use the shared record renderer style from `cli-interaction.md`.

Default list output shows active and paused threads. `--status all` includes resolved and archived threads.

## REPL Contract

TODO: add interactive commands:

```text
:reason
:reason list
:reason show <id_or_index>
:reason start <question>
:reason advance <id_or_index>
:reason pause <id_or_index>
:reason resume <id_or_index>
:reason resolve <id_or_index>
:reason archive <id_or_index>
```

REPL output must match CLI formatting as closely as possible.

## Chat Tool Contract

TODO: add chat tools after manual CLI support exists:

- `list_reasoning_threads`
- `show_reasoning_thread`
- `start_reasoning_thread`
- `advance_reasoning_thread`
- `pause_reasoning_thread`
- `resolve_reasoning_thread`
- `archive_reasoning_thread`

The chat agent may suggest a new reasoning thread, but must not create one without user confirmation.

## Reflection Bridge

TODO: add an explicit promotion command after the base repository exists:

```text
nuself reflection promote <id_or_index> [--by-index]
```

Promotion creates a reasoning thread from the reflection title/body and records the reflection id in `evidence_refs`. The original reflection should remain pending until the user dismisses, archives, or explicitly chooses a promotion policy.

## Notification Policy

TODO: integrate with notification outbox only after manual advance is stable.

Notify only when a step is user-worthy:

- `kind=progress` with a meaningful new conclusion;
- `kind=contradiction`;
- `kind=question` when user input is needed;
- high-priority thread update.

No-change steps must not notify by default.

## Logging

TODO: add a `reasoning` log component or reuse `memory`/`chat` only if a later design chooses not to add a component.

Expected events:

| Event | Status | Meaning |
|---|---|---|
| `thread_started` | `created` | New reasoning thread created |
| `thread_status_changed` | `updated` | Pause, resume, resolve, or archive |
| `advance_started` | `started` | Advance began |
| `advance_completed` | `completed` | Step persisted |
| `advance_no_change` | `skipped` | No meaningful update |
| `advance_failed` | `failed` | Advance failed safely |

## Open Decisions

TODO before implementation:

- Decide whether to add a new `reasoning` log component.
- Decide active-thread cap and default priority behavior.
- Decide whether promotion archives the source reflection automatically.
- Decide the first-pass context retrieval scope.
