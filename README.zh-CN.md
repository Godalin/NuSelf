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
