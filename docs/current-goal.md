# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close one-shot CLI handler ownership so argparse selects stable command keys
and a sealed shared registry performs dispatch.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory all one-shot CLI handler bindings, help-only parser states, and
   dispatch tests.
2. Define stable command keys without duplicating argparse's presentation and
   argument schema.
3. Update the CLI/development specs before changing composition.
4. Compose and seal one `HandlerRegistry` for the parser tree; parsed
   namespaces carry keys rather than raw callable objects.
5. Preserve help behavior, integer result validation, dependency-injected
   entry handlers, and every existing command surface.
6. Reject duplicate keys, unsealed dispatch, unknown commands, and callable
   return-contract violations through the shared handler boundary.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No CLI command rename, flag change, output change, or handler behavior change.
- No merge of REPL command parsing with argparse; both reuse the shared
  registry primitive while retaining their distinct grammars.
- Closed job message contracts were completed in `2c74e2d`.
- Generic corrupt-record and audit-projection diagnostics remain shared.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- Initial inspection finds daemon requests and REPL commands already use
  `HandlerRegistry`, while one-shot argparse embeds raw callables in parsed
  namespaces.
- Initial inventory found 103 handler bindings across the root and Memory
  parser modules.
- `CliHandlerBindings` now derives stable keys from complete parser `prog`
  values, composes one registry per parser tree, and seals it before returning
  the root parser.
- Parsed namespaces contain `handler_key` only; dispatch resolves through the
  sealed registry and retains strict integer exit-status validation.
- Registry composition exposed and removed two duplicate log-command
  bindings that argparse previously overwrote silently, leaving 101 unique
  one-shot command handlers.
- Focused CLI suite: `315 passed`.
- Full test suite: `2007 passed`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- `git diff --check` passed.

## Publication

Pending this batch's implementation commit and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after one-shot CLI
dispatch is verified and published.
