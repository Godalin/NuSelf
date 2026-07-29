# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Unify local runtime-job construction under sealed semantic definitions.
Production code must not create unknown or invalid job messages before queue
ingress, while decoded envelopes remain structurally representable and are
revalidated at every trust boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory all event/job/audit envelope construction and first semantic
   validation points.
2. Separate transport-envelope structural invariants from domain semantic
   authorization.
3. Add registry-owned job construction and remove unchecked
   `JobMessage.create(...)`.
4. Give every production job producer a sealed registry and retain queue
   ingress validation for decoded/untrusted messages.
5. Prove invalid name, producer, and domain data fail before a message is
   returned or queue state changes.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No universal factory that merges event, job, and audit semantic registries.
- No assumption that successful envelope decoding grants domain authorization.
- No compatibility retention of unchecked `JobMessage.create(...)`.
- No change to job payload wire shape or durable manifest recovery.

## Completion Evidence

- Event publication resolves a sealed event definition and validates its
  payload before constructing the event envelope.
- Direct audit construction validates component, audit-name grammar, and typed
  log payload before constructing its envelope; domain audit registries remain
  separate presentation/metadata contracts.
- `JobMessage.create(...)` currently constructs unknown job names, disallowed
  producers, and invalid domain data; only the worker queue ingress rejects
  them.
- Reason initial export, retry, and reconciliation are the only production job
  producers and all use the same closed Reason job definition builder.
- `JobDefinitionRegistry.create(...)` is now the only field-based local job
  constructor. It builds the immutable structural envelope, validates the
  registered name, allowed producer, and exact domain data, then returns the
  authorized `JobMessage`.
- `JobMessage.create(...)` was removed without a compatibility alias.
- `DefinitionRegistry` exposes thread-safe sealed state; job validation and
  construction reject unsealed registries before entering runtime use.
- Reason initial export, retry, and reconciliation producers all use their
  sealed Reason job registry.
- Structurally decoded messages remain representable and worker ingress still
  validates them before queue mutation; the unknown-job ingress test uses this
  explicit untrusted path.
- Production `RuntimeEnvelope(...)` construction now occurs only inside the
  event publisher, audit builder, and job definition registry.
- Focused definition, job, message, Reason contract/output, and export recovery
  tests: 114 passed.
- Full suite: 2121 passed.
- Pyright: 0 errors, 0 warnings.
- Static search found no `JobMessage.create(...)` or uncontrolled production
  envelope construction; `git diff --check` passed.

## Publication

Registry-owned job construction was implemented in `379e328`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review sealed-definition runtime ownership next. Job registries now reject
runtime validation/construction before sealing, but `EventPublisher` accepts an
arbitrary `EventDefinitionRegistry` and the shared definition resolver itself
permits lookup during composition. Verify whether a publisher can observe late
event registration or partially composed definitions, and make runtime owners
require an immutable sealed snapshot consistently.
