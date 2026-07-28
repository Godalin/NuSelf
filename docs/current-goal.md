# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon post-chat memory curation use the shared observability boundary so
recoverable curation failures cannot silently masquerade as "no memory change".

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace daemon chat reply and synchronous curator failure behavior.
2. [x] Specify post-chat curation as an observable secondary effect.
3. [x] Replace the private RuntimeError catch with
   `run_observed_best_effort(errors=(RuntimeError,))`.
4. [x] Preserve successful replies and `memory_update=None` on recoverable
   curation failure.
5. [x] Preserve propagation of undeclared exceptions to the daemon request
   backstop.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing curator decisions, cursor behavior, or auto-accept policy.
- Retrying curation inside the chat request.
- Making the curator authoritative for chat reply success.
- Changing background curator worker behavior.

## Completion Evidence

- A post-chat `RuntimeError` still returns the completed chat response with no
  memory update.
- The same failure emits `memory/post_chat_curation_failed` with inherited
  request, thread, turn, and source context plus a compact error chain.
- An undeclared exception is not swallowed and reaches the daemon connection
  backstop.
- No private try/except wrapper remains around the post-chat curator call.
- Focused daemon/observability tests, full pytest, Pyright, and
  `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining private silent secondary-effect catches, beginning with CLI
persona lifecycle trace recording.
