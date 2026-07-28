# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The CLI chat adapter extraction is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `cli/chat.py` owns configured daemon timeout lookup, daemon/application
  failure translation, correlated audit events, local `ChatAgent` invocation,
  one-shot presentation, and post-turn curator coordination.
- The CLI composition root retains only thin reply-rendering wrappers and
  entrypoint wiring; tests patch the modules that actually own chat and live
  activity transports.
- Direct adapter tests prove retryability classification, error correlation,
  successful reply/memory projection, and reply-before-curator ordering.
- Focused CLI/chat/turn tests: 303 passed.
- Final full tests: 1263 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Extract the remaining CLI entry/session presentation responsibilities or move
to daemon composition review.
