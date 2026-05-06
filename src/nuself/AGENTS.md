# AGENTS.md

Development constraints for `src/nuself/`.

## CLI Behavior

- Incomplete command groups must print the relevant subcommand help and exit cleanly.
- Do not let missing subcommands raise `AttributeError` or expose Python tracebacks.
- `nuself` without a subcommand is the default daemon-backed entrypoint: connect to the current daemon, or create one and then connect.
- `nuself daemon` without a subcommand must show daemon subcommand help.
- Interactive input starting with `:` is always an interactive command.
- Interactive chat exits on `:q`, `:quit`, `:exit`, or EOF.
- Interactive input should use readline-backed line editing/history when available, with history stored under ignored `private/runtime/interactive_history`.
- Interactive history must skip consecutive duplicate entries.
- Unknown interactive commands must print interactive help and keep the session open.
- Keep CLI behavior covered by tests when adding command groups or changing parser structure.
- Prefer clear command output over implicit behavior.

## Daemon And Runtime

- Keep daemon runtime files, sockets, pid files, and logs under ignored `private/`.
- Keep the CLI-to-daemon protocol independent from LangGraph internals.
- Protocol changes should directly update client, server, tests, and docs; do not keep old wire formats during early development.

## Memory Entries

- User-visible memory must stay inspectable as clear entries.
- Changes to memory entry schema must update repository code and tests together.
- Derived indexes belong under `private/derived/` and should be rebuildable from entries.

## Documentation Boundary

- Update root README files for user workflows and features users need to learn.
- Keep small implementation constraints, parser invariants, and internal behavior rules in this scoped `AGENTS.md`.
