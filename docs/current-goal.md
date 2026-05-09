# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 11 (Notification Adapters) is complete. Shift focus to REPL polish and first usable interface improvements.

All notification adapters (log-only, macOS, email) and deep links are now in place. The outbox CLI supports list, show, send, and dismiss. Reflection scheduler runs in the daemon background and writes reflection intents with deep links to the `reflections` thread.

## Immediate Context

- `nuself notify` subcommands: `list`, `show`, `send`, `dismiss`.
- `nuself open --deep-link <url>` opens a thread from a notification.
- `MacOSNotificationAdapter` and `EmailNotificationAdapter` both support dry-run mode.
- The REPL already supports `:q`, `:threads`, `:thread`, `:rename`, `:branch`, `:archive`, `:memory`, `:logs`, `:status`.

## Next Steps

1. Add REPL autocomplete for commands and thread IDs.
2. Add a lightweight status bar or header showing daemon status and current thread.
3. Polish the `nuself` default entrypoint message to be more informative.
4. Update README with real usage examples for notifications and deep links.
5. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Idea candidate generation or relevance gate.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- REPL has autocomplete for commands.
- Status bar or header shows daemon and thread context.
- README contains usage examples for notifications and deep links.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
