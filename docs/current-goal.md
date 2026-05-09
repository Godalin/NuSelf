# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add outbox CLI commands and a macOS notification adapter.

The reflection scheduler is now wired into the daemon lifecycle. It checks interval, cooldown, and quiet hours before writing a reflection intent into the notification outbox. The next step is to surface that outbox to users: list entries, show details, send (retry), and dismiss from the CLI. After that, add a macOS notification adapter so reflection intents actually appear as system notifications.

## Immediate Context

- `NotificationOutbox` lives under `private/outbox/` with `add/list/get/mark_sent/mark_failed/dismiss`.
- `LogOnlyNotificationAdapter` writes to the structured log.
- `ReflectionScheduler` runs in a background thread inside `DaemonState`.
- The CLI has a single `nuself` entrypoint with subcommands for thread management, eval, and chat.

## Next Steps

1. Add `nuself outbox` subcommands: `list`, `show <id>`, `send <id>`, `dismiss <id>`.
2. Add a macOS notification adapter using `pync` or `osascript`.
3. Add outbox tests for CLI integration and macOS adapter dry-run mode.
4. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Idea candidate generation or relevance gate (scheduler first).
- Email adapter (macOS first).
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- CLI can list, show, send, and dismiss outbox entries.
- macOS adapter delivers pending entries as system notifications.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
