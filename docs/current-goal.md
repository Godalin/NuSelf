# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Recover the active structured log cleanly when a single-record append fails
after writing only part of its JSONL bytes.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit text-stream write, flush, and failure behavior.
2. Specify record-boundary rollback for failed appends.
3. Add a complete-write loop under the existing process lock.
4. Preserve the primary append error if rollback also fails.
5. Verify recovery from an injected partial write.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Successful appends remain process-visible rather than `fsync`-durable.
- Rollback is limited to bytes written by the failing append while holding the
  stable inter-process lock.
- Failed events are not delivered to observers.

## Completion Evidence

- Active-file appends capture the record boundary under the existing stable
  lock and use an unbuffered complete-write loop.
- Short writes are retried until the full JSONL record is process-visible.
- An injected partial write rolls back to the prior boundary, propagates the
  original `OSError`, skips observer delivery, and permits a clean later write.
- Rollback failure emits one non-raising diagnostic containing only component
  and exception type; private paths and exception messages remain excluded.
- Focused log infrastructure tests: `51 passed`.
- `.venv/bin/pytest -q`: `1547 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `4089880`.

## Next Review Batch

Audit sidecar lock lifecycle and in-process lock registry growth.
