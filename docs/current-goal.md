# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — shorten the public confirmation declaration and seal effect composition.

## Objective

Rename the public Tool confirmation decorator to `confirmed` while preserving
the generic ABC-based effect interpreter and proving existing effects compose.

## Next Steps

1. Update the governing Tool specification and public decorator vocabulary.
2. Migrate Tool declarations and tests without changing approval semantics.
3. Strengthen composition coverage, run full validation, and update PR #4.

## Exclusions

- Do not rename the internal `ApprovalEffect` protocol types.
- Do not add a compatibility alias for the superseded pre-1.0 spelling.

## Completion Evidence

- No production or test reference uses `requires_confirmation`.
- A Tool carrying approval, observation, audit, execution, and presentation
  declarations executes through the generic effect ABC lifecycle.
- Full pytest, Pyright, build, wheel smoke, and diff checks pass.
