# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Audit and fix spec-code gaps across reflection, memory, and notification subsystems. The goal is to make the codebase strictly conform to the behavioral contracts in `docs/spec/`.

## Immediate Context

A cross-subsystem audit found the following spec-code gaps:

**Reflection**
- `reflect()` emits redundant `cycle_no_candidates` after `candidate_generation_skipped`/`candidate_generation_failed`, causing double events for the same condition.
- No end-to-end test covers the daemon background scheduler startup through outbox creation.

**Memory**
- `MemoryQueryService._score_entry()` excludes `score <= 0` entries before applying quality bonuses (`reviewed`, `confidence`, `importance`), so entries with no text matches but positive quality signals are wrongly dropped.
- `min_importance` is filtered after scoring; the spec requires it before scoring.
- Unknown-type candidates accepted by auto-accept conflict with `MemoryEntryRepository` quarantine: the curator forces `review_state="reviewed"`, but the repository quarantines unknown types and raises `MemoryValidationError`, which is silently swallowed.

**Notification**
- The daemon `NotificationDeliveryLoop` only uses `LogOnlyNotificationAdapter`, ignoring configured `email.enabled` and `macos_notification.enabled` settings.

## Next Steps

1. **Fix reflection double-event bug**: Remove the redundant `cycle_no_candidates` emission when generation-specific events have already been logged.
2. **Add end-to-end reflection test**: Cover daemon scheduler startup → `reflect()` → outbox entry creation.
3. **Fix memory scoring order**: Move `score <= 0` exclusion to after quality bonuses; move `min_importance` filter to the pre-scoring phase.
4. **Fix unknown-type auto-accept conflict**: Make curator skip the `reviewed` overwrite for quarantined entries, or handle the validation error explicitly.
5. **Wire notification adapters into daemon**: Construct `EmailNotificationAdapter` and `MacOSNotificationAdapter` in the daemon server when their config flags are enabled.

## Not Now

- New reflection strategies (Phase 4).
- Memory-routing changes for chat discussion outcomes.
- LLM-less reflection (Phase 3).
- Hot reload of reflection config.
- Vector and hybrid indexes (still planned but not in this slice).

## Completion Criteria

- `reflect()` emits exactly one event per outcome path (no double events).
- At least 1 test validates the end-to-end daemon reflection cycle (scheduler thread → outbox).
- `MemoryQueryService` scoring matches the spec order: filters first, then bonuses, then exclusion.
- Unknown-type candidates accepted by auto-accept do not silently fail.
- Daemon notification delivery respects configured email and macOS adapters.
- All changes update the corresponding spec in `docs/spec/`.
