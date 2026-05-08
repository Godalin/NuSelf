# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Temporarily plan TUI and logging polish before returning to the persona-runtime work.

The persona-runtime slice is paused at the minimal skeleton stage. Before continuing, define a focused TUI and logging plan for review on the `tui-log-plan` branch. Implementation should wait until the plan is approved.

## Immediate Context

- Existing interactive chat is a readline-backed loop with `:q`, `:memory`, and help.
- Existing daemon logging writes daemon stdout/stderr to `private/logs/daemon.log`.
- Memory curator and optimizer append action lines to `private/logs/memory.log`.
- `nuself daemon logs` currently prints the whole daemon log.
- Interactive chat should show compact colorful activity events for background work.
- Future persona discussion should fit the same activity feed as concise summaries, not final-answer text.
- The detailed review plan lives in [docs/tui-log-plan.md](tui-log-plan.md).

## Next Steps

1. Review the TUI and logging plan.
2. After approval, implement structured local logs without recording raw private chat or memory bodies.
3. Add a general `nuself logs` surface and keep daemon logs readable.
4. Render selected log events inside interactive chat as compact colored activity lines.
5. Extract interactive rendering into a small TUI module and add focused `:status` / `:logs` commands.
6. Merge back to `main`, then resume persona activation and routing.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Rich dependency-heavy terminal UI.

## Completion Criteria

- TUI and logging plan is explicit enough to review.
- No functional code changes land before plan approval.
- The plan preserves private data boundaries under ignored `private/`.
- The plan includes an interactive background activity feed and future persona discussion summaries.
- README TODOs track the temporary focus while completed work stays out of this file.
