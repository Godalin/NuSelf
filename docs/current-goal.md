# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Objective

No active objective.

## Next Steps

1. Wait for the next explicitly approved goal.

## Exclusions

- Do not begin unapproved feature or refactor work.

## Last Verification

- CLI, REPL, Chat, daemon, evaluation, and cross-domain workflows consume
  authority-scoped services instead of repositories, persistence stores, or
  private workspace stores.
- `ApplicationGraph` exposes Memory, Conversation, Persona, Delivery,
  Reflection, Reason, Source, Inbox, Trace, Profile, workflow, and
  administration services; persistence construction remains internal.
- Architecture tests reject persistence types on `ApplicationGraph` and in
  process/agent adapters.
- `uv run --locked pytest -q`: 2331 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
