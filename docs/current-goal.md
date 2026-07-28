# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make persona activation and competitive-discussion schemas authoritative so
malformed LLM output cannot pass through looser handwritten parsers.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Compare typed and handwritten persona parser behavior.
2. [x] Specify authoritative activation, scoring, selection, and moderator schemas.
3. [x] Reject string booleans, numeric strings, and mixed malformed selections.
4. [x] Remove duplicate handwritten parsing paths.
5. [x] Preserve the existing no-activation, default-participant, neutral-score,
   and non-converged fallbacks.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing activation policy, participant limits, score clamping, or moderator policy.
- Changing valid persona identifiers or emergent-persona behavior.
- Migrating model invocation to a different LangChain abstraction.
- Tightening contribution or synthesis schemas in this same commit.

## Completion Evidence

- Valid activation, scoring, selection, and moderator JSON produces the same
  domain values.
- String booleans and numeric strings fail schema validation instead of being
  coerced.
- One malformed selected-persona item invalidates the selection instead of
  being silently discarded.
- Existing safe fallback behavior remains unchanged at each caller boundary.
- No handwritten dict parser remains behind the four typed schemas.
- Focused persona tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit the remaining derived runtime state for validation, atomic recovery, and
observable failure behavior.
