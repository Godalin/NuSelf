# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — migrating subsystem composition to service boundaries.

## Objective

Make services the boundary consumed by CLI, REPL, agent tools, request
handlers, and cross-domain workflows. Keep repositories, persistence stores,
and private workspaces inside their owning domain composition, except for
explicit administration, projection, recovery, and migration ports.

## Next Steps

1. Complete Memory entry, candidate-review, profile, and maintenance services;
   migrate ordinary adapters away from `MemoryRepositories`.
2. Add Conversation management and Persona services/providers; remove their
   repositories and stores from ordinary adapters.
3. Add Delivery services and completed background workflow composition.
4. Internalize Reflection repository and Reason workspace requirements behind
   owner-composed services and workflows.
5. Replace general graph borrowing with consumer-specific service/workflow
   snapshots and enforce the boundary with architecture tests.
6. Run full verification, delete the temporary composition audit, record any
   unresolved follow-up in `TODOs.md`, and return this file to Idle.

Current progress: Memory entry, candidate-review, and profile services now own
ordinary CLI/REPL use cases. Memory curator/optimizer composition, observation
recovery, and explicit import/export remain narrow workflow work for the final
application snapshot migration.

Persona management, Chat tools, and Reason workflows now consume one
authority-scoped `PersonaService`; the prompt repository is constructed only
inside application or thread-local Persona composition.

Conversation execution, history, and management now consume one
authority-scoped `ConversationService`; only validated data administration
retains the underlying `ConversationStore`.

Delivery requests, Reflection publication, and background adapter transitions
now consume `DeliveryService`; `DeliveryStore` remains inside application
composition.

Reflection scheduling and relevance now consume `ReflectionService`, while
Reason tools, advancement, export, and recovery consume `ReasonService` for
thread workspace capabilities. Neither `ReflectionRepository` nor
`PrivateWorkspaceStore` remains on its domain resource snapshot.

## Exclusions

- Do not add forwarding methods that merely mirror every repository operation;
  service APIs represent stable user or workflow intent.
- Do not route projection, recovery, migration, repair, or validated data
  administration through a universal public service.
- Do not add a service locator, common service base class, dynamic registry, or
  duplicate authority graph.
- Do not combine this work with retrieval, configuration, distribution, or
  conversation crash-durability backlog items.

## Completion Evidence

- General process adapters receive services or completed workflow snapshots,
  not domain repositories or persistence stores.
- `ApplicationGraph` does not expose `MemoryRepositories`, `DeliveryStore`,
  `PersonaPromptRepository`, `ReflectionRepository`, or
  `PrivateWorkspaceStore` to general consumers.
- Internal curator, projection, recovery, scheduler, export, and administration
  paths reuse the single authority-owned persistence graph.
- Declarative architecture tests enforce the allowed exceptions.
- `uv run --locked pytest`, `uv run --locked pyright`, and `git diff --check`
  pass.
