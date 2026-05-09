# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 10–13 are functionally complete. The system now has proactive reflection with scheduling, candidate generation, relevance gating, multi-channel notifications, deep links, and evaluation fixtures.

## Immediate Context

- `ReflectionScheduler`: interval, cooldown, quiet hours, daemon background thread.
- `IdeaCandidateGenerator`: reads latest user message from threads for context-aware prompts.
- `RelevanceGate`: drops duplicate or empty candidates.
- Notification adapters: log-only, macOS (osascript), email (SMTP).
- Deep links: `nuself://thread/<id>` with CLI resolution.
- Evaluation harness: chat fixtures + notification fixtures.

## Next Steps

1. Review recent commits for any missed documentation or test gaps.
2. Consider whether any remaining README TODOs should be re-prioritized.
3. Update README TODOs together with any follow-up work.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- All Milestone 10–13 deliverables are implemented and tested.
- README TODOs reflect current progress.
- All operations are type-checked and tested.
