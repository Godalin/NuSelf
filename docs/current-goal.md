# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — readable Reflection email provenance projection.

## Objective

Keep the complete Memory → Trace → Reflection provenance graph while making
Reflection Inbox/email output non-repetitive and making generation evidence,
assessment, and decisions easy to scan.

## Next Steps

1. Specify the distinction between the stored provenance graph and its
   Reflection notification projection.
2. Omit the terminal Reflection artifact block when the notification body
   already presents that artifact.
3. Render Reflection generation Trace details as labeled multiline fields and
   decision bullets.
4. Verify focused/full tests, diff review, CI, and merge a feature PR into
   `dev/v0.4.x`.

## Exclusions

- Do not remove the terminal Reflection node from the provenance graph.
- Do not merge the process Trace with the Reflection artifact.
- Do not truncate evidence, decision points, or translations.
- Do not introduce provider-specific rendering behavior.

## Completion Evidence

- Stored provenance still resolves Memory → Trace → Reflection.
- Reflection Inbox/email contains the Reflection body once.
- The Trace block separates summary, evidence count, assessment, and each
  decision without parsing or inferring evidence from prose.
- Focused tests, Pyright, full suite, CI, and diff review pass.
