# AGENTS.md

This project is an AI-Mirror of most ideas of one person, for those who want to discuss further on some topics but there is no one available for them.  For myself, one with similar life experience and knowledge structure, whereas with broader view and further understanding is the best.

## Code Standard

- Standard Python project managed by `uv`.
- Code must be type-checked with `uvx pyright`.
- Sub-components must be tested individually.

## Project Design

- Architecture overview: [docs/architecture.md](docs/architecture.md)
- Development plan: [docs/development-plan.md](docs/development-plan.md)
- Agent framework plan: [docs/agent-framework.md](docs/agent-framework.md)
- Public sample memory directory: [examples/private/](examples/private/)

Keep these documents current when changing the system shape, module boundaries, or milestone order.

## Private Memory

- Real personal memory lives in the root `private/` directory.
- `private/` is ignored by Git and must not be committed.
- Code should load private memory from `private/` by default, while tests and demos should use `examples/private/`.
