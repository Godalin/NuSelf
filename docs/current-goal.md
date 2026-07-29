# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Serialize curator plan/candidate/cursor mutation per thread across processes.
Concurrent curation must not duplicate model work, and CLI discard must never
race an active daemon curation run.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inspect existing ThreadStore, daemon, log, and reason-export locks.
2. Define a separate stable per-thread curator advisory lock.
3. Hold it across plan, candidate, auto-accept, and cursor mutation.
4. Make curator contention a safe deferred result and discard contention an
   immediate CLI error.
5. Prove same-thread exclusion, different-thread independence, and no deletion
   under contention.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm development-branch CI.

## Out Of Scope

- No plan, candidate, cursor, or MemoryEntry wire-schema change.
- No reuse of the chat ThreadStore lock across a model call.
- No blocking wait on contention.
- No global curator lock that serializes unrelated threads.
- No lock-file deletion during ordinary release.

## Completion Evidence

- Curator runtime and CLI discard currently share plan decoding/path rules but
  do not coordinate mutations.
- A daemon run can save or resume a plan while CLI simultaneously unlinks it;
  two daemon triggers can also model and stage the same source concurrently.
- ThreadStore's lock cannot guard the full curator run without blocking chat
  persistence for the duration of the model call.
- Chosen design: a separate non-blocking advisory lock per curator thread.
- `MemoryCuratorPlanStore.exclusive()` now owns the stable lock path and both
  daemon curation and CLI discard use it as the single mutation boundary.
- Curator contention emits the sealed `memory/curator_contended` deferred event
  and returns zero changes before loading the thread or invoking the model.
- CLI contention returns non-zero and retains the exact plan. Inspection
  remains lock-free because plan writes are atomic snapshots.
- `source_trace_id` now flows through the call instead of shared curator
  instance state, preserving different-thread concurrency.
- A spawned-process test proves same-thread exclusion; focused tests also prove
  different-thread independence, stable lock files, exception release, dual
  failure provenance, and no cursor/candidate mutation under contention.
- Focused curator/CLI/audit/lock tests: 385 passed.
- Full suite: 2191 passed.
- Pyright: 0 errors, 0 warnings.
- Exception-presentation guard and `git diff --check` passed.

## Publication

Implementation and local validation complete. Functional commit and
intermediate publication are pending; CI will be tracked only after the final
push of the broader infrastructure review.

## Next Review Batch

After this boundary is complete, run a requirement-by-requirement completion
audit over the shared handler/log/event/error infrastructure review.
