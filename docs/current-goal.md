# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give Reason Output one closed audit contract across service and worker.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory reasoning-side output and daemon-side export audit producers.
2. Extend shared audit definitions for optional status and duration contracts.
3. Register the complete cross-component Reason Output audit taxonomy.
4. Migrate output planning/composition/PDF projections to the domain adapter.
5. Migrate queue/retry/reconciliation projections to the same domain registry.
6. Verify every canonical schema and pre-sink rejection of invalid producers.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No migration or rewriting of historical JSONL records.
- No change to export manifests, queue semantics, retry timing, or PDF behavior.
- No conversion of typed job wake-ups into runtime events or persisted commands.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- The inventory identified ten reasoning-side artifact events and fourteen
  daemon-side wake-up, queue, retry, and reconciliation events.
- One sealed `reason.output_audit` registry now owns all twenty-four
  `(component, event)` identities instead of splitting the capability into
  unrelated file-local string protocols.
- Shared `AuditEventDefinition` now supports exact optional-status and
  forbidden/required/optional duration policies; existing Reflection contracts
  remain validated through the same primitive.
- Planning, chunk, composition, PDF, enqueue, dequeue, retry, failure, drain,
  and reconciliation producers all route through the Reason Output adapter.
- Caught operation failures resolve their registered error contract before
  shared failure reporting; normal projections resolve before the best-effort
  sink.
- The schema review clarified that `source_end_index=None` is the intentional
  “through the final step” representation and validates it explicitly.
- Queue drain counts and ignored job names are now structured metadata rather
  than facts available only by parsing human-readable messages.
- No direct `write_observed_log_event(...)`,
  `report_observed_failure(...)`, or `run_observed_best_effort(...)` calls
  remain in the output service or export worker.
- Direct tests cover all twenty-four canonical schemas, unknown fields,
  unknown identities, optional status, duration requirements, and existing
  output/retry/recovery behavior.
- Focused audit, output, queue, subagent, and recovery suites: `104 passed`.
- Full test suite: `1852 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

The Reason Output audit-contract batch is awaiting its implementation commit.

## Next Review Batch

Review Memory curator and optimizer audit schema ownership.
