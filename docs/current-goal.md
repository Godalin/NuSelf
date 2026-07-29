# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make sealed definitions a universal runtime-read boundary. No publisher,
validator, audit adapter, or warning renderer may resolve a registry while its
identity set remains open to late composition changes.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory shared definition adapters, resolve calls, and runtime owner
   construction.
2. Reproduce lookup and late registration through an EventPublisher-owned
   unsealed registry.
3. Make generic `resolve()` reject unsealed state and preserve composition-time
   definition snapshots.
4. Translate generic state failures at Event, Job, and Audit semantic adapters;
   reject unsealed event registries during publisher construction.
5. Prove late registration cannot change a live owner's identity set.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No merging of Event, Job, Audit, or terminal-warning definition types.
- No implicit auto-seal that hides incomplete composition.
- No compatibility path allowing pre-seal runtime lookup.
- No change to registered identities, payload schemas, or rendering contracts.

## Completion Evidence

- Generic `DefinitionRegistry.resolve()` currently permits lookup before
  sealing even though registration remains open.
- `EventPublisher` accepts an arbitrary `EventDefinitionRegistry` without
  checking sealed state; late registration can therefore expand the supported
  event set during the publisher lifetime.
- Job create/validate already perform explicit sealed-state checks.
- Audit and terminal-warning adapters are built sealed in production but their
  public resolve paths do not enforce that invariant themselves.
- `DefinitionRegistry.resolve()` now raises typed
  `DefinitionRegistryUnsealedError` until composition seals the registry;
  immutable `definitions` snapshots remain available during composition.
- Event, Job, Audit, and terminal-warning adapters translate unsealed lookup
  into domain-specific typed errors.
- `EventPublisher` requires a sealed event registry during construction, so it
  cannot retain a definition set that late registration later expands.
- No registry auto-seals implicitly; incomplete composition remains an explicit
  caller error.
- Focused generic definition, Event, Audit, terminal-warning, Job, and daemon
  audit tests: 94 passed.
- Full suite: 2126 passed.
- Pyright: 0 errors, 0 warnings.
- The full suite proves every production definition builder seals before
  runtime lookup; `git diff --check` passed.

## Publication

Sealed runtime definition lookup was implemented in `93a721a`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review best-effort audit construction next.
`run_observed_best_effort(...)` currently calls `create_audit_envelope(...)`
once outside its failure boundary for validation, discards that envelope, then
`write_log_event(...)` constructs a second envelope from the caller's mutable
inputs. Verify duplicate identity/time allocation, context consistency, and
time-of-check/time-of-use behavior; make validation and persistence operate on
one immutable envelope without misclassifying producer contract errors.
