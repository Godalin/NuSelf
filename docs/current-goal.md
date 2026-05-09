# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add an email notification adapter using ignored private configuration.

The outbox CLI commands (`nuself notify list/show/send/dismiss`) and the macOS notification adapter are now in place. The next step is to add an email adapter that reads SMTP credentials from an ignored private configuration file and delivers pending outbox entries via email.

## Immediate Context

- `NotificationOutbox` lives under `private/outbox/` with full CRUD and status lifecycle.
- `LogOnlyNotificationAdapter` writes to the structured log.
- `MacOSNotificationAdapter` delivers via `osascript` with dry-run support.
- The CLI `nuself notify send <id>` uses `LogOnlyNotificationAdapter` by default.
- Private configuration lives in `private/` (ignored by Git).

## Next Steps

1. Define email configuration schema (SMTP host, port, user, password, from/to addresses).
2. Load credentials from an ignored private config file (e.g., `private/email.toml`).
3. Implement `EmailNotificationAdapter` with SMTP delivery and dry-run support.
4. Add adapter tests with a fake SMTP server or mock.
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

- Email adapter reads SMTP config from ignored private file.
- Email adapter delivers pending outbox entries via SMTP.
- Dry-run mode supported for testing without real email delivery.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
