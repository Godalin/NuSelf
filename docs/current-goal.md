# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make LangChain structured-response state authoritative when present, without
removing the compatibility path for runtimes that omit it.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace structured-response parsing and endpoint failover behavior.
2. [x] Specify authoritative and compatibility state paths.
3. [x] Reject malformed or protocol-like structured responses explicitly.
4. [x] Preserve message fallback only when structured state is absent.
5. [x] Add focused parser and endpoint-boundary tests.
6. [x] Run full tests, type checking, and formatting checks.
7. [x] Commit this stage as one functional change.

## Out Of Scope

- Changing `ChatStructuredOutput` fields or user-visible response payloads.
- Removing local-LLM fallback after all configured LangChain endpoints fail.
- Changing tool definitions, middleware, or conversation graph nodes.
- Auditing CLI configuration and history fallbacks in the same commit.

## Completion Evidence

- Valid framework structured output is accepted.
- Present-but-invalid structured output raises into retry/failover rather than
  being reinterpreted from ordinary messages.
- Missing structured state can still parse the final message for compatibility.
- Protocol-like tool-call text is rejected in either path.
- Focused parser tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue the classified exception audit with CLI configuration and history
boundaries.
