# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 13: First Usable Interface — REPL polish and basic profile integration.

The REPL now has tab completion, a session header after every turn, `:whoami` for profile preview, and a compact `nuself status` command. The default entrypoint message is more informative. README usage examples for notifications and deep links are in place.

## Immediate Context

- `_InteractiveCompleter` provides tab completion for `:commands` and thread IDs.
- `render_session_header` prints after every non-command turn.
- `:whoami` shows up to 6 core profile items.
- `nuself status` shows daemon state, thread count, and pending notifications.
- Default entrypoint shows "Tip: type :help for commands, :q to quit, or start chatting."

## Next Steps

1. Add REPL command autocomplete hints (show available completions on partial match).
2. Consider adding a `:notify` REPL command to list pending notifications inline.
3. Update README TODOs together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Idea candidate generation or relevance gate.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- REPL autocomplete hints display on partial command match.
- `:notify` lists pending outbox entries inline.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
