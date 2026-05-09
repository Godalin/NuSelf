# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 13 is complete. Next: generate idea candidates from recent threads, memory, and sources.

The evaluation harness now includes proactive-notification fixtures for reflection scheduler triggers, deep link parsing, and outbox delivery lifecycle. All Milestone 11 and 13 deliverables are done.

## Immediate Context

- `ReflectionScheduler` writes generic reflection intents to the outbox.
- `NotificationOutbox` supports idempotency, status transitions, and CLI/REPL commands.
- `DeepLink` connects notifications to threads.
- The evaluation harness has 3 notification fixture files under `tests/fixtures/notifications/`.

## Next Steps

1. Implement `IdeaCandidateGenerator` that reads recent thread turns and surfaces questions or observations.
2. Wire candidate generation into `ReflectionScheduler` so reflection intents carry meaningful content.
3. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Relevance gate with full novelty/confidence/urgency scoring.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Reflection scheduler generates context-aware reflection content instead of a generic message.
- Candidate generation is tested with fixture-based scenarios.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
