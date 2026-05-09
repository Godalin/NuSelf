# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 10–13 are functionally complete. Recent follow-up work added thread lifecycle commands (delete, unarchive, archived) and fixed all pre-existing pyright strict-mode errors in tests.

## Immediate Context

- `ReflectionScheduler`: interval, cooldown, quiet hours, daemon background thread.
- `IdeaCandidateGenerator`: reads latest user message from threads for context-aware prompts.
- `RelevanceGate`: drops duplicate or empty candidates.
- Notification adapters: log-only, macOS (osascript), email (SMTP).
- Deep links: `nuself://thread/<id>` with CLI resolution.
- Evaluation harness: chat fixtures + notification fixtures.
- Thread lifecycle: CLI `delete`/`unarchive`/`archived`, REPL `:archive`/`:unarchive`/`:archived`/`:delete`.
- All tests pass under pyright strict mode (0 errors).

## Next Steps

1. ~~Review whether any CLI subcommands or REPL commands still have gaps.~~ Done: filled test coverage for memory list/show/add/edit/delete/search, source list/show/delete/chunks/search/extract, profile list/show/search/delete/reindex, candidate list/show/accept/reject/edit/merge, graph nodes/edges/search/path/closure, stats, reindex, daemon list/logs.
2. ~~Fix pre-existing pyright strict-mode errors.~~ Done: 0 errors across src/ and tests/.
3. Consider whether the `source` workflow deserves a top-level CLI command.
4. Update README TODOs together with any follow-up work.

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
