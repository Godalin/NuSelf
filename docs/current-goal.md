# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add deep links to outbox entries so notifications can open a specific thread.

All three notification adapters (log-only, macOS, email) are now in place. The next step is to give outbox entries a `deep_link` field that resolves to a thread ID, and update the CLI so that clicking or following a deep link opens the corresponding conversation.

## Immediate Context

- `OutboxEntry` already has an optional `deep_link` field.
- `nuself open <thread-id>` opens a thread in interactive mode.
- The daemon has access to `chat_agent` and `ThreadStore`.

## Next Steps

1. Define deep link format (e.g., `nuself://thread/<thread-id>`).
2. Update `ReflectionScheduler` to include a deep link pointing to a reflection thread.
3. Add `nuself open --deep-link <url>` CLI command that parses and opens the target thread.
4. Add tests for deep link parsing and resolution.
5. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Idea candidate generation or relevance gate (scheduler first).
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Outbox entries can carry deep links to threads.
- CLI can open a thread from a deep link.
- Deep links are tested for parsing and resolution.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
