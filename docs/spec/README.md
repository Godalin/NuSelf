# NuSelf System Specifications

This directory contains the authoritative behavioral specifications for NuSelf. These documents define contracts, state machines, valid transitions, and output formats. Code changes that alter any behavior described here must update the corresponding spec in the same commit.

## Spec Index

| Spec | Scope |
|---|---|
| [`development-process.md`](development-process.md) | Code standards, commit policy, development workflow |
| [`cli-interaction.md`](cli-interaction.md) | CLI commands, REPL commands, output formats, color conventions |
| [`memory.md`](memory.md) | Memory intake, curation, optimization, query, type system, symbolic graph |
| [`reflection.md`](reflection.md) | Reflection scheduler event taxonomy, pipeline flow, discussion outcomes |
| [`long-reasoning.md`](long-reasoning.md) | TODO long-run reasoning threads for sustained work on explicit questions |
| [`notification.md`](notification.md) | Outbox state machine, delivery pipeline, adapters, deep links |
| [`persona-discussion.md`](persona-discussion.md) | Competitive discussion flow, scoring, consensus, trace format |
| [`presentation-agent.md`](presentation-agent.md) | Final user-facing answer presentation stage and retry boundary |
| [`logging.md`](logging.md) | Log components, write/read contracts, event structure |
| [`configuration.md`](configuration.md) | Config hierarchy, env overrides, runtime paths |
| [`versioning.md`](versioning.md) | Package versioning, changelog, and release checklist |

## Change Policy

- Specs are authoritative. A behavioral change is not complete until the spec is updated.
- When adding a new subsystem, create a new spec file and register it here.
- Natural-language design documents (architecture, plans) live in `docs/`. Behavioral contracts live in `docs/spec/`.
