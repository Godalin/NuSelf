# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Harden internal message transport so event, job, and audit envelopes cross
subsystem boundaries through typed, definition-validated adapters.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every `RuntimeEnvelope` construction, decode, publication, queue,
   and persistence boundary.
2. Compare the event definition registry, job wrapper, and audit/log adapter
   for duplicated validation and untyped escape hatches.
3. Define the target transport contract in the governing runtime/log specs
   before implementation.
4. Add closed job definitions and typed event/job/audit decoding where raw
   envelope kind checks currently leak across owners.
5. Route producers and consumers through shared typed adapters without
   weakening immutable payload or runtime-context guarantees.
6. Remove obsolete constructors, aliases, and duplicate validation paths
   rather than preserving compatibility shims.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No change to domain payload semantics, daemon delivery ordering, durable job
  state, or audit JSONL wire format without an explicit spec decision.
- No process-external message broker in this batch.
- Reason audit ownership was completed in `b2d2b07`.
- Generic corrupt-record and audit-projection diagnostics remain shared.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- Initial inspection confirms `RuntimeEnvelope` is the shared immutable wire
  shape, while events validate through a definition registry, jobs use a typed
  wrapper without closed name definitions, and audits adapt the envelope
  separately in `logs.py`.
- Direct envelope construction is already confined to the event publisher,
  `JobMessage`, and log/audit adapter; no domain bypass requires another
  wrapper layer.
- `docs/spec/runtime-infrastructure.md` and
  `docs/spec/reason-output.md` now define the missing sealed job-definition
  boundary and reject unknown jobs before queue mutation.
- `JobDefinitionRegistry` now owns dotted job names, allowed producers, exact
  data validators, duplicate rejection, sealing, and typed-message validation.
- Reason owns the `reason.output.export` contract for `reasoning`,
  `daemon_retry`, and `daemon_reconciliation`; enqueue validates before the
  only `SimpleQueue.put(...)` call.
- The worker's unknown-name compatibility branch and
  `export_job_type_ignored` audit were removed.
- Focused runtime-job/Reason-export suite: `106 passed`.
- Full test suite: `2005 passed`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- `git diff --check` passed.

## Publication

Pending this batch's implementation commit and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after the transport
contract is verified and published.
