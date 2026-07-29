# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close six externally identified runtime-boundary gaps: direct LangChain
dependency ownership, thought-pack export containment, typed agent failures,
structured endpoint availability classification, complete chat-compression
fallback, and observable compression degradation.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Verify every external finding against source, tests, and dependency metadata.
2. Declare the directly imported `langchain` distribution and lock it.
3. Restrict pack export names to contained portable file names.
4. Define distinct model-unavailable, invalid-output, and protocol agent errors.
5. Replace error-message failover matching with typed/structured exception
   classification.
6. Make every recoverable compression-agent failure fall back locally and emit
   one sealed Chat degradation audit.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No provider retry-count or endpoint-order change.
- No failover based on provider exception message text.
- No change to pack import or inspect path resolution.
- No persistence of raw prompts, summaries, provider responses, or endpoint
  URLs in compression fallback audits.

## Completion Evidence

- CLI warning isolation completed in `2abfc63`.
- Direct runtime dependency ownership and pack export containment completed in
  `7047269`.
- Typed Agent failure contracts and structured provider availability
  classification completed in `5807ee5`.
- Complete observable chat compression fallback completed in `47e2139`.
- Pack focused tests: 22 passed.
- Agent invocation/failover focused tests: 107 passed.
- Chat compression/audit focused tests: 124 passed.
- Full suite: 2081 passed.
- Pyright: 0 errors, 0 warnings.
- Static searches prove production failover no longer classifies rendered
  exception text, compression no longer catches only two exception classes,
  and production code no longer assigns `warnings.warn`.
- `git diff --check`: passed.

## Publication

The external review batch is implemented in `7047269`, `5807ee5`, and
`47e2139`; milestone publication is pending this goal update and push.

## Next Review Batch

Resume the shared-infrastructure review at internal message delivery: inventory
`RuntimeEnvelope`, publisher/subscriber failure isolation, correlation-context
propagation, queue/backpressure policy, and duplicate event transport shapes
before selecting the next aggressive consolidation.
