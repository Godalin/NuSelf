# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Audit and fix spec-code gaps across reflection, memory, and notification subsystems.

## Immediate Context

All identified spec-code gaps from the audit have been fixed:

- **Reflection**: `cycle_no_candidates` is now emitted only when the generator receives a valid but empty candidate list, not after `candidate_generation_skipped`/`candidate_generation_failed`.
- **Memory**: `min_importance` filter moved to pre-scoring phase; quarantined entries no longer silently fail during curator auto-accept.
- **Notification**: Daemon `NotificationDeliveryLoop` now constructs `EmailNotificationAdapter` and `MacOSNotificationAdapter` when their config flags are enabled.
- **Testing**: Added `test_daemon_background_reflection_scheduler_creates_outbox_entry` covering the full daemon thread → scheduler → outbox path.

## Next Steps

1. **QA**: Run integration checks and manual REPL verification to confirm the fixes work end-to-end.
2. **Docs**: Keep README, README.zh-CN, current-goal, and specs synchronized.

### Recently Done

- Fixed reflection double-event emission.
- Added end-to-end daemon reflection cycle test.
- Fixed `MemoryQueryService` `min_importance` phase mismatch.
- Fixed unknown-type auto-accept conflict.
- Wired configured notification adapters into daemon delivery loop.

## Not Now

- New reflection strategies (Phase 4).
- Memory-routing changes for chat discussion outcomes.
- LLM-less reflection (Phase 3).
- Hot reload of reflection config.
- Vector and hybrid indexes.

## Completion Criteria

- `reflect()` emits exactly one event per outcome path (no double events).
- At least 1 test validates the end-to-end daemon reflection cycle (scheduler thread → outbox).
- `MemoryQueryService` filters `min_importance` before scoring.
- Unknown-type candidates accepted by auto-accept do not silently fail.
- Daemon notification delivery respects configured email and macOS adapters.
- All changes update the corresponding spec in `docs/spec/`.
