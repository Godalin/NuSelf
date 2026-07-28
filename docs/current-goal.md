# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Improve system robustness in review-driven stages, beginning with silent
failure handling and observability at best-effort side-effect boundaries.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Classify silent exception handlers by control-flow intent and risk.
2. [x] Specify a shared observable best-effort boundary and fallback channel.
3. [x] Implement the shared boundary with focused unit tests.
4. [x] Migrate audit logging and memory/persona trace recording.
5. [x] Audit remaining broad or silent exceptions and record the next batch.
6. [x] Run full tests, type checking, and formatting checks.
7. [ ] Commit and push in reviewable stages.

## Out Of Scope

- Treating expected parse failures, missing files, or cleanup races as errors.
- Changing the success/failure semantics of primary domain operations.
- Adding an autonomous agent subsystem without a bounded task that benefits
  from agent reasoning.

## Completion Evidence

- Best-effort failures produce a structured warning/error when possible and a
  fallback diagnostic when the structured sink itself fails.
- Migrated primary operations remain successful when their trace/audit side
  effect fails.
- Focused tests cover the shared boundary and each migrated caller.
- The remaining silent-exception audit has an explicit next action.
- Full pytest, Pyright, and `git diff --check` pass.

## Next Review Batch

After this slice, make corrupt-record handling observable across repositories
that currently skip malformed memory, source, profile, persona, reason,
reflection, notification, or trace records. Then harden daemon export-manifest
failure reporting. Expected missing-file and cleanup races remain excluded.
