# NuSelf

[English README](README.md)

NuSelf 是一个面向深度个人讨论的 local-first AI 镜像。它把可恢复的对话、私人记忆、长期推理、主动反思和受控通知放在用户自有 authority 或显式选择的隔离工作区中。

NuSelf 以 CLI 为主要入口，适合希望检查并掌控 Agent 数据，而不是把数据隐藏在托管账号背后的用户。

## 当前状态

当前稳定版本是 **v0.3.1**，支持适合安装使用的用户级存储和显式隔离工作区。

NuSelf 仍在激进开发中。v0.3 系列建立了运行时、存储、Agent 和后台任务的基础；后续开发版本仍可能主动调整接口。

支持环境：

- Linux 和 macOS
- Python 3.12、3.13 或 3.14
- 使用 `uv` 管理的本地源码仓库

当前不支持 Windows，因为运行时协调依赖 POSIX 锁和 Unix-domain socket。

## 主要能力

- 具有记忆上下文的一次性和 daemon-backed 对话，并支持交互批准持久记忆写入及只读本地/UTC 时间查询
- 持久、可恢复、可分支的对话线程
- 支持审核、搜索、关系和符号图视图的长期记忆
- 独立的 Markdown 与纯文本外部知识库
- 长期推理线程和可追踪的思考来源
- 通过独立 API 连接的会话历史、记忆观察与顶级反思控制
- 统一 Inbox，并通过独立的日志、邮件和 macOS 适配器投递完整反思正文
- 本地 SQLite authority、迁移工具和可移植 thought pack
- 瞬时重试及有序 OpenAI-compatible / Anthropic 端点切换
- 自动隐藏凭据的结构化诊断
- 可组合的类型化 Tool 副作用（审批、观察与审计）；单一有界 daemon 调度器支持可恢复的维护唤醒和资源 lane 串行化

## 快速开始

### 1. 安装

克隆仓库并创建锁定环境：

```bash
git clone https://github.com/Godalin/NuSelf.git
cd NuSelf
uv sync --locked
```

确认 CLI：

```bash
uv run nuself --version
uv run nuself --help
```

需要个人状态的命令必须先显式执行 `nuself init`。如果所选 authority
或模型配置尚未就绪，NuSelf 会打印明确的下一步命令并退出，不会启动 daemon
或停留在不可用的交互提示符中。临时聊天传输失败不会关闭已有 REPL；可以用
`:retry` 安全重试同一个逻辑 turn。

### 2. 配置模型

初始化默认用户 authority，并复制示例配置：

```bash
uv run nuself init
cp examples/.nuself/config.yaml ~/.nuself/config.yaml
```

OpenAI-compatible 端点可在 `~/.nuself/config.yaml` 中这样配置：

```yaml
llm:
  - base_url: https://api.openai.com/v1
    api_key: YOUR_API_KEY
    model: gpt-4.1-mini
    timeout_seconds: 60
```

Anthropic Messages 端点需要加入 `anthropic: true`。NuSelf 不会根据 URL 或模型名猜测协议；
运行时只接受当前配置 schema，启动前请显式迁移已经废弃的 v0.2.5 字段。

查看经过凭据脱敏的实际配置：

```bash
uv run nuself dev config
```

端点切换、聊天上下文、反思、daemon 和通知设置见[配置指南](docs/configuration.md)。

### 3. 开始对话

启动或连接本地 daemon-backed 交互会话：

```bash
uv run nuself
```

即使 daemon 仍在处理上一轮对话，新交互客户端也会立即启动，并读取最近一次
已提交的线程快照。
Ctrl-C 会先关闭进行中请求的传输再取消本轮；Ctrl-D 会依次完成对话记录、
记忆整理与存储清理后退出。

发送一条消息：

```bash
uv run nuself --message "帮我梳理当前最重要的事情。"
```

不要求 daemon，直接执行一次聊天：

```bash
uv run nuself chat --message "你了解这个项目的哪些内容？"
```

如果没有配置模型，NuSelf 会返回本地配置指引，不会伪装成已经生成了模型回复。

## 常用流程

### 恢复对话

```bash
uv run nuself conversation list
uv run nuself conversation open default
uv run nuself conversation branch default alternative
```

### 搜索与整理记忆

```bash
uv run nuself memory search "decision"
uv run nuself memory preview
uv run nuself memory update
```

### 导入个人笔记

```bash
uv run nuself source ingest ~/notes.md --tag notes
uv run nuself source list
```

### 延续长期问题

```bash
uv run nuself reason start "接下来最值得投入的方向是什么？"
uv run nuself reason list
uv run nuself reason advance <reason-id>
```

### 检查运行状态

```bash
uv run nuself daemon status
uv run nuself dev health
uv run nuself dev logs --component chat --tail 20
```

### 查看或编辑存储数据

```bash
uv run nuself data collections
uv run nuself data check memory
uv run nuself data list memory
uv run nuself data show memory <memory-id>
uv run nuself data edit memory <memory-id>
uv run nuself data export threads --format json
```

`data check` 会无修改地找出无效记录，并为每条记录给出准确的 `edit`
或需确认的 `delete` 命令。一次性旧格式迁移仅位于 `scripts/`，安装后的 CLI
不携带迁移逻辑。通用编辑会校验完整记录、显示 diff、要求确认，
并拒绝覆盖并发修改。内部运行状态默认隐藏，只有显式使用 `--internal`
才能查看。

Schema v5 将领域记录和 namespaced workspace 状态收进一个无冗余索引的紧致
authority 数据库。升级仍须显式执行且支持反向迁移，详见
[迁移规范](docs/spec/database-migrations.md)。

[CLI 指南](docs/cli.md)按工作流整理了命令；CLI 自身的 `--help` 是最新命令参考。

## 隐私与存储

个人状态默认位于 `~/.nuself`。`--local` 使用 `./.nuself`，`--workspace PATH` 使用 `PATH/.nuself`；每次选择都是隔离的状态 authority。工作区配置继承用户默认值，但数据库和运行状态绝不合并。每个 authority 严格只允许一个 NuSelf daemon 操作系统进程；一个有界调度器统一协调聊天和后台任务。

交互聊天会用简洁的 `Attention:` 区块提示关键状态：当前 authority
没有可用模型、本地工作区 authority 尚未被选择、持久化记录无法解码，
或 daemon 最近未能交付回复。可修复记录会指向 `data check`；已经持久化
但未交付的聊天回复可通过 `:history` 恢复，反复出现交付失败时会建议重启
daemon。成功修复记录后，对应的旧解码告警不再被当作当前问题显示。

local-first 不等于模型离线：配置远程模型后，一次调用所需的上下文会发送给你选择的端点。请根据自己的隐私要求选择提供方及其数据保留政策。

重要边界：

- 源码仓库不再是隐式数据根目录。
- 默认测试和 CI 不读取项目私人数据。
- 可选的真实 API 测试只发送固定合成提示。
- 配置诊断会隐藏凭据。
- 工具活动日志默认包含结构化参数和结果；显式精简的工具只记录操作与状态。
- thought pack 和 JSON export 是显式迁移工具；仍应独立备份所选 authority。

更多说明见[记忆指南](docs/memory.md)和[存储规范](docs/spec/storage-v2.md)。

## 当前限制

- NuSelf 仍是早期 CLI-first 系统，不是成熟的桌面应用。
- 模型质量和工具能力取决于提供方与具体模型。
- 后台记忆整理、反思和通知投递需要 daemon；聊天回复不会等待记忆整理完成。
- macOS 通知仅适用于对应平台；邮件需要显式 SMTP 配置。
- 当前不支持 Windows。
- 工作区必须显式选择；NuSelf 不会自动向父目录发现工作区。

## 文档

- [配置指南](docs/configuration.md)
- [CLI 指南](docs/cli.md)
- [记忆指南](docs/memory.md)
- [系统架构](docs/architecture.md)
- [行为规范索引](docs/spec/README.md)
- [测试说明](tests/README.md)
- [贡献指南](CONTRIBUTING.md)
- [更新记录](CHANGELOG.md)
- [当前开发目标](docs/current-goal.md)
- [待办事项](docs/TODOs.md)

行为契约属于 `docs/spec/`，已经完成的版本历史属于 `CHANGELOG.md`。README 会保持为简洁的项目入口。
