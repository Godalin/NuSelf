# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — closing Tool effects for the 0.4.0 release boundary.

## Objective

Replace the remaining central Tool-effect union/handler and approval-shaped
transport with immutable `FeatureEffect` declarations bound per invocation to
`BoundFeatureEffect` implementations. Make observation the sole Tool logging
authority, keep Agent middleware limited to execution safety, and prepare the
verified result as NuSelf 0.4.0.

## Next Steps

1. Specify declaration binding, lifecycle ordering, generic interaction
   protocol, observation ownership, and release boundaries.
2. Implement `FeatureEffect`, `BoundFeatureEffect`, `EffectEnvironment`, and
   invocation-scoped lifecycle execution without a central effect union.
3. Move interaction codecs to `runtime.feature`; remove approval knowledge
   from daemon and LangGraph supervision, and make terminal dispatch explicit.
4. Move Tool outcome observation into the observed effect and reduce Agent
   middleware to retry safety and invocation-local execution tracking.
5. Add architecture/protocol tests, update version and changelog to 0.4.0,
   run full test/type/build/wheel verification, and create the release PR.

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
