# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Each client chat operation now owns one runtime correlation scope instead
of repeating thread, turn, and source fields on individual audit writes.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Daemon-backed and one-shot client adapters establish one nested
  `source="client"` scope for transport, boundary audit, and post-turn
  curation.
- Daemon completion uses one narrower nested thread override only when the
  response owns a different thread identity.
- REPL retry markers execute inside the same exact thread/turn context as each
  send attempt and no longer reconstruct correlation per event.
- Tests prove request/job/trace inheritance and complete caller-context
  restoration on connection failure and successful daemon/one-shot operations.
- A real post-turn memory audit inherits the client thread, turn, trace, and
  source; retry audit does not inherit unrelated ambient request/job identity.
- Retry count, stable turn ID, output, protocol, and result contracts are
  unchanged.
- Focused CLI chat/REPL/runtime tests: 339 passed.
- Final full tests: 1283 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing domain-state projection overrides after client scope
ownership is explicit.
