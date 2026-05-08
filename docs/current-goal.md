# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Finish the TUI and logging polish branch, then merge back to `main` and return to persona-runtime work.

The TUI/logging slice now has structured local logs, a general `nuself logs` viewer, REPL activity lines, `:status` / `:logs`, read-only `:mem ...` inspect commands, and readable memory renderers. The remaining work is validation, progress commit, merge back to `main`, and restoring the persona activation/routing focus.

## Immediate Context

- Interactive chat is still readline-backed and REPL-shaped.
- Structured local logs are written under `private/logs/`.
- `nuself logs` and `nuself daemon logs` render structured log tails.
- Interactive chat prints compact activity events after turns.
- Interactive chat supports `:status`, `:logs`, and read-only `:mem ...` inspect commands.
- Memory inspect output has compact rows and grouped detail blocks.
- Future persona discussion should fit the same activity feed as concise summaries, not final-answer text.
- The detailed review plan lives in [docs/tui-log-plan.md](tui-log-plan.md).

## Next Steps

1. Run focused and full validation.
2. Commit README/current-goal progress updates.
3. Merge `tui-log-plan` back to `main`.
4. Restore `docs/current-goal.md` to the persona activation/routing focus.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Focused CLI/daemon tests pass.
- Full project tests pass.
- `uvx pyright` passes.
- README TODOs track completed REPL/log/memory inspect progress.
- Merge back to `main` is complete.
