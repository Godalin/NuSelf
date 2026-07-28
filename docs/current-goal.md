# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make `private/email.toml` decoding strict and observable so present-but-invalid
notification configuration cannot silently look identical to missing config.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit email config parsing and delivery fallback behavior.
2. [x] Specify missing versus invalid configuration semantics.
3. [x] Strictly validate section shapes, required non-empty strings, port range,
   TLS boolean, and paired optional credentials.
4. [x] Convert declared file/TOML/schema failures into one payload-safe
   `email_config_invalid` event and disable the adapter.
5. [x] Preserve silent normal behavior only when the file is absent.
6. [x] Preserve propagation of undeclared implementation failures.
7. [x] Run focused/full tests, type checking, and formatting checks.
8. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing SMTP send, TLS, login, or retry mechanics.
- Moving email configuration into the main YAML config.
- Logging email addresses, credentials, or raw TOML content.
- Retrying configuration reads after adapter construction.

## Completion Evidence

- Missing `private/email.toml` produces no config-invalid event.
- A valid config preserves current dry-run and SMTP behavior.
- Syntax, IO, section, required-field, port, TLS, and credential-pair failures
  produce one `outbox/email_config_invalid` event without raw values.
- Delivery remains disabled and continues to return `False` after invalid
  config, with the existing `email_no_config` delivery event.
- Undeclared exceptions are not swallowed.
- Focused email/observability tests, full pytest, Pyright, and
  `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit outbox timestamp cleanup and delivery state transitions for silent
per-record parse failures.
