# NuSelf System Specifications

This directory contains the authoritative behavioral specifications for NuSelf. These documents define contracts, state machines, valid transitions, and output formats. Code changes that alter any behavior described here must update the corresponding spec in the same commit.

## Spec Index

| Spec | Scope |
|---|---|
| [`development.md`](development.md) | Code standards, commit policy, development workflow |
| [`module-boundaries.md`](module-boundaries.md) | Package dependency direction, composition ownership, and shared-code extraction |
| [`runtime-infrastructure.md`](runtime-infrastructure.md) | Shared handlers, envelopes, events, jobs, daemon payloads, and activity transport |
| [`cli.md`](cli.md) | CLI commands, REPL commands, output formats, color conventions |
| [`agent-tools.md`](agent-tools.md) | Agent-facing tool contracts, approval boundaries, and capability groups |
| [`llm.md`](llm.md) | Model invocation, structured output, endpoint failover, and framework boundaries |
| [`memory.md`](memory.md) | Memory intake, curation, optimization, query, type system, symbolic graph |
| [`source.md`](source.md) | External document ingestion, retrieval, connectors, and Source tools |
| [`reflection.md`](reflection.md) | Reflection scheduler event taxonomy, pipeline flow, discussion outcomes |
| [`reason.md`](reason.md) | Long-run reasoning threads for sustained work on explicit topics |
| [`reason-output.md`](reason-output.md) | Reason-scoped long-form export and output composition |
| [`workspace.md`](workspace.md) | Isolated private scratch storage for agent-facing services |
| [`trace.md`](trace.md) | TODO thought provenance records for tracing how important thoughts were derived |
| [`inbox.md`](inbox.md) | Generic user-attention items, lifecycle, publishers, and commands |
| [`delivery.md`](delivery.md) | External presentation records, delivery pipeline, and adapters |
| [`persona/`](persona/) | Persona subsystem — builtin personas (`static.md`), competitive discussion (`discussion.md`), dynamic prompts (`dynamic.md`), and management (`management.md`) |
| [`presentation.md`](presentation.md) | Final user-facing answer presentation stage and retry boundary |
| [`errors.md`](errors.md) | Error classes, retry policy, exception-chain preservation |
| [`logs.md`](logs.md) | Log components, write/read contracts, event structure |
| [`config.md`](config.md) | Config hierarchy, defaults, and runtime paths |
| [`scope.md`](scope.md) | User/workspace scope selection, authority identity, daemon isolation, and legacy layout migration |
| [`storage-v2.md`](storage-v2.md) | SQLite storage, migrations, and thought-pack contracts |
| [`database-migrations.md`](database-migrations.md) | Versioned SQLite migration artifacts, planning, reversal, and safety |
| [`hardcode.md`](hardcode.md) | Policy for constants, defaults, prompts, and configurable values |
| [`versioning.md`](versioning.md) | Package versioning, changelog, and release checklist |

## Change Policy

- Specs are authoritative. A behavioral change is not complete until the spec is updated.
- When adding a new subsystem, create a new spec file and register it here.
- Current architecture rationale lives in
  [`../architecture.md`](../architecture.md). Historical
  plans remain available through Git history rather than as parallel active
  behavior documents.
