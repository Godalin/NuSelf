# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make audit envelopes self-contained and project audit/event envelopes through
one typed log boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit direct log writes and runtime-event log projection.
2. Specify complete audit content inside the envelope payload.
3. Add explicit audit-envelope construction and write boundaries.
4. Share one envelope-to-`LogEvent` projector across audit and event kinds.
5. Verify audit envelope round trips retain every projected field.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Preserve `write_log_event()` as the domain-facing convenience API.
- Keep direct audit names governed by domain specs rather than the runtime
  event-definition registry.
- Preserve append, observer, retention, and legacy-read behavior.

## Completion Evidence

- `create_audit_envelope()` puts the complete `RuntimeLogEventPayload` and
  resolved runtime context into one immutable `kind="audit"` envelope.
- `write_audit_envelope()` and `write_runtime_event()` delegate to one strict
  envelope-to-`LogEvent` projector with explicit kind ownership.
- `write_log_event()` is now only the domain-facing composition of audit
  envelope creation and persistence; it no longer constructs a parallel
  `LogEvent`.
- Tests prove a serialized/decoded audit envelope preserves every identity,
  context, payload, and metadata field, while wrong-kind and empty audit
  envelopes are rejected before append.
- Focused log, runtime-event, observability, and CLI tests: `352 passed`.
- `.venv/bin/pytest -q`: `1521 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `0c46c4e`.

## Next Review Batch

Audit LogEvent construction and decode validation for remaining silent coercion.
