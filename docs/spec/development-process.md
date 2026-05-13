# Development Process Spec

## Code Standard

- Standard Python project managed by `uv`.
- Type-check with `uvx pyright`.
- Sub-components must be individually tested.
- User-facing changes must update both `README.md` and `README.zh-CN.md`.
- Track progress in `README.md` TODOs; short-term focus in `docs/current-goal.md`.

## Commit Policy

- Separate commits:
  1. **Functional commit**: code + tests.
  2. **Progress commit**: `docs/current-goal.md`, README TODOs, and spec updates.
- Before non-trivial work, check `docs/current-goal.md`. Mention conflicts before proceeding.

## Development Style

- **Design before implement**: For any non-trivial feature or behavioral change, write or update the relevant spec document **before** writing implementation code.
- **Spec is authoritative**: A feature change is not complete until the spec that governs it is updated in the same change.
- **No spec drift**: If code behavior diverges from its spec, either fix the code or update the spec. The spec must always describe the actual system.
- Early development: prefer direct, clean implementation over compatibility shims.
- Interface changes must update all callers, tests, examples, and docs in the same commit.
- Do not preserve obsolete CLI commands, protocols, schemas, or APIs unless a document explicitly requires them.
- Refactors are welcome when they clarify architecture; always pair them with doc and test updates.
- Keep `docs/current-goal.md` concise (active focus, next steps, out-of-scope, completion criteria). Move completed history to README TODOs.
- Keep scoped implementation constraints in local `AGENTS.md` files near the code, not the root README.

## Memory Architecture Direction

- Prefer open typed memory (`MemoryObject + MemoryTypeDescriptor`) over closed enums.
- Descriptors own validation, summarization, merge, decay, conflict, retrieval, and reflection rules.
- Symbolic memory evolves as a derived open graph with `RelationDescriptor` rules.
- File-backed private memory is authoritative; all indexes are derived and rebuildable.

## Private Memory

- Real personal memory lives in the root `private/` directory.
- `private/` is ignored by Git and must not be committed.
- Code loads from `private/` by default; tests and demos use `examples/private/`.
