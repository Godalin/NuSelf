# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give log-projected runtime events one typed payload contract shared by
producers, event definitions, and the log sink.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit payload construction and sink-side coercion for every core event.
2. Specify one strict runtime log-projection payload.
3. Validate core event payloads before envelope creation and subscriber calls.
4. Migrate chat and daemon worker producers to the typed payload.
5. Reuse the same parser in the log sink and reject ignored fields.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep extension events free to define their own payload validator.
- Preserve runtime envelope identity and context behavior.
- Do not turn direct domain audit records into runtime events.

## Completion Evidence

- `RuntimeLogEventPayload` is the single typed schema for core event log
  projections, including exact scalar types, non-negative durations, mapping
  metadata, and rejection of unknown fields.
- Every core `RuntimeEventDefinition` validates that schema before
  `RuntimeEnvelope` creation or subscriber delivery; extension definitions
  retain an optional custom payload validator.
- Chat-turn and daemon-worker producers construct the typed payload directly,
  while `write_runtime_event()` parses the same type instead of independently
  coercing or dropping fields.
- Tests prove invalid core payloads and prebuilt envelopes reach no
  subscribers, invalid projection fields fail precisely, and manually
  supplied envelopes cannot bypass the strict log sink parser.
- Focused runtime-event, observability, daemon-worker, chat, and log tests:
  `120 passed`.
- `.venv/bin/pytest -q`: `1511 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `e1aa5db`.

## Next Review Batch

Audit runtime envelope kinds and transport-specific message wrappers.
