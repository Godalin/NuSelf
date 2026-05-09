# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 10 implementation is complete. Next: stabilization, README sync, and any follow-up polish before moving to Milestone 11.

## Immediate Context

- `IdeaCandidate` and `RelevanceScore` models are typed, serializable, and tested.
- `IdeaCandidateGenerator` scans threads, memory, and sources; produces structured candidates.
- `RelevanceGate` scores across novelty, confidence, urgency, interruption cost, and cooldown.
- `ReflectionScheduler` supports randomized intervals, daily caps, quiet hours, cooldowns, and event triggers.
- `ProactivePersonaDiscussion` randomly selects personas, scores candidates competitively, allows blocking vetoes, and requires synthesizer arbitration.
- `NotificationDeliveryLoop` polls pending outbox entries and dispatches through configured adapters.
- Daemon `reflect()` writes to outbox only; adapters are called only from the delivery loop.
- `DeepLink` supports both `open_thread` and `new_thread` actions; CLI `open --deep-link` handles both.
- All new code passes `uv run pytest` (514 tests) and `uvx pyright` (0 errors).

## Next Steps

1. ~~Add `IdeaCandidate` and `RelevanceScore` typed models with wire serialization tests.~~ Done.
2. ~~Enhance `IdeaCandidateGenerator` to scan threads, memory, and sources.~~ Done.
3. ~~Enhance `RelevanceGate` with multi-dimensional scoring.~~ Done.
4. ~~Enhance `ReflectionScheduler` with jitter, daily cap, and event triggers.~~ Done.
5. ~~Add competitive persona discussion for high-value candidates.~~ Done.
6. ~~Add `NotificationDeliveryLoop` that polls pending outbox entries and dispatches through adapters.~~ Done.
7. ~~Decouple daemon: scheduler writes to outbox only; start delivery thread.~~ Done.
8. ~~Enhance `DeepLink` with `new_thread` action and wire into CLI/REPL.~~ Done.
9. Update `README.md` and `README.zh-CN.md` TODOs for proactive agent features. (in progress)
10. Commit feature code and docs separately.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- `IdeaCandidate` and `RelevanceScore` are typed, serializable, and tested.
- `IdeaCandidateGenerator` scans threads, memory, and sources; produces structured candidates.
- `RelevanceGate` scores across novelty, confidence, urgency, interruption cost, and cooldown.
- `ReflectionScheduler` supports randomized intervals, daily caps, quiet hours, cooldowns, and event triggers.
- Competitive persona discussion randomly selects personas, scores candidates competitively, allows blocking vetoes, and requires synthesizer arbitration.
- `NotificationDeliveryLoop` polls pending outbox entries and dispatches through configured adapters.
- Daemon `reflect()` writes to outbox only; adapters are called only from the delivery loop.
- `DeepLink` supports both `open_thread` and `new_thread` actions.
- All new code passes `uv run pytest` and `uvx pyright`.
- `README.md` and `README.zh-CN.md` TODOs updated for proactive agent features.
