# AGENTS.md

This project is an AI-Mirror of most ideas of one person, for those who want to discuss further on some topics but there is no one available for them.  For myself, one with similar life experience and knowledge structure, whereas with broader view and further understanding is the best.

## Code Standard

- Standard Python project managed by `uv`.
- Code must be type-checked with `uvx pyright`.
- Sub-components must be tested individually.
- User-facing workflow or feature changes must update both `README.md` and `README.zh-CN.md`.
- Project progress is tracked in the TODOs section of `README.md`; completed features and planning changes must update that checklist.
- Short-term implementation focus is tracked in `docs/current-goal.md`.

## Development Style

- This project is in active early development; prefer direct, clean implementation over compatibility shims.
- When an interface changes, update all callers, tests, examples, and docs to the new interface in the same change.
- Do not preserve old CLI commands, protocol fields, data schemas, or module APIs unless a current document explicitly requires them.
- Aggressive refactoring is acceptable when it clarifies architecture, removes obsolete concepts, or aligns code with the current design.
- Keep refactors intentional: update documentation and validation together with the code change.
- When commands, configuration, runtime behavior, or user-facing workflows change in a way users need to learn, update both English and Chinese README files in the same change.
- When completing a feature or changing the development plan, update the project TODOs in [README.md](README.md) and keep [README.zh-CN.md](README.zh-CN.md) synchronized.
- Commit feature implementation and current-task/progress updates separately. The first commit should contain the functional code and tests; the second commit should contain `docs/current-goal.md`, README TODO progress, and development-guidance updates.
- Before starting non-trivial implementation work, check [docs/current-goal.md](docs/current-goal.md). If the requested task conflicts with the current goal, mention the conflict before proceeding.
- When the user changes the current focus, update [docs/current-goal.md](docs/current-goal.md) and README TODOs in the same change.
- Keep [docs/current-goal.md](docs/current-goal.md) concise. It should describe the active focus, immediate context, next few steps, out-of-scope work, and completion criteria; do not use it as a changelog or completed-work archive.
- Move completed feature history and progress checkmarks into the README TODOs instead of accumulating them in [docs/current-goal.md](docs/current-goal.md).
- Keep implementation constraints and small behavior polish in scoped `AGENTS.md` files near the code rather than overloading the user README.

## Project Design

- Current short-term goal: [docs/current-goal.md](docs/current-goal.md)
- User-facing project progress TODOs: [README.md](README.md)
- Architecture overview: [docs/architecture.md](docs/architecture.md)
- Development plan: [docs/development-plan.md](docs/development-plan.md)
- Agent framework plan: [docs/agent-framework.md](docs/agent-framework.md)
- Interaction layer plan: [docs/interaction-layer.md](docs/interaction-layer.md)
- Memory management plan: [docs/memory-management.md](docs/memory-management.md)
- Public sample memory directory: [examples/private/](examples/private/)

Keep these documents current when changing the system shape, module boundaries, or milestone order.

## Memory Architecture Direction

- Prefer open typed memory over closed enum-style memory categories.
- Long-term memory should evolve toward `MemoryObject + MemoryTypeDescriptor`, where descriptors own schema validation, summarization, merge, decay, conflict, retrieval, and reflection rules.
- Symbolic memory should evolve as a derived open graph with `RelationDescriptor` rules, not as hard-coded relation enums.
- File-backed private memory remains authoritative; graph indexes, vector indexes, lexical indexes, and LangGraph Store mirrors are derived and rebuildable.

## Private Memory

- Real personal memory lives in the root `private/` directory.
- `private/` is ignored by Git and must not be committed.
- Code should load private memory from `private/` by default, while tests and demos should use `examples/private/`.
