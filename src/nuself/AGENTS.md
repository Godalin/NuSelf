# AGENTS.md

Development constraints for `src/nuself/`.

## CLI Behavior

- Incomplete command groups must print the relevant subcommand help and exit cleanly.
- Do not let missing subcommands raise `AttributeError` or expose Python tracebacks.
- `nuself` without a subcommand is the default daemon-backed entrypoint: connect to the current daemon, or create one and then connect.
- `nuself daemon` without a subcommand must show daemon subcommand help.
- Interactive input starting with `:` is always an interactive command.
- Interactive chat exits on `:q`, `:quit`, `:exit`, or EOF.
- Interactive `:memory` and `:mem` must preview current memory entries without invoking an LLM.
- Interactive input should use `prompt_toolkit` for line editing, styled prompts, and history (via `FileHistory`), with history stored under the selected authority's ignored `runtime/interactive_history`.
- Interactive history must skip consecutive duplicate entries.
- Unknown interactive commands must print interactive help and keep the session open.
- Keep CLI behavior covered by tests when adding command groups or changing parser structure.
- Prefer clear command output over implicit behavior.

## Daemon And Runtime

- Keep persistent daemon PID, lock, and log files under the selected ignored
  authority; Unix sockets use the short owner-private runtime path defined by
  `RuntimePaths`.
- Keep the CLI-to-daemon protocol independent from LangGraph internals.
- Protocol changes should directly update client, server, tests, and docs; do not keep old wire formats during early development.
- User-facing configuration lives in the selected authority's `config.yaml`;
  the public example is `examples/.nuself/config.yaml`.
- Chat thread state belongs under the selected authority's ignored `threads/`.
- The default thread is shared working memory for the current NuSelf mind; writes must be serialized with a lock.
- Temporary chat agent behavior must stay deterministic without an API key so tests do not require network access.

## Memory Entries

- User-visible memory must stay inspectable as clear entries.
- Chat is the primary source of new memory; manual memory commands are maintenance tools, not the main user workflow.
- Memory curation must be based on discussion depth, quality, and durable signal, not a fixed number of chat turns.
- Memory entries and candidates should preserve real-world temporal metadata so changes in thought remain visible over time.
- Memory evidence should be structured and source-linked; keep legacy `source_refs` usable during migration.
- Curator and optimizer proposals should enter the candidate review queue before becoming durable memory.
- Manual `memory add` should infer the memory type through the intake agent by default; explicit type/title flags are only overrides for maintenance.
- Changes to memory entry schema must update repository code and tests together.
- Do not add new long-term memory categories as only closed `Literal` tags when the behavior is type-specific; prefer a descriptor/registry path aligned with root memory architecture docs.
- Future typed memory descriptors should own validation, summarization, merge, decay, conflict, retrieval, and reflection behavior.
- Future symbolic graph relations should be registered through relation descriptors rather than hard-coded relation enums.
- Derived indexes belong under the selected authority's `derived/` directory
  and should be rebuildable from entries.
- Chat prompts must use `MemoryQueryService` or a successor query layer instead of loading all entries indiscriminately.
- Memory query and context packing must remain independently testable without live LLM calls.
- Memory curator logic must write structured memory entries through
  repositories, log updates under the selected authority, and remain testable
  with fake LLMs.
- Memory optimizer logic must consolidate existing entries through structured agent actions and deterministic repository writes.
- Do not commit raw chat transcripts as long-term memory. Curator writes require structured agent actions; unavailable or invalid curator output should defer instead of using a local transcript fallback.

## Documentation Boundary

- Update root README files for user workflows and features users need to learn.
- Keep small implementation constraints, parser invariants, and internal behavior rules in this scoped `AGENTS.md`.
