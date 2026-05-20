# AGENTS.md

An AI mirror for deep personal discussion — someone with similar life experience but broader perspective.

> Behavioral specifications live in [`docs/spec/`](docs/spec/). This file is for project context and high-level direction.

## Development Constraints

- **Design before implement**: For any non-trivial feature or behavioral change, write or update the relevant `docs/spec/` document **before** writing implementation code.
- **Spec is authoritative**: A feature change is not complete until the spec that governs it is updated in the same change.
- **No spec drift**: If code behavior diverges from its spec, either fix the code or update the spec. The spec must always describe the actual system.
- **Changelog for user-visible changes**: Any user-visible feature, fix, command/config change, or behavior change must update [`CHANGELOG.md`](CHANGELOG.md) under `Unreleased` in the same change. Purely internal refactors and tests may skip the changelog only when behavior and docs are unchanged.
- **Use framework-native agent APIs**: When LangChain/LangGraph provides an official abstraction for agent behavior, tool calling, structured output, middleware, state graphs, or model invocation, NuSelf should use that abstraction instead of inventing a parallel protocol. Custom code should wrap NuSelf domain behavior, not replace the framework's agent runtime contracts.

## Quick Links

- [`docs/spec/development-process.md`](docs/spec/development-process.md) — code standards, commit policy, architecture direction
- [`docs/spec/cli-interaction.md`](docs/spec/cli-interaction.md) — CLI/REPL output contracts
- [`docs/spec/memory.md`](docs/spec/memory.md) — memory system behavioral contracts
- [`docs/spec/reflection.md`](docs/spec/reflection.md) — reflection event taxonomy and pipeline
- [`docs/spec/long-reasoning.md`](docs/spec/long-reasoning.md) — TODO long-run reasoning thread contracts
- [`docs/spec/private-workspace.md`](docs/spec/private-workspace.md) — isolated private scratch storage for agent-facing services
- [`docs/spec/trace.md`](docs/spec/trace.md) — TODO thought provenance contracts
- [`docs/spec/notification.md`](docs/spec/notification.md) — outbox state machine and delivery
- [`docs/spec/persona-discussion.md`](docs/spec/persona-discussion.md) — competitive discussion flow
- [`docs/spec/error-handling.md`](docs/spec/error-handling.md) — error classes, retry policy, exception-chain preservation
- [`docs/spec/logging.md`](docs/spec/logging.md) — log write/read contracts
- [`docs/spec/configuration.md`](docs/spec/configuration.md) — config hierarchy and runtime paths
- [`docs/spec/versioning.md`](docs/spec/versioning.md) — version, changelog, and release rules
