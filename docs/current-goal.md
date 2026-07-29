# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Remove the CLI composition root's process-global `warnings.warn` replacement.
The known LangGraph/LangChain import warning must be suppressed only while
loading the CLI chat adapter, without hiding unrelated warnings or changing the
warning callable.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Identify the exact third-party import, warning category, and message.
2. Update CLI, error, and development specs before implementation.
3. Replace callable monkeypatching with one exact `catch_warnings` filter around
   the `cli.chat` import only.
4. Prove unrelated warnings remain visible and `warnings.warn` identity is
   unchanged after importing `nuself.cli`.
5. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No dependency upgrade or patch to LangGraph/LangChain.
- No suppression of urllib3, Pydantic, or other import warnings.
- No lazy-loading redesign of the CLI composition root.
- No change to CLI commands, output, exit status, or chat runtime behavior.

## Completion Evidence

Pending.

## Publication

Pending implementation and validation.
