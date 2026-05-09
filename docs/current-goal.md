# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add a notification outbox with log-only adapter.

Milestone 8 is complete. The next natural step is Milestone 10 (Proactive Agent And Outbox). The outbox is the foundational piece: it gives all later proactive features a controlled channel to surface ideas without becoming a noisy chatbot. Graph nodes and reflection schedulers will write notification intents into the outbox; adapters (starting with log-only) will deliver them. This keeps tests safe and keeps the system runnable before any real external notifications are wired.

## Immediate Context

- `private/logs/` already exists for structured log files.
- The CLI has deep command trees for `daemon`, `chat`, `memory`, `thread`, `logs`, and `eval`.
- `ThreadStore` and `MemoryEntryRepository` provide patterns for file-backed persistence with atomic writes.
- The daemon runs a background memory curator thread; later it will also run a reflection scheduler.
- `write_log_event` is the existing structured logging boundary.

## Next Steps

1. Design `OutboxEntry` and `NotificationOutbox` repository under `private/outbox/`.
2. Add `NotificationAdapter` protocol with `send(entry) -> bool`.
3. Implement `LogOnlyNotificationAdapter` that writes to `private/logs/notifications.log`.
4. Add CLI commands: `nuself notify list`, `show`, `send`, `dismiss`.
5. Ensure the outbox supports idempotency keys so duplicate intents are deduplicated.
6. Add tests for outbox CRUD, adapter delivery, and idempotency.
7. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection scheduler, idea candidates, or relevance gate (outbox first).
- macOS or email notification adapters (outbox first).
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Notification intents can be written to the outbox.
- Log-only adapter delivers intents to a structured log file.
- CLI can list, show, send, and dismiss outbox entries.
- Idempotency keys prevent duplicate entries.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
