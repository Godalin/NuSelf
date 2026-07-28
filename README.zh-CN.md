# NuSelf

[English README](README.md)

NuSelf 是一个本地 AI 镜像项目。它的目标是逐步成长为一个带有私人记忆、可恢复会话、轻量思想分身、主动反思和受控通知能力的个人智能体。

当前实现仍是早期的 CLI 优先系统：

- 本地 `nuself` 命令。
- 可选的本地后台守护进程，通过 Unix socket 通信。
- 一个基于 LangGraph 的带记忆聊天 agent，支持 one-shot 和守护进程模式，可在对话中使用工具进行记忆搜索、反思检视、记忆整理、长线推理查询和 trace 溯源。
- 基于统一存储层的记忆条目和 profile items，可列出、查看、新增、编辑、删除和搜索。
- 在 ignored `private/sources/` 下支持 Markdown 和纯文本 source ingestion，并可从导入的 chunks 提取可审阅候选项。
- 基于统一存储层的 trace 记录和长线 reason 线程，用于保存可追溯的思考来源；已有 SQLite 数据库会被自动选用。
- 持久化聊天线程，并能压缩较早的对话上下文。

LangGraph 现已支撑 conversation runtime。聊天 agent 可在对话中调用工具搜索记忆、列出和搁置待讨论反思主题、归档过时记忆、调整重要性分数、查看活跃 reason 线程，并搜索 thought trace。内部 persona 系统对聊天和后台反思共用一套竞争式讨论流程，LLM 驱动的人格节点可生成独立观点。邮件和 macOS 通知在配置后可用。

审批门控工具在次要审计存储不可用时仍以用户提示和工具结果为准；
故障会通过结构化降级诊断记录，并在诊断日志也失败时退化为运行时警告。

进程内日志 observer 彼此隔离，也不会影响业务操作；如果 observer 和对应的
结构化故障记录同时失败，NuSelf 会发出最终运行时警告，不再静默丢失诊断。

Persona graph 的 LLM 故障会保留确定性的贡献、汇总和激活 fallback，同时记录
结构化降级信息；诊断存储不可用也不会中断 endpoint failover。

竞争式 persona discussion 对评分、参与者选择和 moderator 判断使用相同边界，
诊断归属调用项目，而不是隐式进程状态。

## 项目 TODOs

项目进度记录在 [`docs/TODOs.md`](docs/TODOs.md)。短期实现焦点在 [`docs/current-goal.md`](docs/current-goal.md)。

## 分支与版本策略

- `main` 是稳定、可发布的分支。
- `dev/v0.3.x` 是当前优化分支。
- `feature/*` 是隔离的实验性分支。
- `patch` 版本用于稳定化、重构和修复。
- `minor` 版本用于新增子系统或认知能力。
- `major` 版本用于架构成熟度里程碑。

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

## 配置

NuSelf 所有配置都集中在一个 YAML 文件中：

```text
private/config.yaml
```

配置优先级（从高到低）：
1. `private/config.yaml`
2. 代码中的硬编码默认值

### LLM 配置

```text
llm:
  - base_url: https://api.openai.com/v1
    api_key: ""        # 留空使用本地 fallback
    model: gpt-4.1-mini
    timeout_seconds: 60
  # 可选 Anthropic endpoint：
  # - anthropic: true
  #   api_key: ""
  #   model: claude-sonnet-4-5
```

### 聊天设置

```text
chat:
  request_timeout_seconds: 120
  context:
    recent_messages: 12
    summary_trigger_messages: 18
    summary_target_chars: 2400
```

### 守护进程间隔

```text
daemon:
  memory_curator:
    interval_seconds: 300
  reflection_scheduler:
    check_interval_seconds: 60
  notification_delivery:
    interval_seconds: 30
```

### 主动反思系统

```text
reflection:
  scheduler:
    interval_seconds: 3600
    cooldown_seconds: 300
    quiet_start_hour: 22
    quiet_end_hour: 7
    daily_cap: 5
    jitter_percent: 20
    max_pending_entries: 20
  gate:
    relevance_threshold: 0.5
    persona_discussion_threshold: 0.7
  moderator:
    max_discussion_rounds: 10
    moderator_convergence_patience: 5
```

参见 `examples/private/config.yaml` 了解完整带注解的示例和其他配置部分（email、macOS 通知、实验性功能）。

查看生效配置：

```bash
uv run nuself dev config
```

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

不带 `--message` 时，`chat` 和 `attach` 会进入交互模式。终端支持时，行编辑和上下键历史由 `private/runtime/interactive_history` 支持。动态补全和 history 持久化采用 best effort：存储失败会记录 degraded event，但不会阻止输入或接受已经输入的内容。会话状态栏会在启动时、每个完成的聊天轮次后，以及请求重绘 thread 或状态的命令后显示。以 `:` 开头的输入会被识别为交互指令。输入 `:dev status` 可以查看 daemon/thread 状态，输入 `:dev logs` 可以查看最近 activity events，输入 `:mem` 可以预览当前记忆条目。只读记忆 inspect 快捷命令包括 `:mem search <query>`、`:mem show <entry-id>`、`:mem review`、`:mem review <candidate-id>`、`:mem profile <query>`、`:mem sources` 和 `:mem source <source-id>`。输入 `:reason` 可查看长线推理线程，输入 `:trace` 可查看思维溯源记录，输入 `:inbox` 可查看反思和通知。输入 `:q`、`:quit`、`:exit` 或发送 EOF 可以退出；未知指令会打印交互帮助并继续会话。

如果 styled terminal input 因已声明的终端能力或 IO 故障不可用，NuSelf 会记录
`chat/interactive_prompt_failed` 并退回内置输入。EOF、键盘中断和未声明的 prompt
异常仍保持原本的控制流，不会被当作可降级故障吞掉。

非 LangChain 的本地模型可以返回普通文本或有效的 JSON/fenced-JSON response
envelope。看起来属于内部协议的输出会被严格解码；损坏的协议 JSON 和非法 response
字段不会再作为原始答案显示。

当前聊天使用一个基于 LangGraph 的 conversation runtime。它会检索 memory entries、derived profile items 和 imported source chunks，把对话轮次追加到 `private/threads/default.json`，并在对话增长后把较早上下文压缩成线程摘要。Agent 还可以在对话中调用工具：`search_memory` 进行定向检索，`list_pending_reflections` / `dismiss_reflection` 检视和管理主动想法，`archive_memory` / `update_memory_importance` 整理长期记忆，`list_active_reasoning_threads` / `show_reasoning_thread` 查看长期 reason 状态，`search_trace` / `show_trace` 查看 thought provenance。当前记忆检索是确定性的词法检索，带有 descriptor-aware 类型提示、type/tag filters、基于现有 memory links 的 relation expansion 和排序原因；向量索引和图索引会作为后续派生检索层加入。

Chat 生命周期统一发布为已注册的 `turn.started`、`turn.completed`、
`turn.failed` 和 `turn.reused` event。只有 thread update 持久化成功后才会发布
completed event。结构化 audit 和 daemon live activity projection 保留相同的
event identity 与 correlation；subscriber 失败不会替换成功 reply，也不会遮蔽
原始 chat failure。

Daemon-backed、one-shot 和交互重试 client operation 统一使用一个
`source="client"` runtime scope。它们的 transport、retry、completion 和
post-turn curation log 会共享 thread/turn correlation，保留调用方已有的
request/job/trace identity，并在结束后恢复调用方 context。

thread-scoped dynamic persona prompt 文件是权威数据；其派生 name index 会在缺失、损坏或陈旧时被校验并原子重建，因此损坏的 lookup metadata 不会隐藏健康 persona，改名后也不会残留旧名称。

reflection relevance 和 candidate generation 使用严格的 typed response schema。malformed batch、字符串布尔值和未知 candidate type 会进入既有安全 fallback，而不会被强制转换或部分接受。

persona activation 和 competitive discussion 同样遵循严格的 typed-output
规则。malformed activation、score、participant selection 或 moderator JSON
会进入既有安全 fallback，而不会转换字符串布尔值、数字字符串，或部分接受
包含错误成员的 selection。

reflection cooldown 和 daily-cap 状态现在带有版本并采用原子写入。malformed
或不完整状态会阻止 reflection 调度并留下结构化诊断，而不会被误判为首次运行、
从而静默关闭限流保护。

最近成功的 LLM endpoint 会保存为带版本、原子写入的派生偏好。无效或陈旧的
endpoint 状态会留下诊断并安全回退到配置顺序，因此损坏的偏好 metadata 不会
阻断模型访问。

每个项目根目录通过跨进程 instance lock 只允许一个 daemon owner。并发启动
不会再删除正在工作的 daemon Unix socket 或 PID 文件；竞争者会留下诊断并
退出，owner 继续正常服务。

daemon PID metadata 现在采用原子发布。PID 缺失仍表示正常 stopped 状态；
malformed 或非正数 PID 会留下诊断，不再被静默表现为普通缺失。

runtime state 和生成的 reason artifact 现在统一使用带唯一临时文件及失败清理的
atomic writer；thread、persona 和 reason 子系统不再各自维护不同的替换实现。

CLI persona lifecycle trace 遇到可恢复失败时会记录
`persona/trace_recording_failed`，而不会撤销已经成功的 create、enable 或
disable mutation。

缺失 `private/email.toml` 仍表示主动关闭 email delivery；如果文件存在但无法
读取或配置无效，NuSelf 会记录不包含配置内容的
`outbox/email_config_invalid`，不再静默当作文件缺失。

`private/threads/default.json` 是当前 NuSelf mind 的共享 working memory。多个终端连接同一个 daemon 时会共享它。thread store 会用锁串行化写入，避免并发对话互相覆盖。

memory curator 会在 daemon 后台定时运行，也会在交互式聊天退出时运行。它会用 agent 判断新的 working-memory 对话应该新增、修改还是忽略长期记忆。无意义闲聊会被忽略，已有相似记忆会优先更新而不是重复创建，原始对话流水账会被拒绝写入。默认情况下，候选记忆会自动提升为持久记忆条目（`auto_accept=True`）；如果 validation 失败，可恢复的候选会保留为 pending 并输出诊断，而不会静默消失。每个 thread 的 curator cursor 会原子写入；如果 cursor 损坏，本轮整理会停止并报告 corruption diagnostic，而不会重放旧对话。另有一个 memory optimizer 可以手动、低频运行，用来整合已经存在的杂乱条目。更新事件会写入 `private/logs/memory.log`，交互式聊天也会用紧凑 activity lines 显示新的 chat、daemon 和 memory 事件。

同步 post-chat curation 遇到可恢复失败时，已经完成的 assistant reply 仍会返回，
失败会带 turn correlation context 记录为
`memory/post_chat_curation_failed`，而不会静默表现为普通 no-op。

当前 conversation graph 有意保持较小：它保留 CLI 和 daemon protocol 边界，同时为后续 persona subgraphs 和更丰富的 agent routing 留出空间。

## 守护进程

启动、检查和停止本地守护进程：

```bash
uv run nuself daemon start
uv run nuself daemon status
uv run nuself daemon health
uv run nuself daemon list
uv run nuself daemon logs
uv run nuself daemon attach --message "continue"
uv run nuself daemon stop
uv run nuself daemon restart
```

也可以用通用日志查看器检查结构化本地日志：

```bash
uv run nuself dev logs
uv run nuself dev logs --component chat --tail 20
uv run nuself dev logs --component memory --json
uv run nuself dev logs --component reflection --tail 10
uv run nuself dev logs --component storage --tail 10
```

次要的审计或 thought trace 记录失败会显示为结构化的 `*_failed` 警告，但不会改变主操作的结果。
共享 backend 的生命周期故障会写入 `storage` component。
读取集合时会隔离损坏的存储记录，并通过不包含正文的 `record_decode_failed` 警告报告。
Reason thread 的调度时间戳必须包含时区，因此损坏的 cooldown 状态不会再静默地让线程
进入后台推进。

SQLite 后端对损坏的动态列 JSON 采用相同隔离规则：健康的相邻记录仍可读取，直接查询
保持严格，诊断中也不会包含损坏列的内容。显式关闭 backend 时会先 checkpoint WAL，
并明确返回 checkpoint 或连接关闭失败；关闭失败仍可重试，不会被错误标记为已完成。
无效的 reason export manifest 会安全停止合成。任务列表会报告并隔离损坏 manifest，
且不会暴露其中内容；直接查询和文件系统失败仍会明确返回。无效 progress 和 retry
state 持久化失败会写入 daemon 日志。Progress 缺失属于正常状态，但无法读取或格式
损坏时会明确诊断，也不会把部分非法字段强制转换成有效快照。

检查系统健康：

```bash
uv run nuself dev health
```

Daemon health 会同时反映定时迭代失败和 worker target 的意外退出。Worker 生命周期
统一发布为已注册的 `worker.started`、`worker.failed` 和 `worker.stopped` event，
再以相同 identity 和 `daemon.worker.<name>` source 投影到结构化 audit log。
Audit 或其他 event subscriber 失败时只会回退为 runtime warning，不会改变 worker
执行、health transition 或仍可恢复的定时循环。Shutdown 会尝试每一个 owned
cleanup step 并保留同时发生的故障；只有 worker、当前项目 storage、socket 和 PID
都清理成功后，才会写入 `daemon/stopped`。SIGINT/SIGTERM handler 只由 daemon
临时借用，退出时会精确恢复 host process 原有的 handler。

快速状态概览：

```bash
uv run nuself dev status
```

不带子命令时，`daemon` 会显示守护进程子命令帮助。

守护进程运行时文件存放在：

```text
private/runtime/
private/logs/
```

第一版协议在每个 Unix domain socket 连接上传输一个 request 和一个 response，
两者都是以换行结尾的 UTF-8 JSON；socket 路径是
`private/runtime/nuself.sock`。单帧上限为 1 MiB；停滞、截断、额外、格式错误或
request id 不匹配的 response 都会作为 transport error 返回，不会占住 server
thread 或被当成部分 JSON 接受。envelope 字段在收发两端都严格校验；重复或未知
字段、空 request id、非有限 payload 数值以及与 status 不一致的 error 状态都会被
拒绝。
每种 request type 还会校验自身的精确 payload 字段；类型错误的可选值不会再被静默
替换为默认值，`echo` 则保留为明确的任意 object 例外。
chat、health、activity、ping 和 shutdown 的 typed client operation 会校验完整的
成功 payload。daemon 明确拒绝与损坏的成功响应保持不同错误类型，损坏的 worker 或
activity 嵌套记录也不会被静默跳过。
排队的 reason export 会把不可变 runtime context 带入 worker 执行和重试，因此日志
能保留顶层 request、turn、trace、job 与 thread 关联，同时用消费它的 worker 标记
source。
持久化 notification intent 也会把来源 runtime context 直接保存在 outbox record
上；每条 adapter chain 会在 notification worker source 下恢复该 context，旧的无
context 记录仍可读取。
每次定时 memory、reflection、reason 和 notification-delivery tick 也会获得新的
job identity；嵌套工作与失败诊断共享该 identity，复用 worker thread 时每轮都会从
隔离的 context 开始。
短生命周期的 deferred callback 可以显式绑定其所延续逻辑操作的不可变 runtime
context。交互聊天的发送线程使用这一边界，同时 transcript capture 仍仅限当前 chat
path，不会吸收并发后台子系统的 audit record。
Reason advance 也通过这一共享 context 确定 workspace 与 thread-local persona
tools 的活动持久 reason thread，同时保留 request/job correlation。
进程内 live log observer 与 correlation identity 保持分离：嵌套 observer 会按
顺序组合，projection failure 在 audit write 后被隔离，并且 observer 不会隐式进入
新的 worker thread。
Runtime envelope 与 log event 共用同一个严格 JSON freeze/thaw 边界，因此持久化
audit data 和 live activity 会得到同一份不可变 metadata snapshot，不会保留对调用
方容器的别名。
每轮 agent tool 去重也使用同一套严格 JSON 语义生成 canonical cache identity；
非 JSON 参数会绕过缓存，而不是因字符串强制转换发生碰撞或阻止 LangChain 处理。
权威 file、SQLite collection 和 workspace persistence 会在 mutation 前校验严格
JSON；非有限值不会留下部分文件、动态 column、被替换的旧 row 或部分提交的
workspace batch。

## 通知

通知 outbox 是持久化的用户注意力队列，用于存放“发生了某事，请查看 X”的提醒，
它与内部 runtime 事件总线相互独立。需要提醒用户的后台任务可以使用它（如
开启 `auto_notify` 的 reflection、memory curator 等）。持久化通知时间戳必须
包含时区；损坏记录会被报告并隔离，不会再静默影响保留期清理。

```bash
uv run nuself inbox notify list
uv run nuself inbox notify show <entry-id>
uv run nuself inbox notify show -i <index>
uv run nuself inbox notify send <entry-id>
uv run nuself inbox notify dismiss <entry-id>
uv run nuself inbox notify dismiss -i <index>
uv run nuself inbox notify clear
uv run nuself inbox notify watch          # 轮询新条目
```

通知包含 deep link，可以直接打开：

```bash
uv run nuself thread open --deep-link "nuself://thread/reflections"
```

macOS adapter 通过 `osascript` 将 pending 条目投递为系统通知。email adapter 从 `private/email.toml` 读取 SMTP 凭证并通过 SMTP 发送。两者都支持 dry-run 模式用于测试。

## 主动反思

守护进程运行一个主动反思调度器，从近期 threads、记忆条目和 source documents 中生成想法候选。候选想法会按新颖度、置信度、紧急度和打断代价进行评分，再由一组随机抽取的内部人格进行讨论。通过 gate 的想法会被存储到 `private/reflections/`，作为带有 `pending` / `dismissed` / `archived` 状态的一等条目。

反思想法可以通过以下命令查看和管理：

```bash
uv run nuself inbox reflection list
uv run nuself inbox reflection list --status pending
uv run nuself inbox reflection list --status dismissed
uv run nuself inbox reflection show <id>
uv run nuself inbox reflection show -i <index>
uv run nuself inbox reflection dismiss <id>
uv run nuself inbox reflection archive <id>
uv run nuself inbox reflection promote <id>
```

当配置中 `reflection.auto_notify` 开启时，每次产生反思想法还会同时在 notify outbox 中创建一条简短提醒。

## Reason 与 Trace

Reason 将明确的长线问题保存成持久线程。Trace 保存重要聊天轮次、reason 线程创建、reason 推进和反思提升的来源记录。

```bash
uv run nuself reason list
uv run nuself reason start "我应该持续思考什么？"
uv run nuself reason show <id-or-index> --by-index
uv run nuself reason advance <id-or-index> --by-index
uv run nuself reason pause <id-or-index> --by-index
uv run nuself reason resume <id-or-index> --by-index
uv run nuself reason resolve <id-or-index> --by-index
uv run nuself reason archive <id-or-index> --by-index
```

```bash
uv run nuself trace list
uv run nuself trace show <id-or-index> --by-index
uv run nuself trace search "reason thread"
```

将一个 pending reflection 提升为 reason 线程：

```bash
uv run nuself inbox reflection promote <id-or-index> --by-index
```

## Threads

列出、查看和管理对话 threads：

```bash
uv run nuself thread list
uv run nuself thread show <thread-id>
uv run nuself thread new <thread-id>
uv run nuself thread rename <old-id> <new-id>
uv run nuself thread branch <source-id> <new-id> [--index <n>]
uv run nuself thread archive <thread-id>
uv run nuself thread unarchive <thread-id>
uv run nuself thread archived
uv run nuself thread delete <thread-id>
```

以交互模式打开 thread：

```bash
uv run nuself thread open <thread-id>
uv run nuself thread open <thread-id> --message "hello"
```

在 REPL 中，使用 `:thread <id>` 切换 thread，`:history` 查看近期消息，`:mem sources` 列出导入的 sources，`:mem search <query>` 搜索 memory，`:archive` 归档当前 thread，`:unarchive <id>` 恢复已归档 thread，`:archived` 列出已归档 threads，`:delete` 删除当前 thread。如果持久化 thread history 已损坏或无法读取，`:history` 会报告加载错误，而不会把它显示成空 thread。

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

导出所有记忆条目为 JSON：

```bash
uv run nuself memory export -o backup/memory.json
uv run nuself memory import backup/memory.json
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

列出已注册的记忆类型：

```bash
uv run nuself memory types
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

- [当前架构](docs/architecture.md)
- [系统规范](docs/spec/) — CLI、记忆、反思、通知等行为契约
- [当前开发目标](docs/current-goal.md)
- [未完成待办](docs/TODOs.md)
- [变更日志](CHANGELOG.md)
- [Agent 指令](AGENTS.md)

## 开发政策

NuSelf 处于早期快速开发阶段。接口预计会快速变化。除非当前文档明确要求兼容，否则不要保留过时的 CLI 命令、协议字段、数据 schema 或 Python API。

功能、命令、配置、运行方式或用户可见行为发生变化时，必须同步更新 [README.md](README.md) 和 [README.zh-CN.md](README.zh-CN.md)。
