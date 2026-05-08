# NuSelf

[English README](README.md)

NuSelf 是一个本地 AI 镜像项目。它的目标是逐步成长为一个带有私人记忆、可恢复会话、轻量思想分身、主动反思和受控通知能力的个人智能体。

当前实现仍是早期的 CLI 优先系统：

- 本地 `nuself` 命令。
- 可选的本地后台守护进程，通过 Unix socket 通信。
- 一个基于 LangGraph 的带记忆聊天 agent，可以用 one-shot 模式运行，也可以通过守护进程运行。
- 基于文件的记忆条目和 profile items，可列出、查看、新增、编辑、删除、搜索和重建索引。
- 在 ignored `private/sources/` 下支持 Markdown 和纯文本 source ingestion，并可从导入的 chunks 提取可审阅候选项。
- 持久化聊天线程，并能压缩较早的对话上下文。

LangGraph 现在已经支撑 conversation runtime，而且一个受 gate 控制的内部 persona skeleton 已经可以在显式或高深度 turns 上运行。persona subgraphs、主动反思、邮件和 macOS 通知仍是后续规划。

## 项目 TODOs

这是项目面向用户的进度面板。它汇总了 [docs/development-plan.md](docs/development-plan.md)、[docs/architecture.md](docs/architecture.md)、[docs/agent-framework.md](docs/agent-framework.md)、[docs/interaction-layer.md](docs/interaction-layer.md) 和 [docs/memory-management.md](docs/memory-management.md) 中的详细规划。完成功能或改变开发规划时，要同步更新本节、实现代码和相关规划文档。

短期实现焦点放在 [docs/current-goal.md](docs/current-goal.md)。先用它作为当前开发目标，再从下面更大的 backlog 中拉取任务。

### 当前目标

- [x] 完成 REPL 形态 TUI、结构化日志和记忆 inspect 优化。
- [x] 添加 persona activation gate，用于显式请求和高深度讨论线索。
- [x] 将最小 persona skeleton 内部接入 conversation runtime。
- [x] 保持 persona contributions 为内部信息，同时保留 chat、CLI 和 daemon payloads 不变。
- [x] 为已激活 turns 在 REPL 中展示紧凑 persona activity summaries。
- [x] 为 `analyst_self`、`skeptic_self` 和 `builder_self` 添加确定性路由。
- [x] 再增加一个有界 persona（`historian_self`），并补上混合意图优先级规则。
- [x] 增加 `care_self`，并优化显式多视角路由策略。
- [ ] 增加内部 `synthesizer_self`，用于融合 persona contributions。

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
- [x] 添加 REPL 形态的终端交互层，用于显示状态、紧凑活动事件、日志和更清晰的聊天会话。
- [x] 添加只读 REPL 记忆 inspect 命令，用于查看 entries、candidates、profile items 和 sources。
- [x] 添加适合终端阅读的记忆列表和详情渲染器。
- [x] 添加结构化本地日志文件和通用 `nuself logs` 查看器。
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
- [x] 在聊天轮次后运行 memory curation，让对话成为主要记忆来源。
- [x] 让 memory curation 按讨论深度和持久信号触发，而不是按固定轮次数。
- [x] 收紧 curator 写入策略：忽略闲聊、优先更新重复项、拒绝原始对话流水账。
- [x] 添加手动 `memory update`。
- [x] 添加低频 Memory Optimizer Agent，用于批量清理、合并和删除重复长期记忆。
- [x] 添加手动 `memory optimize`。
- [x] 让手动 `memory add` 通过 memory intake agent 推断 type 和 title。
- [x] 添加 memory candidate review queue：list、show、accept、edit、merge、reject。
- [x] 为 entries 和 candidates 添加现实世界时间字段。
- [x] 让 curator 和 optimizer 的 proposals 进入 memory candidate review queue。
- [x] 为 memory entries 添加 source-linked evidence records。
- [x] 添加开放的 `MemoryObject + MemoryTypeDescriptor` registry，用于 typed memory 行为。
- [x] 添加 preference、belief、episode 和 instruction memory 的内置 descriptors。
- [x] 添加 goal 和 concept memory 的内置 descriptors。
- [x] 为 memory query tools 添加 descriptor-aware retrieval heuristics 和 type/tag filters。
- [x] 基于现有 memory links 添加第一版 relation-aware retrieval expansion。
- [x] 添加从现有 memory links 派生、可重建的 relation index。
- [x] 添加用于内置关系行为的 `RelationDescriptor` registry。
- [x] 添加覆盖 memory entries 和 relation edges 的可重建 symbolic graph projection。
- [x] 为 transitive symbolic relations 添加 transitive-closure retrieval expansion。
- [ ] 添加派生向量、hybrid 和 graph 索引。
- [x] 添加开放 symbolic graph，并用 `RelationDescriptor` 描述支持、矛盾、细化和依赖关系。
- [x] 让检索扩展尊重每个关系的 `retrieval_rule`（例如同时包含当前和被取代的 vs. 仅直接邻居）。
- [x] 添加基于描述符元数据的图遍历命令（多跳搜索）。
- [x] 为 `transitive=True` 的关系描述符添加传递闭包遍历。
- [x] 添加特定记忆节点之间的路径查找命令。
- [x] 将传递闭包接入 `MemoryQueryService` 的自动上下文扩展。
- [x] 将临时运行时替换为 LangGraph 对话图。
- [x] 添加 memory stats 和更丰富的 query 命令。

### 导入与知识库

- [x] 添加 Markdown 和纯文本本地 source ingestion。
- [x] 添加 source metadata 解析：title、path、date、tags、origin、privacy。
- [x] 添加保留 source references 的 chunking。
- [x] 添加 source documents 和 chunks 的 repositories。
- [x] 添加面向 imported document chunks 的确定性 source search。
- [x] 让 `memory reindex` 重建 source-derived chunk artifacts。
- [x] 添加 profile items 的 repositories。
- [x] 让 `memory reindex` 从权威来源重建所有派生 artifacts。

### Agent Runtime

- [x] 添加临时 memory-aware chat agent，使用 OpenAI-compatible `/chat/completions`。
- [x] 添加被忽略的 `.env` 配置和提交的 `examples/.env`。
- [x] 未配置 API key 时保持确定性的 fallback 行为。
- [x] 添加用于 LangGraph 迁移的最小 conversation runtime boundary。
- [x] 添加 typed conversation runtime state 和 node contracts。
- [x] 用 LangGraph conversation graph 替换临时 runtime。
- [x] 隔离 LangGraph driver boundary，并在 graph failures 时保留 thread state。
- [x] 添加 graph runtime diagnostics，用于 node execution 和 failures。
- [x] 将 conversation tool handling 拆成 graph-native routes。
- [x] 强化 graph-native tool extension boundary。
- [x] 收尾 LangGraph runtime migration slice。
- [x] 添加结构化 response schema：answer text、evidence references、confidence、epistemic status。
- [x] 添加 personal claims 的 unsupported-claim guard。
- [x] 为 conversation agent 添加 tool-based memory search。
- [x] 让 conversation retrieval 基于现有 memory links 支持 relation-aware 检索。

### 轻量多智能体分身

- [ ] 添加 LangGraph persona subgraph。
- [x] 添加最小内部 persona skeleton，且不改变 chat payloads。
- [x] 将最小 persona skeleton 内部接入 conversation runtime。
- [x] 添加 persona activation gate，用于显式请求和高深度讨论线索。
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

不带 `--message` 时，`chat` 和 `attach` 会进入交互模式。终端支持时，行编辑和上下键历史由 `private/runtime/interactive_history` 支持。以 `:` 开头的输入会被识别为交互指令。输入 `:status` 可以查看 daemon/thread 状态，输入 `:logs` 可以查看最近 activity events，输入 `:memory` 或 `:mem` 可以预览当前记忆条目。只读记忆 inspect 快捷命令包括 `:mem search <query>`、`:mem show <entry-id>`、`:mem candidates`、`:mem candidate <candidate-id>`、`:mem profile <query>`、`:mem sources` 和 `:mem source <source-id>`。输入 `:q`、`:quit`、`:exit` 或发送 EOF 可以退出；未知指令会打印交互帮助并继续会话。

当前聊天使用一个基于 LangGraph 的 conversation runtime。它会检索 memory entries、derived profile items 和 imported source chunks，把对话轮次追加到 `private/threads/default.json`，并在对话增长后把较早上下文压缩成线程摘要。当前记忆检索是确定性的词法检索，带有 descriptor-aware 类型提示、type/tag filters、基于现有 memory links 的 relation expansion 和排序原因；向量索引和图索引会作为后续派生检索层加入。

`private/threads/default.json` 是当前 NuSelf mind 的共享 working memory。多个终端连接同一个 daemon 时会共享它。thread store 会用锁串行化写入，避免并发对话互相覆盖。

上下文压缩可在 `.env` 中调整：

```text
NUSELF_CONTEXT_RECENT_MESSAGES=12
NUSELF_CONTEXT_SUMMARY_TRIGGER_MESSAGES=18
NUSELF_CONTEXT_SUMMARY_TARGET_CHARS=2400
NUSELF_MEMORY_CURATOR_INTERVAL_SECONDS=300
```

memory curator 会在 daemon 后台定时运行，也会在交互式聊天退出时运行。它会用 agent 判断新的 working-memory 对话应该新增、修改还是忽略长期记忆。无意义闲聊会被忽略，已有相似记忆会优先更新而不是重复创建，原始对话流水账会被拒绝写入。另有一个 memory optimizer 可以手动、低频运行，用来整合已经存在的杂乱条目。更新事件会写入 `private/logs/memory.log`，交互式聊天也会用紧凑 activity lines 显示新的 chat、daemon 和 memory 事件。

当前 conversation graph 有意保持较小：它保留 CLI 和 daemon protocol 边界，同时为后续 persona subgraphs 和更丰富的 agent routing 留出空间。

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

也可以用通用日志查看器检查结构化本地日志：

```bash
uv run nuself logs
uv run nuself logs --component chat --tail 20
uv run nuself logs --component memory --json
```

不带子命令时，`daemon` 会显示守护进程子命令帮助。

守护进程运行时文件存放在：

```text
private/runtime/
private/logs/
```

第一版协议是 JSON lines，通过 Unix domain socket 通信，socket 路径是 `private/runtime/nuself.sock`。

## 记忆条目

新记忆的主要来源是聊天。每轮聊天后，NuSelf 会运行 Memory Curator Agent；如果长期记忆被创建或更新，会打印 `[memory] ...` 摘要。
Curator 会根据讨论深度、质量和持久信号判断是否写入，而不是按固定聊天轮次数触发。

手动记忆命令仍作为维护工具保留。记忆以清晰条目的形式存放在：

```text
private/memory/entries/
```

新增条目：

```bash
uv run nuself memory add \
  --body "Prefer explicit assumptions and source-aware reasoning." \
  --tag style
```

`memory add` 默认会推断 memory type 和 title。只有需要显式维护 override 时，才使用 `--type` 或 `--title`。

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

查看派生 memory relations：

```bash
uv run nuself memory relations
uv run nuself memory relations --relation supersedes
uv run nuself memory relations --source-id <entry-id>
uv run nuself memory relations --target-id <entry-id>
```

查看派生 symbolic graph：

```bash
uv run nuself memory graph nodes
uv run nuself memory graph nodes --type belief
uv run nuself memory graph edges
uv run nuself memory graph edges --relation related_to
uv run nuself memory graph edges --source-id <entry-id>
uv run nuself memory graph edges --target-id <entry-id>
uv run nuself memory graph search "graph retrieval"
uv run nuself memory graph search "graph retrieval" --type concept --limit 5
```

派生 memory、relation 和 symbolic graph artifacts 会写入：

```text
private/derived/memory_index.json
private/derived/relation_index.json
private/derived/symbolic_graph.json
```

## Source Documents

将 Markdown 或纯文本 source material 导入 ignored 本地存储：

```bash
uv run nuself memory source ingest private/sources/my-note.md --tag notes
uv run nuself memory source ingest private/sources/ --tag archive
```

导入后的 document metadata 存储在 `private/sources/documents/`，稳定 chunks 存储在 `private/sources/chunks/`。

查看已导入 sources：

```bash
uv run nuself memory source list
uv run nuself memory source show <source-id>
uv run nuself memory source chunks <source-id>
uv run nuself memory source search "durable citation"
```

从已导入的 source 中提取可审阅的 profile candidates：

```bash
uv run nuself memory source extract <source-id>
```

这一步会把 `profile_fact` 候选项放入 review queue，并保留结构化 source evidence。已接受的 profile candidates 会存放在 `private/profile/items/`，可以用下面的命令查看：

```bash
uv run nuself memory profile list
uv run nuself memory profile search "concise"
uv run nuself memory profile show <profile-id>
```

Profile search 支持 `--type`、`--tag`、`--observed-from`、`--observed-to` 和 `--valid-on` 这些确定性过滤条件。

支持的 front matter 字段是 `title`、`date`、`tags`、`origin` 和 `privacy`。Source chunk references 使用 `source:<source-id>:<chunk-index>` 格式。

`memory reindex` 会从权威 memory、source 和 profile records 重建 `private/derived/memory_index.json`、`private/derived/relation_index.json`、`private/derived/source_index.json` 与 `private/derived/profile_index.json`。

删除一个导入的 source 以及它派生出的 review artifacts：

```bash
uv run nuself memory source delete <source-id>
```

直接删除一个 derived profile item：

```bash
uv run nuself memory profile delete <profile-id>
```

## 记忆条目类型

支持的条目类型：

- `source_note`
- `profile_fact`
- `belief`
- `preference`
- `goal`
- `concept`
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
