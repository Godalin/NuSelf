# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prevent malformed or partially written memory-curator cursors from silently
replaying already processed conversation history.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Classify remaining domain/storage cleanup suppression.
2. [x] Specify authoritative curator cursor validation and failure behavior.
3. [x] Introduce a typed cursor record with thread/count validation.
4. [x] Persist curator cursors atomically.
5. [x] Report corrupt cursors and stop the run instead of resetting to zero.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing curator LLM policy, quality gates, or auto-accept behavior.
- Automatically repairing, deleting, or quarantining a corrupt cursor.
- Changing thread compression or absolute message-index semantics.
- Refactoring unrelated not-found and temporary-file cleanup handlers.

## Completion Evidence

- A missing cursor still starts at zero.
- Valid cursors require the requested thread identity and a non-negative integer
  absolute message count.
- Invalid JSON, shape, identity, or count emits a payload-safe corruption event
  and aborts the curator run before LLM or candidate work.
- Cursor writes use atomic replacement and leave no partial target.
- Focused cursor tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit memory auto-accept failure visibility and legacy persona name-index
recovery.
