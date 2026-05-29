# NuSelf System Specifications

This directory contains the authoritative behavioral specifications for NuSelf. These documents define contracts, state machines, valid transitions, and output formats. Code changes that alter any behavior described here must update the corresponding spec in the same commit.

## Spec Index

| Spec | Scope |
|---|---|
| [`development.md`](development.md) | Code standards, commit policy, development workflow |
| [`cli.md`](cli.md) | CLI commands, REPL commands, output formats, color conventions |
| [`memory.md`](memory.md) | Memory intake, curation, optimization, query, type system, symbolic graph |
| [`reflection.md`](reflection.md) | Reflection scheduler event taxonomy, pipeline flow, discussion outcomes |
| [`reason.md`](reason.md) | Long-run reasoning threads for sustained work on explicit topics |
| [`reason-output.md`](reason-output.md) | Reason-scoped long-form export and output composition |
| [`workspace.md`](workspace.md) | Isolated private scratch storage for agent-facing services |
| [`trace.md`](trace.md) | TODO thought provenance records for tracing how important thoughts were derived |
| [`notification.md`](notification.md) | Outbox state machine, delivery pipeline, adapters, deep links |
| [`persona/`](persona/) | Persona subsystem — builtin personas (`static.md`), competitive discussion (`discussion.md`), dynamic prompts (`dynamic.md`) |
| [`presentation.md`](presentation.md) | Final user-facing answer presentation stage and retry boundary |
| [`errors.md`](errors.md) | Error classes, retry policy, exception-chain preservation |
| [`logs.md`](logs.md) | Log components, write/read contracts, event structure |
| [`config.md`](config.md) | Config hierarchy, env overrides, runtime paths |
| [`versioning.md`](versioning.md) | Package versioning, changelog, and release checklist |

## Change Policy

- Specs are authoritative. A behavioral change is not complete until the spec is updated.
- When adding a new subsystem, create a new spec file and register it here.
- Natural-language design documents (architecture, plans) live in `docs/`. Behavioral contracts live in `docs/spec/`.
