# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — readable bilingual provenance notifications.

## Objective

Render Reflection provenance as compact Git-like node blocks with stable short
display IDs, readable spacing, and best-effort Chinese translations for
English node bodies.

## Next Steps

1. Specify display-ID, node layout, translation, and degradation contracts.
2. Implement a pure compact renderer and a batched model-backed translator.
3. Compose rendering into Reflection without changing stored provenance IDs.
4. Add focused/full tests, review the diff, and merge a feature PR.

## Exclusions

- Do not shorten or replace canonical IDs in storage or query APIs.
- Do not translate content that already contains Chinese.
- Do not let translation failure suppress the original provenance chain.
- Do not expose hidden reasoning or add a second persistence representation.

## Completion Evidence

- Each node renders its short display ID, body, optional Chinese translation,
  then one blank separator line.
- Display IDs are stable, start at six hexadecimal characters, and expand only
  when required to disambiguate nodes in the same chain.
- English translations are batched, validated, and best-effort.
- Inbox, plain email, and HTML email preserve the same block ordering.
- Pyright, focused tests, full suite, CI, and diff review pass.
