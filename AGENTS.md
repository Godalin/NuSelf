# AGENTS.md

An AI mirror for deep personal discussion — someone with similar life experience but broader perspective.

## Code Standard

- Standard Python project managed by `uv`.
- Type-check with `uvx pyright`.
- Sub-components must be individually tested.
- User-facing changes must update both `README.md` and `README.zh-CN.md`.
- Track progress in `README.md` TODOs; short-term focus in `docs/current-goal.md`.

## Development Style

- Early development: prefer direct, clean implementation over compatibility shims.
- Interface changes must update all callers, tests, examples, and docs in the same commit.
- Do not preserve obsolete CLI commands, protocols, schemas, or APIs unless a document explicitly requires them.
- Refactors are welcome when they clarify architecture; always pair them with doc and test updates.
- Separate commits: **(1)** functional code + tests, **(2)** `docs/current-goal.md`, README TODOs, and guidance updates.
- Check `docs/current-goal.md` before non-trivial work. Mention conflicts before proceeding.
- Keep `docs/current-goal.md` concise (active focus, next steps, out-of-scope, completion criteria). Move completed history to README TODOs.
- Keep scoped implementation constraints in local `AGENTS.md` files, not the root README.

## Project Design

Keep these current when system shape or boundaries change:

- Short-term goal: [`docs/current-goal.md`](docs/current-goal.md)
- Progress TODOs: [`README.md`](README.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Plans: [`docs/development-plan.md`](docs/development-plan.md), [`docs/agent-framework.md`](docs/agent-framework.md), [`docs/interaction-layer.md`](docs/interaction-layer.md), [`docs/memory-management.md`](docs/memory-management.md)
- Sample memory: [`examples/private/`](examples/private/)

## Memory Architecture Direction

- Prefer open typed memory (`MemoryObject + MemoryTypeDescriptor`) over closed enums.
- Descriptors own validation, summarization, merge, decay, conflict, retrieval, and reflection rules.
- Symbolic memory evolves as a derived open graph with `RelationDescriptor` rules.
- File-backed private memory is authoritative; all indexes are derived and rebuildable.

## Private Memory

- Real personal memory lives in the root `private/` directory.
- `private/` is ignored by Git and must not be committed.
- Code loads from `private/` by default; tests and demos use `examples/private/`.
