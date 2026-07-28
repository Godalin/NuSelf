# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Keep uncertain auxiliary chat-log persistence from changing completed replies,
application failures, or transport retry decisions.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit chat adapters and REPL retry markers around log writes.
2. Specify that only typed transport failures control chat retries.
3. Move daemon, one-shot, curator, and retry audits behind observability.
4. Preserve completed replies and application outcomes when audit fails.
5. Verify retry execution and success projection under uncertain log failure.
6. Run full quality gates, commit, and push.

## Out Of Scope

- The original uncertain log record is never retried automatically.
- `DaemonConnectionError.retryable` remains the sole chat transport retry
  decision.
- Diagnostic logging may emit a distinct failure record through the shared
  best-effort boundary.

## Completion Evidence

- Daemon success/failure, one-shot success/failure, curator status, and
  `turn_retry` records now use the shared observed best-effort boundary.
- An uncertain daemon completion audit preserves the typed successful reply;
  an uncertain one-shot completion audit preserves the reply and still runs
  post-turn curation.
- An uncertain `turn_retry` audit produces a separate diagnostic without
  suppressing the second transport attempt or changing its stable `turn_id`.
- No caller retries the original uncertain log record; diagnostics carry its
  failure separately under `audit_projection_failed`.
- Focused CLI, chat, REPL, activity, and observability tests: `335 passed`.
- `.venv/bin/pytest -q`: `1558 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `c97695c`.

## Next Review Batch

Audit remaining direct log projections outside chat adapters.
