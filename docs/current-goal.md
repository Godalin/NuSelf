# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Persona graph structured outputs are strict, and
`with_structured_output(...)` must return the declared model type.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Activation, contribution, and synthesis output models use strict types and
  forbid unknown fields.
- Contribution and synthesis confidence values are constrained to the
  inclusive zero-to-one range.
- Persona graph structured endpoints accept only an instance of the requested
  output model; dictionary results are observed endpoint failures.
- Endpoint fakes now return typed models, and regression tests cover dictionary
  rejection, coercion rejection, extra fields, and confidence bounds.
- The documented ordinary `ChatLLM` fallback after structured endpoint
  exhaustion remains unchanged.
- Focused persona/chat tests: 92 passed.
- Final full tests: 1425 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit reflection and memory LLM JSON models for strict shape, numeric bounds,
and fail-closed action dispatch.
