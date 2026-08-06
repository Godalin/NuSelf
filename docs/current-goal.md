# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — Tool effect implementation complete; preparing the 0.4.0 release.

## Objective

Replace the remaining central Tool-effect union/handler and approval-shaped
transport with immutable `FeatureEffect` declarations bound per invocation to
`BoundFeatureEffect` implementations. Make observation the sole Tool logging
authority, keep Agent middleware limited to execution safety, and prepare the
verified result as NuSelf 0.4.0.

## Next Steps

1. Update package version and reorganize the accumulated changelog as 0.4.0.
2. Run full pytest, Pyright, build, clean-wheel smoke, release-gate, and diff
   verification.
3. Commit release metadata, restore this board to Idle, and create the 0.4.0
   release PR to `main` without tagging an unmerged release.

## Exclusions

- Do not add a new user-facing effect or frontend.
- Do not build a dynamic plugin or service-locator registry.
- Do not make continuations durable or redesign ConversationStore/scheduler
  outcomes unless a current correctness defect requires it.
- Do not move domain mutations, framework objects, or runtime dependencies into
  decorators or service functions.

## Completion Evidence

- `FeatureSpec.effects` contains only `FeatureEffect` declarations; the
  executor knows no approval/observation/audit concrete types.
- Bound effects are invocation-scoped and lifecycle order is stable regardless
  of decorator order; service calls remain exactly once.
- Approval request/resolution are concrete implementations of generic typed
  interaction bases; daemon and supervisor do not import approval types.
- `@observed` solely declares Tool lifecycle/outcome logging; middleware owns
  only execution safety and classification-based retry suppression.
- Runtime producer is injected, approval requested is visible before suspend,
  and all architecture/protocol tests pass.
- Package/build/changelog report 0.4.0; full pytest, Pyright, build, clean-wheel
  smoke, and `git diff --check` pass.
