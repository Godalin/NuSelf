# Configuration

NuSelf reads an optional user configuration:

```text
~/.nuself/config.yaml
```

Explicit workspace scope additionally reads `<workspace>/.nuself/config.yaml`.
Mappings recursively override the user configuration; sequences and scalars
replace lower-layer values. Runtime state still belongs to exactly one
authority and is never merged.

All fields are optional. When both files are absent, NuSelf uses safe defaults
and model-backed chat remains disabled until at least one endpoint has a
non-empty API key.

Start from the annotated example:

```bash
nuself init
cp examples/private/config.yaml ~/.nuself/config.yaml
```

Set `NUSELF_HOME` to an absolute path to replace the default user authority
root. Use `--local` or `--workspace PATH` to select workspace state explicitly.
Never put real secrets in `examples/private/`.

## Minimal Model Configuration

OpenAI-compatible endpoint:

```yaml
llm:
  - base_url: https://api.openai.com/v1
    api_key: YOUR_API_KEY
    model: gpt-4.1-mini
    timeout_seconds: 60
```

Anthropic Messages endpoint:

```yaml
llm:
  - anthropic: true
    base_url: https://api.anthropic.com
    api_key: YOUR_API_KEY
    model: claude-sonnet-4-5
    timeout_seconds: 60
```

The protocol is explicit. Set `anthropic: true` only when the selected
gateway and model use the Anthropic Messages protocol. NuSelf does not infer
protocol from a URL or model name.

Multiple entries form an ordered failover list:

```yaml
llm:
  - base_url: https://primary.example/v1
    api_key: PRIMARY_KEY
    model: primary-model
  - anthropic: true
    base_url: https://secondary.example
    api_key: SECONDARY_KEY
    model: secondary-model
```

## Chat Context

```yaml
chat:
  request_timeout_seconds: 120
  context:
    recent_messages: 12
    summary_trigger_messages: 18
    summary_target_chars: 2400
```

The request timeout controls how long a client waits for daemon-backed chat.
Context settings control when older turns are compressed.

## Background Tasks

```yaml
daemon:
  memory_curator:
    interval_seconds: 300
  reflection_scheduler:
    check_interval_seconds: 600
  notification_delivery:
    interval_seconds: 30
```

These intervals apply while the daemon is running. Restart the daemon after a
configuration change:

```bash
uv run nuself daemon restart
```

## Reflection

```yaml
reflection:
  scheduler:
    interval_seconds: 3600
    cooldown_seconds: 300
    quiet_start_hour: 22
    quiet_end_hour: 7
    daily_cap: 5
    jitter_percent: 20
  gate:
    relevance_threshold: 0.5
    persona_discussion_threshold: 0.7
  moderator:
    max_discussion_rounds: 10
    moderator_convergence_patience: 5
```

Quiet hours use local 24-hour time and may wrap across midnight.

## Notifications

macOS notifications:

```yaml
macos_notification:
  enabled: true
```

Email:

```yaml
email:
  enabled: true
  smtp:
    host: smtp.example.com
    port: 587
    use_tls: true
    username: YOUR_USERNAME
    password: YOUR_PASSWORD
  from_address: nuself@example.com
  to_address: you@example.com
```

Credentials remain in the private configuration file. Diagnostic output
redacts API keys and credential values.

## Inspect And Validate

Show effective configuration:

```bash
uv run nuself dev config
```

Run local health checks:

```bash
uv run nuself dev health
```

Inspect relevant structured logs:

```bash
uv run nuself dev logs --component chat --tail 20
uv run nuself dev logs --component daemon --tail 20
```

For editor validation, use
[`nuself-config.schema.json`](nuself-config.schema.json). The complete
annotated example is [`examples/private/config.yaml`](../examples/private/config.yaml).
The authoritative defaults and validation rules live in
[`spec/config.md`](spec/config.md); model protocol and failover behavior live
in [`spec/llm.md`](spec/llm.md).
