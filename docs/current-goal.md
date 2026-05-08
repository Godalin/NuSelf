# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add named thread creation, branching, renaming, and archival to the conversation runtime.

The conversation runtime already persists threads under `private/threads/` with compression, locking, and a typed `ThreadState`. The CLI supports `nuself chat` and `nuself attach` against a default thread. The next step is to let users create named threads, rename existing ones, branch from a thread at a specific point, and archive old threads without deleting them. These operations must stay behind the existing `ThreadStore` boundary, preserve the current `ChatAgent.respond` interface, and keep the daemon protocol unchanged.

## Immediate Context

- `ThreadStore` owns file-backed persistence under `private/threads/` with advisory locking.
- `ThreadState` tracks `thread_id`, `summary`, `messages`, `message_start_index`, and `next_message_index`.
- `ChatAgent.respond` takes an optional `thread_id` parameter defaulting to `"default"`.
- The daemon protocol and CLI already pass thread identifiers through the stack.
- Thread files use `.json` extension; thread locks use `.lock`.
- Compression drops old messages and updates `message_start_index`.

## Next Steps

1. Add `ThreadStore.list()`, `ThreadStore.rename()`, `ThreadStore.branch()`, and `ThreadStore.archive()` methods.
2. Add corresponding CLI commands (`nuself thread list`, `nuself thread rename`, `nuself thread branch`, `nuself thread archive`) or REPL commands (`:threads`, `:rename`, `:branch`, `:archive`).
3. Keep branching semantics explicit: copy messages and summary up to a chosen index, assign a new thread ID, and start a new file.
4. Archival should move the thread file to an `archived/` subdirectory or add an `archived` flag in metadata.
5. Ensure the default thread behavior remains unchanged when no thread management commands are used.
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

- Users can list existing threads.
- Users can create a new named thread.
- Users can rename an existing thread.
- Users can branch a thread from a specific message index.
- Users can archive a thread without losing data.
- Default `nuself chat` behavior is unchanged.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
