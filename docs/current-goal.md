# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add deep links that open an existing thread or create a new one.

Thread management now works through the CLI (`nuself thread list/create/rename/branch/archive`) and the REPL (`:threads`, `:thread`, `:rename`, `:branch`, `:archive`). The next step is to let external tools or automation open a specific thread directly without typing REPL commands. A deep link is a compact string or command-line invocation that resolves to a thread ID and optionally a seed message, so NuSelf can start a conversation at a known context.

## Immediate Context

- `ThreadStore` supports `list`, `rename`, `branch`, and `archive`.
- The daemon protocol `chat` request accepts an optional `thread_id` field.
- The REPL already prints the current thread ID in the session header.
- `nuself chat` and `nuself attach` both enter the interactive loop.
- Thread files live under `private/threads/`; archived threads live under `private/threads/archived/`.

## Next Steps

1. Design a compact deep link format (e.g., `nuself://<thread-id>?message=<seed>` or a CLI shorthand like `nuself open <thread-id> [--message <seed>]`).
2. Add a CLI `nuself open <thread-id>` command that attaches to the daemon and enters the REPL focused on that thread.
3. If the thread does not exist, create it automatically (opt-in or explicit).
4. Optionally support a seed message so the link can start a turn immediately.
5. Keep the default `nuself` entrypoint behavior unchanged.
6. Update tests and documentation together with the implementation.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- A CLI command can open a specific thread by ID in the REPL.
- Opening a non-existent thread can create it or report an error, deterministically.
- The default `nuself` entrypoint behavior is unchanged.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
