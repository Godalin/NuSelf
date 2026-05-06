# NuSelf

[English README](README.md)

NuSelf 是一个本地 AI 镜像项目。它的目标是逐步成长为一个带有私人记忆、可恢复会话、轻量思想分身、主动反思和受控通知能力的个人智能体。

当前实现仍是早期的 CLI 优先骨架：

- 本地 `nuself` 命令。
- 可选的本地后台守护进程，通过 Unix socket 通信。
- 一个临时的带记忆聊天 agent，可以用 one-shot 模式运行，也可以通过守护进程运行。
- 基于文件的记忆条目，可列出、查看、新增、编辑、删除、搜索和重建索引。
- 持久化聊天线程，并能压缩较早的对话上下文。

LangGraph/LangChain 集成、主动反思、邮件和 macOS 通知目前是规划内容，还没有实现。

## 项目 TODOs

这是项目面向用户的进度面板。它汇总了 [docs/development-plan.md](docs/development-plan.md)、[docs/architecture.md](docs/architecture.md)、[docs/agent-framework.md](docs/agent-framework.md)、[docs/interaction-layer.md](docs/interaction-layer.md) 和 [docs/memory-management.md](docs/memory-management.md) 中的详细规划。完成功能或改变开发规划时，要同步更新本节、实现代码和相关规划文档。

### 项目基础

- [x] 创建标准 `uv` Python 项目和 typed package 布局。
- [x] 将 `uv run pytest` 和 `uvx pyright` 作为基础验证命令。
- [x] 将真实个人数据放在被忽略的根目录 `private/`。
- [x] 提交安全的样例私人记忆目录 `examples/private/`。
- [x] 用户可见变更同步维护英文和中文 README。

### CLI 与守护进程

- [x] 添加 `nuself` CLI 入口。
- [x] 添加 daemon 生命周期命令：`start`、`stop`、`status`、`list`、`logs`。
- [x] 添加 Unix socket JSONL daemon 协议。
- [x] 添加 `chat`、`attach` 和 daemon-backed attach 流程。
- [x] 让根命令 `nuself` 成为便捷的 daemon-backed chat 入口。
- [x] 添加交互模式，支持 `:q`、`:memory`、指令帮助和 readline 历史。
- [ ] 添加命名 thread 创建、分支、重命名和归档。
- [ ] 添加可以打开已有 thread 或创建新 thread 的 deep link。

### 记忆系统

- [x] 在 `private/memory/entries/` 下添加 file-backed memory entries。
- [x] 添加 `memory list`、`show`、`add`、`edit`、`delete`、`search`、`preview`、`reindex`。
- [x] 添加共享默认 working memory：`private/threads/default.json`。
- [x] 用锁串行化共享 working-memory 写入。
- [x] 添加长对话上下文压缩。
- [x] 添加确定性的 `MemoryQueryService` 用于相关记忆检索。
- [x] 添加后台 Memory Curator Agent，用于从对话更新长期记忆。
- [x] 收紧 curator 写入策略：忽略闲聊、优先更新重复项、拒绝原始对话流水账。
- [x] 添加手动 `memory update`。
- [x] 添加低频 Memory Optimizer Agent，用于批量清理、合并和删除重复长期记忆。
- [x] 添加手动 `memory optimize`。
- [ ] 添加 memory candidate review queue：list、show、accept、edit、merge、reject。
- [ ] 添加派生向量、hybrid 和 graph 索引。
- [ ] 添加 memory stats 和更丰富的 query 命令。
- [ ] 为 memory entries 添加 source-linked evidence records。

### 导入与知识库

- [ ] 添加 Markdown 和纯文本本地 source ingestion。
- [ ] 添加 source metadata 解析：title、path、date、tags、origin、privacy。
- [ ] 添加保留 source references 的 chunking。
- [ ] 添加 source documents、chunks、profile items 和 candidates 的 repositories。
- [ ] 让 `memory reindex` 从权威来源重建所有派生 artifacts。

### Agent Runtime

- [x] 添加临时 memory-aware chat agent，使用 OpenAI-compatible `/chat/completions`。
- [x] 添加被忽略的 `.env` 配置和提交的 `examples/.env`。
- [x] 未配置 API key 时保持确定性的 fallback 行为。
- [ ] 用 LangGraph conversation graph 替换临时 runtime。
- [ ] 添加结构化 response schema：answer text、evidence references、confidence、epistemic status。
- [ ] 添加 personal claims 的 unsupported-claim guard。
- [ ] 为 conversation agent 添加 tool-based memory search。

### 轻量多智能体分身

- [ ] 添加 LangGraph persona subgraph。
- [ ] 添加有界 personas：analyst、skeptic、builder、historian、care、synthesizer。
- [ ] 按请求只路由相关 personas。
- [ ] 让 synthesizer 成为唯一面向用户的声音。
- [ ] 将 persona instructions 和 corrections 保存为 procedural memory。

### 主动反思与通知

- [ ] 添加低频 daemon reflection scheduler，支持 cooldowns 和 quiet hours。
- [ ] 从近期 threads、memory 和 sources 中生成 idea candidates。
- [ ] 添加 relevance gate：novelty、confidence、urgency、cooldown、interruption cost。
- [ ] 添加 notification outbox，包含 idempotency keys 和 delivery state。
- [ ] 添加 log-only notification adapter。
- [ ] 添加 macOS notification adapter。
- [ ] 添加使用 ignored private configuration 的 email adapter。
- [ ] 将通知链接到新的或已有的 conversation。

### 评估与质量

- [ ] 添加 golden conversation fixtures。
- [ ] 添加本地 evaluation command。
- [ ] 评分 citation coverage、unsupported personal claims、uncertainty behavior 和 style fidelity。
- [ ] 添加 proactive-notification evaluation cases。

## 环境要求

- Python 3.12 或更新版本。
- `uv`。

## 安装和运行

在项目根目录执行：

```bash
uv run nuself --help
```

运行测试：

```bash
uv run pytest
uvx pyright
```

## LLM 配置

NuSelf 从根目录下被忽略的私有文件读取模型配置：

```text
.env
```

可以从仓库中的样例开始：

```bash
cp examples/.env .env
```

然后填写：

```text
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

当前客户端使用 OpenAI-compatible `/chat/completions` API。如果 `OPENAI_API_KEY` 为空，聊天会使用确定性的本地 fallback：它仍会保存线程，但不会进行真实模型推理。

## 私人目录

真实个人数据放在被 Git 忽略的根目录：

```text
private/
```

这个目录不会被提交到 Git。它用于存放本地 profile 笔记、记忆条目、聊天线程、运行时文件、守护进程日志、派生索引，以及未来的私人配置。

仓库中包含一个安全的公开样例目录：

```text
examples/private/
```

样例目录用于文档、测试和演示。不要把真实个人记忆放到这里。

## 聊天

没有守护进程时，可以使用 one-shot 聊天：

```bash
uv run nuself chat
uv run nuself chat --message "hello"
```

最短的 daemon-backed 入口是根命令。它会连接当前守护进程；如果没有正在运行的守护进程，会创建一个新进程，然后连接：

```bash
uv run nuself
uv run nuself --message "hello"
```

如果守护进程正在运行，`chat` 会把消息发送给守护进程：

```bash
uv run nuself daemon start
uv run nuself chat --message "hello from daemon"
uv run nuself daemon stop
```

要求必须连接已有守护进程：

```bash
uv run nuself chat --require-daemon --message "hello"
```

连接到已有守护进程会话：

```bash
uv run nuself attach
uv run nuself attach --message "continue"
uv run nuself daemon attach
uv run nuself daemon attach --message "continue"
```

不带 `--message` 时，`chat` 和 `attach` 会进入交互模式。终端支持时，行编辑和上下键历史由 `private/runtime/interactive_history` 支持。以 `:` 开头的输入会被识别为交互指令。输入 `:memory` 或 `:mem` 可以预览当前记忆条目。输入 `:q`、`:quit`、`:exit` 或发送 EOF 可以退出；未知指令会打印交互帮助并继续会话。

当前聊天使用一个临时 agent。它会检索 `private/memory/entries/` 中的记忆条目，把对话轮次追加到 `private/threads/default.json`，并在对话增长后把较早上下文压缩成线程摘要。当前记忆检索是确定性的词法检索，并带有排序原因；向量索引和图索引会作为后续派生检索层加入。

`private/threads/default.json` 是当前 NuSelf mind 的共享 working memory。多个终端连接同一个 daemon 时会共享它。thread store 会用锁串行化写入，避免并发对话互相覆盖。

上下文压缩可在 `.env` 中调整：

```text
NUSELF_CONTEXT_RECENT_MESSAGES=12
NUSELF_CONTEXT_SUMMARY_TRIGGER_MESSAGES=18
NUSELF_CONTEXT_SUMMARY_TARGET_CHARS=2400
NUSELF_MEMORY_CURATOR_INTERVAL_SECONDS=300
```

memory curator 会在 daemon 后台定时运行，也会在交互式聊天退出时运行。它会用 agent 判断新的 working-memory 对话应该新增、修改还是忽略长期记忆。无意义闲聊会被忽略，已有相似记忆会优先更新而不是重复创建，原始对话流水账会被拒绝写入。另有一个 memory optimizer 可以手动、低频运行，用来整合已经存在的杂乱条目。更新事件会写入 `private/logs/memory.log`。

真实的 mirror graph 后续会替换这部分临时 runtime。

## 守护进程

启动、检查和停止本地守护进程：

```bash
uv run nuself daemon start
uv run nuself daemon status
uv run nuself daemon list
uv run nuself daemon logs
uv run nuself daemon attach --message "continue"
uv run nuself daemon stop
```

不带子命令时，`daemon` 会显示守护进程子命令帮助。

守护进程运行时文件存放在：

```text
private/runtime/
private/logs/
```

第一版协议是 JSON lines，通过 Unix domain socket 通信，socket 路径是 `private/runtime/nuself.sock`。

## 记忆条目

记忆以清晰条目的形式管理，存放在：

```text
private/memory/entries/
```

新增条目：

```bash
uv run nuself memory add \
  --type belief \
  --title "Clarity matters" \
  --body "Prefer explicit assumptions and source-aware reasoning." \
  --tag style
```

列出条目：

```bash
uv run nuself memory list
```

预览近期记忆条目：

```bash
uv run nuself memory preview
uv run nuself memory preview --limit 20
```

查看单个条目：

```bash
uv run nuself memory show <entry-id>
```

编辑条目：

```bash
uv run nuself memory edit <entry-id> \
  --title "Clarity matters most" \
  --body "Prefer explicit assumptions, concrete evidence, and source-aware reasoning."
```

搜索条目：

```bash
uv run nuself memory search "clarity"
```

立即运行 memory curator：

```bash
uv run nuself memory update
```

整合已经存在的记忆条目：

```bash
uv run nuself memory optimize
uv run nuself memory optimize --limit 100
```

删除条目：

```bash
uv run nuself memory delete <entry-id>
```

重建派生记忆索引：

```bash
uv run nuself memory reindex
```

派生索引会写入：

```text
private/derived/memory_index.json
```

## 记忆条目类型

支持的条目类型：

- `source_note`
- `profile_fact`
- `belief`
- `style_trait`
- `episode`
- `open_question`
- `instruction`

## 项目文档

- [架构](docs/architecture.md)
- [开发计划](docs/development-plan.md)
- [Agent 框架计划](docs/agent-framework.md)
- [交互层计划](docs/interaction-layer.md)
- [Agent 指令](AGENTS.md)

## 开发政策

NuSelf 处于早期快速开发阶段。接口预计会快速变化。除非当前文档明确要求兼容，否则不要保留过时的 CLI 命令、协议字段、数据 schema 或 Python API。

功能、命令、配置、运行方式或用户可见行为发生变化时，必须同步更新 [README.md](README.md) 和 [README.zh-CN.md](README.zh-CN.md)。
