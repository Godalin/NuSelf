# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — readable Reflection notification trace.

## Objective

Render Reflection provenance as a clear final notification section where each
line starts with a stable evidence/decision ID followed by a bounded body
excerpt, and preserve that line structure in HTML email.

## Next Steps

1. Specify the notification trace layout and privacy bounds.
2. Retain validated evidence excerpts with generated candidates.
3. Render the final trace section and preserve newlines in HTML email.
4. Add focused tests, update user documentation, and run full validation.
5. Review and merge a feature PR into `dev/v0.4.x`.

## Exclusions

- Do not include raw persona discussion traces or hidden model reasoning.
- Do not expand evidence beyond the bounded context already supplied to the
  candidate generator.
- Do not change Reflection scheduling, scoring, or delivery routing.

## Completion Evidence

- Reflection Inbox/email text ends with one trace section.
- Every trace line starts with a stable ID and then a single-line bounded body.
- Evidence IDs remain validated against the supplied context catalog.
- Plain-text and HTML email preserve the same ordering and line boundaries.
- Focused tests, Pyright, the full suite, CI, and diff review pass.
