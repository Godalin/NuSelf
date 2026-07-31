# Module Boundaries

Status: authoritative for v0.3.1.

## Purpose

NuSelf modules are separated by ownership and dependency direction, not merely
by directory names. Shared infrastructure exists only for semantics that are
genuinely common. A shared module must reduce coupling; it must not become a
generic dumping ground that every package can import.

## Dependency Direction

The stable direction is:

```text
CLI / daemon / agent-tool / TUI adapters
                    |
          application composition
                    |
       domain services and workflows
                    |
      repositories and declared ports
                    |
      runtime / storage / filesystem
```

The following import rules are mandatory:

- `nuself.runtime` is dependency-neutral infrastructure. It must not import
  CLI, daemon, agent, TUI, REPL, or business-domain packages.
- Storage, configuration, scope, clock, and private-filesystem foundations
  must not import presentation or process adapters.
- Business-domain packages must not import CLI, daemon, TUI, or REPL modules.
- `nuself.agent` may depend on domain services and framework APIs, but never on
  terminal presentation or daemon/CLI adapters.
- CLI, daemon, and TUI are outer adapters and may depend inward.
- A function-local import does not exempt a dependency from these rules.

These rules are checked from the Python AST in the test suite. New exceptions
require a specification change naming the owner and removal condition; an
unrecorded allowlist is forbidden.

## Composition Ownership

Scope and paths are resolved once by an outer composition root. Storage is
opened once for that authority. Domain repositories receive both the selected
`StorageBackend` and resolved `RuntimePaths` as explicit constructor
dependencies; accepting a project root and resolving either dependency inside
the repository is forbidden. Services receive repositories, clocks, sinks,
and cross-domain capabilities explicitly.

`AuthorityRuntime` is the shared authority-lifetime owner. Construction takes
already-resolved `RuntimePaths` and one closeable `StorageBackend`; the public
factory performs scope-derived path resolution and opens storage. The owner is
not a service locator: it exposes only those two neutral resources and does
not construct or cache domain services. It is context-manageable, closes its
backend exactly once, and rejects resource access after close. A backend close
failure propagates from the first close while the owner still remains closed;
cleanup code must not invoke the backend again.

`get_default_backend()` and `runtime_paths()` are compatibility-free
composition helpers, not domain service locators. Domain repositories must not
call them. Direct CLI mode and daemon mode must construct the same service
graph; transport and lifecycle ownership are their only differences.

The trace package is the first migrated domain boundary. `TraceRepository`
requires an explicit `StorageBackend` and `RuntimePaths`, and `TraceRecorder`
and `TraceQueryService` require an explicit repository. `nuself.application`
owns the factory that assembles those concrete objects into immutable
`TraceServices`; the domain package does not own an authority-resolving
factory. Reintroducing backend or path resolution in the trace package is
forbidden and covered by executable architecture tests.

Profile follows the same boundary: `ProfileItemRepository` receives resolved
paths and storage, profile aggregation receives a repository, and the
application layer owns concrete profile construction. Neither domain may
recover authority resources from a project root.

`ReasonRepository` likewise receives resolved paths and storage, and the
application layer owns its concrete factory. Existing reason workflow
constructors remain migration scope and may still resolve authority while the
service graph is centralized, but the repository itself must never recover
authority. Reason domain modules must not import the application package:
doing so creates an application→reason→application cycle during cold process
startup.

Cross-domain behavior depends on a narrow `Protocol` owned by the consumer or
by a neutral contracts module. It must not depend on another domain's concrete
repository merely to call one capability.

## Shared Infrastructure Extraction

Code becomes shared infrastructure only when all of these are true:

1. at least two owners require the same semantics, not merely similar syntax;
2. one neutral owner can state the complete lifecycle and error contract;
3. consumers can depend inward without creating a cycle;
4. configuration and mutable state remain instance-scoped;
5. the extracted API is narrower than the implementations it replaces.

Shared contracts, immutable result types, validation, correlation context,
handler primitives, clocks, atomic persistence, and lifecycle cleanup are good
candidates. Domain policy, terminal wording, provider-specific behavior, and
one-off convenience wrappers remain with their owners.

Shared modules use specific names such as `runtime.handlers` or
`runtime.cleanup`; new catch-all `utils`, `helpers`, or `common` modules are
forbidden. Existing modules with those names must remain narrowly scoped.

## Presentation Boundary

Domain models expose typed state or wire-safe data. Agent tools return
model-facing structured text owned by the agent adapter. TUI and CLI renderers
own terminal color, layout, labels, and interactive formatting.

Agent tools and domain services must not reuse a TUI renderer merely because
both outputs are strings. If two adapters need identical neutral
serialization, that serializer belongs beside the domain contract and must not
import presentation infrastructure.

## Migration Order

Decoupling proceeds from enforceable boundaries inward:

1. reject adapter-direction violations;
2. centralize runtime composition;
3. inject storage and resolved paths into repositories;
4. replace concrete cross-domain dependencies with narrow ports;
5. split oversized cross-cutting modules after ownership is explicit.

Each step removes the old path repository-wide. NuSelf does not retain parallel
service locators, forwarding APIs, or deprecated construction paths during
active v0.3.1 development.
