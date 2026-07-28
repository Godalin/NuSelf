# AGENTS.md

An AI mirror for deep personal discussion — someone with similar life experience but broader perspective.

> Behavioral specifications live in [`docs/spec/`](docs/spec/). This file is for project context and high-level direction.

## Development Constraints

- **Track active work in current-goal**: Read [`docs/current-goal.md`](docs/current-goal.md)
  before starting non-trivial work. Before implementation, make sure it names
  the active objective, ordered steps, exclusions, and completion evidence.
  Update its checkboxes and scope as soon as progress or direction changes, and
  include the relevant progress update in the same functional commit. Do not
  leave completed work there as project history; once an objective is complete,
  move unresolved follow-ups to [`docs/TODOs.md`](docs/TODOs.md) and return
  `current-goal.md` to an explicit idle state.
- **Design before implement**: For any non-trivial feature or behavioral change, write or update the relevant `docs/spec/` document **before** writing implementation code.
- **Spec is authoritative**: A feature change is not complete until the spec that governs it is updated in the same change.
- **No spec drift**: If code behavior diverges from its spec, either fix the code or update the spec. The spec must always describe the actual system.
- **Changelog for user-visible changes**: Any user-visible feature, fix, command/config change, or behavior change must update [`CHANGELOG.md`](CHANGELOG.md) under `Unreleased` in the same change. Purely internal refactors and tests may skip the changelog only when behavior and docs are unchanged.
- **Use framework-native agent APIs**: When LangChain/LangGraph provides an official abstraction for agent behavior, tool calling, structured output, middleware, state graphs, or model invocation, NuSelf should use that abstraction instead of inventing a parallel protocol. Custom code should wrap NuSelf domain behavior, not replace the framework's agent runtime contracts.

## Quick Links

- [`docs/current-goal.md`](docs/current-goal.md) — active objective, ordered work, and completion evidence
- [`docs/TODOs.md`](docs/TODOs.md) — unresolved medium/long-term backlog
- [`docs/architecture.md`](docs/architecture.md) — current system boundaries and design rationale
- [`docs/spec/development.md`](docs/spec/development.md) — code standards, commit policy, architecture direction
- [`docs/spec/cli.md`](docs/spec/cli.md) — CLI/REPL output contracts
- [`docs/spec/memory.md`](docs/spec/memory.md) — memory system behavioral contracts
- [`docs/spec/reflection.md`](docs/spec/reflection.md) — reflection event taxonomy and pipeline
- [`docs/spec/reason.md`](docs/spec/reason.md) — long-run reasoning thread contracts
- [`docs/spec/workspace.md`](docs/spec/workspace.md) — isolated private scratch storage for agent-facing services
- [`docs/spec/trace.md`](docs/spec/trace.md) — TODO thought provenance contracts
- [`docs/spec/notification.md`](docs/spec/notification.md) — outbox state machine and delivery
- [`docs/spec/persona/`](docs/spec/persona/) — persona subsystem: builtin (`static.md`), competitive discussion (`discussion.md`), dynamic prompts (`dynamic.md`)
- [`docs/spec/errors.md`](docs/spec/errors.md) — error classes, retry policy, exception-chain preservation
- [`docs/spec/logs.md`](docs/spec/logs.md) — log write/read contracts
- [`docs/spec/runtime-infrastructure.md`](docs/spec/runtime-infrastructure.md) —
  shared handlers, events, jobs, correlation, and log boundaries
- [`docs/spec/config.md`](docs/spec/config.md) — config hierarchy and runtime paths
- [`docs/spec/versioning.md`](docs/spec/versioning.md) — version, changelog, and release rules
