# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make reflection relevance and candidate-generation schemas authoritative so
malformed LLM output cannot pass through a looser handwritten parser.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Compare Pydantic and handwritten reflection parser behavior.
2. [x] Specify strict authoritative schemas and safe fallback.
3. [x] Reject string booleans and unknown candidate types.
4. [x] Reject an entire malformed candidate list instead of partial acceptance.
5. [x] Remove duplicate handwritten parsing paths.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing relevance thresholds, score clamping, or cooldown policy.
- Changing candidate limits or generated identifiers.
- Migrating model invocation to a different LangChain abstraction.
- Tightening persona activation/discussion parsers in this same commit.

## Completion Evidence

- Valid relevance and candidate JSON still produces the same domain values.
- String booleans, missing fields, and wrong field types use the safe relevance
  fallback instead of being coerced.
- Unknown candidate types or any malformed candidate item fail the generation
  batch and return no candidates with the existing failure event.
- No handwritten dict parser remains behind either typed schema.
- Focused reflection tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Apply the same authoritative-schema review to persona activation and
competitive discussion output.
