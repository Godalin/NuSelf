# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add a low-frequency daemon reflection scheduler with cooldowns and quiet hours.

The notification outbox is now in place with idempotency keys and a log-only adapter. The next step is to give the daemon a reason to write into that outbox. A reflection scheduler decides when the daemon should run a self-reflection cycle: it checks time-based triggers, cooldowns since the last reflection, and quiet hours, then optionally generates a reflection intent.

## Immediate Context

- `DaemonState` in `nuself.daemon.server` already runs a background memory curator thread.
- The notification outbox lives under `private/outbox/` with `NotificationOutbox` repository.
- `LogOnlyNotificationAdapter` writes to `private/logs/outbox.log`.
- `write_log_event` is the existing structured logging boundary.
- The daemon has access to `chat_agent`, `memory_curator`, and the thread store.

## Next Steps

1. Design `ReflectionScheduler` with configurable interval, cooldown, and quiet hours.
2. Store last reflection timestamp under `private/runtime/last_reflection.json`.
3. Quiet hours default to 22:00–07:00 local time; configurable via env.
4. Cooldown prevents multiple reflections within a short window even if the interval fires.
5. When conditions pass, the scheduler writes a reflection intent to the notification outbox.
6. Wire the scheduler into `DaemonState` as a background thread (separate from memory curator).
7. Add tests for trigger logic, cooldown enforcement, and quiet hours.
8. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Idea candidate generation or relevance gate (scheduler first).
- macOS or email notification adapters (log-only first).
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Daemon runs a reflection scheduler in the background.
- Scheduler respects interval, cooldown, and quiet hours.
- Reflection intents are written to the notification outbox when triggered.
- Log-only adapter delivers them to the structured log.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
