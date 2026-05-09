# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 10: Proactive Agent and Outbox — let NuSelf surface ideas without becoming noisy.

## Immediate Context

- `reflection.py` has a skeleton scheduler, gate, and generator, but they are too primitive for real use.
- `notification/` has a working outbox, adapters, and deep links, but the daemon calls adapters directly from the scheduler.
- `daemon/server.py` runs background reflection and memory curator threads.
- Persona subgraphs exist in `agent/persona.py` and are used in conversation turns.
- Design doc at `docs/proactive-agent-design.md` describes randomized low-frequency reflection, structured candidates, competitive persona discussion, and decoupled outbox delivery.

## Next Steps

1. Add `IdeaCandidate` and `RelevanceScore` typed models with wire serialization tests.
2. Enhance `IdeaCandidateGenerator` to scan threads, memory, and sources; produce structured candidates via LLM.
3. Enhance `RelevanceGate` with multi-dimensional scoring (novelty, confidence, urgency, interruption cost, cooldown).
4. Enhance `ReflectionScheduler` with jitter, daily cap, and event triggers.
5. Add competitive persona discussion for high-value candidates (random persona selection, scoring, veto, synthesizer arbitration).
6. Add `NotificationDeliveryLoop` that polls pending outbox entries and dispatches through adapters.
7. Decouple daemon: scheduler writes to outbox only; start delivery thread.
8. Enhance `DeepLink` with `new_thread` action and wire into CLI/REPL.

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
