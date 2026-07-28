# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Use one immutable `ToolOutcome` object for tool capture and log projection
through the shared agent middleware.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit middleware callback, capture, and failure reporter ownership.
2. Confirm one reporter produces one diagnostic without recursive warnings.
3. Replace the parallel callback argument protocol with `ToolOutcome`.
4. Rename chat composition contracts around outcome projection.
5. Verify success/error identity across logging and capture.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Middleware remains the only layer that catches callback failure.
- The composition-root reporter remains responsible for structured degradation.
- Tool execution, cache, and retry-suppression semantics remain unchanged.

## Completion Evidence

- `ToolCaptureMiddleware` constructs one immutable `ToolOutcome` and passes the
  exact same object to both projection callback and capture sink.
- Chat composition and `ConversationToolRuntime` now accept
  `log_tool_outcome`/`log_outcome` rather than the parallel variadic protocol.
- Reason outcome projection consumes the captured `ToolOutcome` directly while
  retaining its middleware-independent best-effort boundary.
- Non-JSON arguments still execute; outcome construction failure reaches the
  single reporter and preserves both successful results and tool exceptions.
- Focused middleware, chat response/runtime, reason advancer, and agent tests:
  `112 passed`.
- `.venv/bin/pytest -q`: `1564 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `99759ea`.

## Next Review Batch

Audit remaining direct auxiliary projections and domain-owned exceptions.
