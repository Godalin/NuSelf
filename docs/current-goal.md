# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Separate handler lookup failure from invocation failure at the daemon boundary.
An `UnknownHandlerError` raised by middleware, a nested registry, or a
registered handler must preserve its identity instead of being relabeled as an
unsupported daemon request.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every `HandlerRegistry` middleware and dispatch exception
   boundary.
2. Verify middleware chain compilation, ownership, ordering, and exception
   identity guarantees.
3. Reproduce a registered daemon handler raising `UnknownHandlerError`.
4. Specify lookup-versus-invocation exception-source semantics.
5. Decide unsupported requests from the immutable sealed key set before
   dispatch and preserve invocation exceptions unchanged.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No wrapping of every handler exception.
- No change to `ProtocolError` request-payload translation.
- No change to middleware order or request context/activity scopes.
- No fallback dispatch for unsupported request keys.

## Completion Evidence

- Only daemon request dispatch installs `HandlerRegistry` middleware; CLI and
  REPL use the same registry without middleware. LangChain middleware remains
  framework-owned and is outside this registry.
- The shared registry compiles middleware once at seal, releases its lock
  before invocation, preserves registration order, and propagates handler
  exception identity.
- Daemon `handle_request(...)` currently catches `UnknownHandlerError` around
  the complete invocation. A registered handler or nested registry raising
  that type is therefore indistinguishable from lookup failure and becomes an
  incorrect `unsupported request type` response.
- Because daemon catalog coverage is sealed and exact, lookup support can be
  decided before invocation without a race.
- `handle_request(...)` now maps unsupported keys from the sealed registry key
  set before dispatch and no longer catches `UnknownHandlerError` around
  invocation.
- A registered handler test raises a specific nested
  `UnknownHandlerError` instance and proves the exact object propagates.
- Existing daemon server coverage still proves a genuinely unsupported request
  returns the transport-level unsupported response.
- Focused handler, daemon request, and daemon server tests: 55 passed.
- Full suite: 2133 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; static search finds no dispatch-wide
  `UnknownHandlerError` catch.

## Publication

Daemon lookup and invocation failure separation was implemented in `47e0603`;
milestone publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, review exception-source ambiguity at other
shared dispatch and projection boundaries.
