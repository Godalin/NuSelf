# Hardcoded Constants

All non-configurable numeric constants, thresholds, and caps that affect
behavior, grouped by subsystem. Configurable defaults live in
[`config.md`](config.md) and `src/nuself/config.py`.

## Reason

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `_MAX_EVIDENCE_REFS` | `reason/service.py:19` | 20 | Max evidence refs kept on a reasoning thread |
| `_merge_str_lists max_items` | `reason/service.py:33` | 10 | Max items in merged evidence/tracked-item lists |
| `segment_size` | `reason/output.py:331,436` | 5 | Default step window for export composition |
| per-mode window | `reason/output.py:851-858` | 12/6/8/8 | Section window for summary/outline/report/narrative modes |
| `timeout=120` | `reason/output.py:675` | 120 s | PDF subprocess timeout |
| `interval_seconds` | `reason/scheduler.py:27` | 600 s | Reason scheduler poll interval |

## Reflection

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `SIMILARITY_THRESHOLD` | `reflection/organizer.py:12` | 0.48 | Jaccard threshold for merging pending reflections |
| snippet truncation | `reflection/organizer.py:90` | 180 | Max chars in merge body note |
| `max_candidates` | `reflection/scheduler.py:673` | 3 | Max idea candidates per generation call |
| `max_threads` | `reflection/scheduler.py:834` | 5 | Recent reason threads loaded for context |
| `max_messages` | `reflection/scheduler.py:834` | 10 | Recent messages per thread for context |
| `max_entries` | `reflection/scheduler.py:846` | 8 | Recent memory entries for context |
| `max_items` | `reflection/scheduler.py:855` | 10 | Profile items for context |
| `max_sources` | `reflection/scheduler.py:865` | 5 | Recent source docs for context |

## Memory

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `DEFAULT_MEMORY_LIMIT` | `memory/query.py:14` | 8 | Default memory search result limit |
| scoring weights | `memory/query.py:201-236` | various | Title/body/tag/confidence/importance boost values |
| `min_quality_chars` | `memory/curator.py:28` | 120 | Minimum body chars for memory curation |
| `existing_memory_limit` | `memory/curator.py:29` | 12 | Existing entries loaded for dedup context |
| `memory_limit` | `memory/optimizer.py:25` | 50 | Batch size for memory optimization |
| `DEFAULT_CHUNK_TARGET_CHARS` | `memory/source_repository.py:17` | 1200 | Target chunk size for source ingestion |
| `DEFAULT_SOURCE_SEARCH_LIMIT` | `memory/source_repository.py:18` | 8 | Default source search limit |
| `limit=8, depth=1` | `memory/repository.py:305-306` | 8, 1 | Default graph search limit and depth |

## Persona

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| name max length | `persona/tools.py:33,234` | 40 | Max persona name chars (both global and thread-scoped) |

## Trace

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `_short limit` | `trace/service.py:315` | 80 | Display truncation for trace values |

## Daemon

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `MAX_ATTEMPTS` | `daemon/server.py:338` | 5 | Max export job composition retries |
| `BASE_BACKOFF` | `daemon/server.py:339` | 10 s | Export retry base backoff |
| `MAX_BACKOFF` | `daemon/server.py:340` | 600 s | Export retry max backoff |
| `timeout=1.0` | `daemon/server.py:393` | 1 s | Export queue poll timeout |
| poll iterations | `daemon/lifecycle.py:56,71` | 40 | Max startup/shutdown poll loops |
| poll interval | `daemon/lifecycle.py:57,72` | 0.05 s | Startup/shutdown poll sleep |
| `timeout=2.0` | `daemon/client.py:21` | 2 s | Daemon socket connection timeout |

## Notification

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| retention days | `notification/__init__.py:263` | 7 | Dismissed outbox entries cleaned after 7 days |
| `timeout=30` | `notification/email.py:81` | 30 s | SMTP connection timeout |

## CLI

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `CHAT_REQUEST_TIMEOUT_SECONDS` | `cli/__init__.py:116` | 120 s | Interactive chat request timeout |
| `DEFAULT_MEMORY_PREVIEW_LIMIT` | `cli/__init__.py:117` | 8 | Memory preview entry count |
| `INTERACTIVE_CHAT_ATTEMPTS` | `cli/__init__.py:118` | 2 | Max interactive chat retries |
| `INTERACTIVE_LOG_POLL_INTERVAL_SECONDS` | `cli/__init__.py:119` | 0.1 s | Log poll interval |
| profile display | `cli/repl/commands.py:467` | 6 | Max profile items shown inline |

## LLM

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `timeout_seconds` | `llm.py:64` | 60 s | Default LLM endpoint timeout |
| `max_retries: 0` | `llm.py:246` | 0 | LangChain model retries (NuSelf handles retries) |
| `temperature: 0.1` | `llm.py:248` | 0.1 | Structured output temperature |
| error truncation | `llm.py:299` | 500 | LLM error message truncation |

## Store / Workspace

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `limit=10, offset=0` | `store.py:228` | 10 | Default workspace entry listing limit |
| `limit=100, offset=0` | `store.py:242` | 100 | Default namespace listing limit |

## Agent

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `limit: int = 8` | `agent/tools.py:42` | 8 | Default memory search limit in agent tools |
| `limit: int = 5` | `agent/tools.py:74,375,417` | 5 | Default reflection/trace list limits |
| `range(2)` | `agent/chat/response.py:91` | 2 | LLM endpoint retry attempts |
| `[:3]` | `agent/chat/persona.py:209` | 3 | Max default fallback personas |
| note/summary truncation | `agent/chat/persona.py:309,313` | 140 | Persona contribution display truncation |

## Render / TUI

| Constant | File:Line | Value | Effect |
|----------|-----------|-------|--------|
| `_DEFAULT_TEXT_WIDTH` | `tui/persona.py:12` | 88 | Fallback terminal width for persona rendering |
| `DEFAULT_TEXT_WIDTH` | `tui/memory.py:15` | 88 | Fallback terminal width for memory rendering |
| `_TOOL_CALL_INDENT` | `tui/reason.py:19` | 2 | Tool call indentation |
| tag padding | `tui/render.py:791` | 18 | Trace tag label padding |

## Design Notes

- **Config candidates**: Constants with `default=` in `config.py` are already
  user-configurable. The rest are candidates for promotion when a user need
  arises.
- **Internal vs external**: Truncation limits (120, 140, 180 chars) and
  scoring weights are considered internal; behavioural caps (max retries,
  batch sizes, poll intervals) may deserve config promotion.
- **Hardcoded caps removed**:
  - `MAX_ACTIVE_THREADS = 5` (`reason/service.py`) — removed in v0.2.2
  - Agent-side thread cap (`agent/tools.py`) — removed in v0.2.2
