# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Polish the REPL with a lightweight status bar and update README with real usage examples.

Milestone 11 (Notification Adapters) is complete. The REPL now has tab completion for commands and thread IDs. The next step is to add a status bar or header refresh after every turn, and update the README with concrete usage examples for notifications and deep links.

## Immediate Context

- `_InteractiveCompleter` provides tab completion for `:commands` and thread IDs after `:thread `.
- `render_session_header` already shows daemon status and current thread.
- The CLI has `nuself notify`, `nuself open --deep-link`, and daemon background reflection.

## Next Steps

1. Add a lightweight status bar that prints after every non-command turn.
2. Polish the `nuself` default entrypoint message to be more informative.
3. Update README with real usage examples for notifications and deep links.
4. Update README.zh-CN in parallel.
5. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Idea candidate generation or relevance gate.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- REPL prints a status line after every turn (daemon status, thread, last action).
- README contains usage examples for notifications and deep links.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
