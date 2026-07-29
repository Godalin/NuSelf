# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make memory-backed persona definition fallback observable. A runtime failure
loading durable persona instructions must still return builtin personas while
recording one sealed degradation event; diagnostic failure must not replace the
fallback.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit post-commit auxiliary work and response construction.
2. Distinguish intentionally authoritative follow-up failures from optional
   projections and fallbacks.
3. Identify silent fallbacks that bypass shared observability.
4. Specify a closed Persona audit for durable definition load failure.
5. Record the failure without changing the builtin fallback.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to which repository exceptions trigger fallback.
- No change to builtin persona contents or ordering.
- No fallback for malformed successfully loaded persona entries.
- No persistence of persona instruction payloads in diagnostics.

## Completion Evidence

- Chat trace, audit, reason, memory curator, optimizer, and organizer
  post-commit projections already use best-effort boundaries with failure
  injection tests.
- Reflection repository, schedule-state, and optional outbox writes are
  explicitly authoritative in the Reflection spec and correctly propagate.
- `load_persona_definitions(...)` currently catches repository `RuntimeError`
  and silently returns `BUILTIN_PERSONAS`.
- The fallback has no audit event, so operators cannot distinguish an empty
  instruction set from a storage-backed degraded mode.
- The sealed Persona audit taxonomy now owns
  `persona_definition_load_failed` with warning level, degraded status,
  required canonical error, and no metadata.
- `load_persona_definitions(...)` reports the caught repository failure before
  returning the unchanged builtin tuple.
- Tests prove both the structured degradation record and that terminal
  diagnostic storage failure cannot replace the fallback.
- Focused Persona audit, instruction, and graph tests: 73 passed.
- Full suite: 2140 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; the reviewed silent `RuntimeError` fallback no
  longer returns without observation.

## Publication

Observable persona definition fallback was implemented in `4a38cee`;
milestone publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, continue reviewing silent fallback and broad
exception scopes outside the already-covered agent and storage paths.
