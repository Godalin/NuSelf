# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Expected reason-domain failures now use one authoritative exception
hierarchy, and CLI/REPL no longer relabel arbitrary `RuntimeError` values.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `nuself.reason.errors` owns `ReasonError`, `ReasonNotFound`,
  `ReasonPromptError`, `ReasonAdvanceError`, and `ReasonTransitionError`.
- Repository, service, prompt, advancer, agent tools, output, CLI, REPL, and
  tests migrated directly; no repository forwarding alias or legacy
  `ValueError` base remains.
- Expected reason failures retain concise CLI/REPL results through
  `ReasonError`.
- Unexpected prompt-generator, LLM-adapter, and handler `RuntimeError` or
  `TypeError` objects propagate unchanged.
- Provider `RuntimeError` from the LLM abstraction becomes
  `ReasonPromptError` with the provider failure retained as explicit cause.
- Focused reason/error-boundary tests: 90 passed.
- Final full tests: 1387 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit previous refactors for forwarding modules, compatibility aliases,
parallel protocols, and legacy entrypoints that can be removed through direct
repository-wide migration.
