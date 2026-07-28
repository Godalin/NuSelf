# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Sanitize non-LLM observer and tool diagnostic failures consistently.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit daemon, log-observer, tool, and CLI exception exits.
2. Separate diagnostic projections from expected user-facing domain errors.
3. Define one safe single-exception diagnostic formatter.
4. Use it for observer records, tool outcomes, and fallback warnings.
5. Preserve original observer/tool failures and independent delivery behavior.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Daemon wire-response errors are the next independent protocol batch.
- Expected CLI domain errors remain direct user-facing messages.
- Tool and observer exceptions remain authoritative objects at their owning
  control-flow boundaries; only projections are sanitized.

## Completion Evidence

- `diagnostic_exception_message(...)` composes fail-safe exception rendering
  with shared credential sanitization for one exception.
- Process-local observer failures use the shared formatter in both
  `daemon/log_observer_failed` records and terminal warnings; later observers
  and the original audit record remain unaffected.
- Tool middleware sanitizes captured `ToolOutcome.error` text and both logger
  and failure-reporter warning paths, while re-raising the exact original tool
  exception.
- Tests cover credential removal from observer records, observer diagnostic
  fallback warnings, captured tool outcomes, and unreported tool-log warnings,
  plus broken exception renderers.
- Focused log, tool-middleware, and observability suites: `91 passed`.
- Full test suite: `1638 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `d6ea968`.

## Next Review Batch

Review and sanitize daemon wire-error serialization after non-authoritative
observer and tool projections share one diagnostic formatter.
