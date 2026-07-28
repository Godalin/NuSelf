# Storage v2 — Unified Storage Layer → SQLite → Thought Packs

Status: implemented current storage and migration contract.

## Goal

Replace scattered file-backed repositories with a unified storage abstraction,
then migrate to a single SQLite database (`private/nuself.sqlite`) that can be
copied and shared as a complete thought pack.

## Directory Architecture

```
private/                    ← durable, portable, version-controllable
  config.yaml               ← local configuration
  threads/                  ← chat conversations (semi-durable)
  exports/                  ← export jobs + output
  imports/                  ← import staging
  backups/                  ← auto-backups of nuself.sqlite
  nuself.sqlite                 ← v0.2.4+: all durable user data

$TMPDIR/nuself/             ← ephemeral, auto-cleaned on reboot
  daemon.lock
  daemon.sock
  logs/                     ← structured log files (viewed via `nuself logs`)
  cache/                    ← temporary cache
```

### 设计理由

```
nuself.sqlite 包含              — 所有可分享的持久数据
├─ Memory entries / candidates / relations
├─ Profile items
├─ Source documents + chunks
├─ Persona prompts (global)
├─ Reasoning threads + steps
├─ Thought trace nodes + edges
├─ Workspace entries (reason scratch pads)
├─ Notification outbox
├─ Reflection entries
├─ Tool call records
├─ Approval records
├─ Identity information
└─ Schema metadata

threads/ 保留文件系统       — 对话记录是半持久缓存，用户希望保留但非核心知识

$TMPDIR/nuself/ 保留文件系统 — 运行时状态，重启即丢
├─ logs/                     — 查看频率低，放在 temp 不用清理
├─ cache/                    — LLM 响应缓存等
├─ daemon.lock / .sock       — 进程生命周期
```

Workspace 入 `nuself.sqlite` 而非文件系统，因为它是 reason thread 的重要组成部分，
思想包应当包含推理中间产物。DB 连接在 reason step advance 期间保持打开，
WAL 模式读写不阻塞，性能足够。

## Phase v0.2.3 — Storage Abstraction

### 目标

建立统一的 `StorageBackend` 抽象层，所有 Repository 停止直接操作文件系统路径。

### 核心变更

1. 定义 `StorageBackend` 协议 + `StorageCollection` 协议
2. 实现 `FileStorageBackend` 适配器，映射到现有 `private/` 下的目录
3. 所有 Repository 构造函数改为接受 `StorageBackend`，不再接受 `project_root`
4. Repository 内部读写从 `write_json_atomic` / `read_json` 换成 `col.put(id, obj.to_wire())`
5. 统一长期对象 ID 格式（各子系统 ID 前缀规范化）
6. 正式定义 `private/` 目录结构（本文件）

### StorageBackend 接口

```python
class StorageCollection(Protocol):
    """One table-like collection within the backend."""

    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, value: dict) -> None: ...
    def delete(self, key: str) -> None: ...
    def list(self) -> tuple[dict, ...]: ...
    def find(self, **filters: object) -> tuple[dict, ...]: ...

class StorageBackend(Protocol):
    def collection(self, name: str) -> StorageCollection: ...
```

### FileStorageBackend

v0.2.3 用 `FileStorageBackend` 包装现有文件系统布局，不改变数据物理位置。

Collection → 目录 映射表（静态配置）：

| Collection name | Current path |
|---|---|
| `memory_entries` | `private/memory/entries/` |
| `memory_candidates` | `private/memory/candidates/` |
| `memory_relations` | `private/memory/relations/` |
| `reason_threads` | `private/reason/threads/` |
| `reason_steps` | `private/reason/steps/` |
| `trace_nodes` | `private/traces/` |
| `trace_edges` | `private/trace_edges/` |
| `persona_prompts` | `private/persona/` |
| `profile_items` | `private/profile/` |
| `source_documents` | `private/sources/documents/` |
| `source_chunks` | `private/sources/chunks/` |
| `notification_outbox` | `private/notifications/outbox/` |
| `reflection_entries` | `private/reflection/entries/` |

```python
class FileStorageBackend:
    def __init__(self, root: Path, collection_map: dict[str, str]):
        self._root = root
        self._map = collection_map

    def collection(self, name: str) -> StorageCollection:
        return _FileCollection(self._root / self._map[name])

class _FileCollection:
    def put(self, key: str, value: dict) -> None:
        write_json_atomic(self._dir / f"{key}.json", value)

    def get(self, key: str) -> dict | None:
        path = self._dir / f"{key}.json"
        return read_json(path) if path.exists() else None

    def delete(self, key: str) -> None:
        (self._dir / f"{key}.json").unlink(missing_ok=True)

    def list(self) -> tuple[dict, ...]:
        return tuple(
            read_json(p) for p in sorted(self._dir.iterdir())
            if p.suffix == ".json"
        )

    def find(self, **filters: object) -> tuple[dict, ...]:
        # 线性扫描 + 过滤，SQLite 版走索引
        ...
```

### Repository 模式变更（示例）

```python
# Before
class MemoryEntryRepository:
    def __init__(self, project_root: Path | None = None):
        self._root = runtime_paths(project_root).private_root / "memory" / "entries"

# After
class MemoryEntryRepository:
    def __init__(self, backend: StorageBackend):
        self._col = backend.collection("memory_entries")
```

Repository 内部纯数据逻辑不变（`to_wire()` / `from_wire()` 已就绪）。

### Corrupt Record Reads

Storage collections return stored wire dictionaries without applying domain
schema policy. Repository list/rebuild operations decode those dictionaries
through the shared corrupt-record isolation boundary defined in
[`errors.md`](errors.md). A malformed wire record is skipped with a structured,
payload-safe diagnostic; it is never silently deleted or rewritten. Direct
lookups surface the decode failure.

SQLite dynamic columns add one lower-level decode boundary. SQL `NULL` means
the complete-replacement wire record omitted that field; a populated column is
always JSON text and must decode successfully, including JSON `null` as a
present Python `None` value. Invalid JSON and non-text dynamic values are
storage corruption and are never returned as raw strings or silently omitted.

SQLite `get()` surfaces this corruption directly. SQLite `list()` and rows
selected by `find()` report and isolate each corrupt row through the same
payload-safe component `record_decode_failed` event used by repositories, then
continue with healthy neighbors. Diagnostics include only collection and record
id, not column text or the complete row. The SQLite collection adapter retains
its project root and collection-to-component ownership so these diagnostics
flow to the correct structured log.

### SQLite Backend Lifecycle

The creator of a `SqliteStorageBackend` owns it and must call `close()` when
the backend is no longer needed. Process-default backends are owned by the
default-backend registry and released by `reset_default_backend()`; temporary
thought-pack backends are owned by the command that opens them.
Owners must quiesce concurrent users before closing the backend.

`close()` is lock-protected and idempotent after the underlying connection has
closed successfully. It first requests a truncating WAL checkpoint and always
attempts to close the connection even if that checkpoint fails. A checkpoint
exception, invalid status, or non-zero SQLite `busy` result is surfaced after
a successful connection close because data remains recoverable in the WAL but
the requested lifecycle operation was degraded. A
connection-close failure is authoritative: the backend remains open and the
failure is retryable. If both operations fail, the close error exposes the
checkpoint error as secondary diagnostic context without replacing the close
failure.

Schema initialization failures remain the primary cause. The constructor
attempts to close its partially initialized connection; if that cleanup also
fails, it raises a stable initialization-cleanup error whose cause is the
original initialization failure and whose secondary diagnostic retains the
close failure.

Resetting default backends removes their registry ownership before closing
them, attempts every selected backend even when an earlier close fails, and
then raises one cleanup error containing all close failures. It never leaves a
failed backend registered as if it were safe to reuse.

### Unify Long-Lived Object IDs

统一 ID 格式为 `{prefix}_{uuid_short}`：

| Subsystem | Prefix | Example |
|---|---|---|
| Memory entries | `mem` | `mem_a1b2c3d4` |
| Memory candidates | `mc` | `mc_e5f6g7h8` |
| Memory relations | `rel` | `rel_i9j0k1l2` |
| Reason threads | `rt` | `rt_m3n4o5p6` |
| Reason steps | `rs` | `rs_q7r8s9t0` |
| Trace nodes | `tr` | `tr_u1v2w3x4` |
| Trace edges | `te` | `te_y5z6a7b8` |
| Persona prompts | `pp` | `pp_c9d0e1f2` |
| Profile items | `pf` | `pf_g3h4i5j6` |
| Source docs | `sd` | `sd_k7l8m9n0` |
| Source chunks | `sc` | `sc_o1p2q3r4` |
| Notification outbox | `no` | `no_s5t6u7v8` |
| Reflection entries | `re` | `re_w9x0y1z2` |

现有数据保留原 ID，新对象采用新格式。Repository 仅在新建时生成新格式 ID。

## Phase v0.2.4 — SQLite Backend

### 目标

将核心持久状态迁移到 `private/nuself.sqlite`，引入 migration system + schema version
管理。

### 核心变更

1. 实现 `SqliteStorageBackend` 适配同一 `StorageBackend` 接口
2. 引入 `_schema_version` 表 + migration system
3. 支持事务化 trace/reason 操作（因果链批量提交）
4. 引入 `workspace_entries` 表（reason scratch pad）

### 设计原则

当前 SQLite 适配器使用通用 collection 表：`id` 是主键，每个 wire
字典的顶层字段对应一个动态 JSON 文本列。这个布局优先保持
`StorageCollection` 与文件后端的通用 round-trip 语义；领域专用索引、FTS5
和完整 payload 镜像仍是后续 schema 演进事项，不能描述成已经实现。

`put(id, value)` 是完整对象替换，不是 partial patch。调用方必须传入完整
wire 字典；SQLite 使用 conflict update 实现替换语义，不能依赖
`INSERT OR REPLACE` 的隐式 delete+insert 行为。

所有 file 与 SQLite collection payload 必须在任何文件、schema 或 row mutation
之前完成共享 strict JSON 编码。mapping key 必须是 string，float 必须有限，
任意 Python object 不得通过 `default=str` 或 NaN extension 落盘。SQLite
dynamic-column `put()` 必须先编码完整 replacement，之后才能 `ALTER TABLE`；
编码失败不得新增 column、修改旧 row 或依赖后续 rollback 偶然清理。

持久化 JSON 读取也使用严格 decoder，拒绝 `NaN`、`Infinity` 和
`-Infinity`。file list 和 SQLite list 继续按既有 corruption policy 隔离坏记录；
直接 `get()` 继续暴露 corruption。

### Transaction contract

- `StorageBackend.transaction()` 包围一个原子写入批次。
- SQLite 后端必须在最外层 transaction 使用
  `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`；批次内 collection 写入不得自行
  commit。
- 同一线程允许嵌套 transaction；只有最外层上下文拥有数据库事务。
- transaction 抛出异常时，本批次所有写入回滚。
- 任意内层 transaction 抛出 `BaseException` 后，当前最外层事务进入
  rollback-only 状态。即使调用方在外层 block 内捕获了内层异常，最外层退出时也
  必须回滚并抛出 `SqliteTransactionRollbackOnlyError`，不得提交部分失败批次。
- `KeyboardInterrupt`、`SystemExit`、commit 失败和 rollback 失败都必须恢复
  thread-local transaction depth/state。Commit 失败先尝试 rollback，再传播原始
  commit 错误；若 rollback 也失败，稳定的 transaction cleanup 错误必须以原始
  操作错误为 cause，同时描述 rollback 失败。
- 事务内的动态 `ALTER TABLE` 也会被 SQLite rollback。每次 rollback（包括
  rollback 自身报错、数据库状态未知的情况）都必须清空共享 column cache，后续
  collection 操作重新读取真实 schema，不能使用已回滚的列集合。
- 文件后端无法提供跨文件数据库事务；它至少序列化批次，并继续依赖单文件
  atomic replace。调用方不得把它描述为跨文件原子提交。

Reason 的 step + thread 更新必须使用 backend transaction，避免只写入 step
但没有推进 thread 的半完成状态。

### Schema migration safety

- schema migration 必须在数据库事务中执行，任一步失败都不得提升版本号。
- 破坏性 migration 前必须使用 SQLite backup API 创建同目录备份。
- v1 `payload` 数据升级为动态列时，先解析每行完整 JSON object，将其展开并
  验证 ID，再删除旧列；不允许直接 drop `payload`。
- migration 测试必须从真实旧 schema fixture 开始，验证条数、ID 和完整 wire
  数据在升级后保持一致，并验证失败时回滚。

### 核心表清单

```
identities           ← 身份信息
persona_prompts      ← 全局 persona prompt
memory_entries       ← 记忆条目
memory_candidates    ← 记忆候选
memory_relations     ← 记忆关系
reflection_entries   ← 反思条目
reason_threads       ← 推理线程
reason_steps         ← 推理步骤
trace_nodes          ← 思想溯源节点
trace_edges          ← 思想溯源边
workspace_entries    ← 推理工作空间
tool_calls           ← 工具调用记录
approvals            ← 审批记录
notification_outbox  ← 通知发件箱
source_documents     ← 源文档
source_chunks        ← 源文档分块
profile_items        ← 画像条目
metadata             ← schema 元数据 / 系统信息
```

### Future indexed table direction

```sql
CREATE TABLE memory_entries (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    review_state TEXT NOT NULL,
    confidence REAL,
    importance REAL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL       -- to_wire() JSON
);
CREATE INDEX idx_mem_type ON memory_entries(type);
CREATE INDEX idx_mem_review ON memory_entries(review_state);

CREATE TABLE reason_threads (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX idx_thread_status ON reason_threads(status);

-- 同类模式扩展至全部核心表
```

### Future full-text search

Memory search 当前的手写 tokenize+score 逻辑保留评估，v0.2.4 引入 FTS5
作为可选搜索后端：

```sql
CREATE VIRTUAL TABLE memory_fts USING fts5(
    title, body, content=memory_entries, content_rowid=rowid
);
```

FTS5 支持 `AND`, `OR`, `NOT`, phrase, prefix 查询。评分权重通过 FTS5 `rank`
和自定义 rank 函数控制。v0.2.4 阶段 FTS5 与现有评分搜索并存，用户可选择。

### 启动初始化

`SqliteStorageBackend.__init__` 时执行 schema 初始化：

```python
def _init_schema(self):
    current_version = self._conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version < 1:
        self._conn.executescript(_SCHEMA_V1)
        self._conn.execute("PRAGMA user_version = 1")
```

### 并发

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- 写操作通过 `threading.Lock` 串行化（当前每个 repo 已有 RLock）
- WAL 模式读写互不阻塞

## Phase v0.2.5 — Thought Pack Infrastructure

### 目标

建立思想包（Thought Pack）导出与导入基础设施，实现跨实例知识分享。

### 包格式

思想包就是一份 `nuself.sqlite`。导出 = cp，导入 = cp，不需要中间格式。

```
private/
  nuself.sqlite             ← 当前思想（完整）
  exports/
    <name>.sqlite           ← 导出快照
  imports/
    <filename>.sqlite       ← 导入的他人思想
```

### CLI 接口

```
nuself pack export <name>         → cp nuself.sqlite → exports/<name>.sqlite
nuself pack import <path>         → cp <path> → imports/<filename>.sqlite
nuself pack inspect [<path>]      → 展示 <path> 或主库的表统计
                                   (默认展示主库)
```

### 导出约束

- **不包含 runtime state**（chat threads, daemon state, logs, cache — 这些不在 nuself.sqlite 里）
- **不包含本地配置**（config.yaml — 不在库里）
- **保持 identity 来源信息**（出处可追溯）
- 导出的 `.sqlite` 可用 `SqliteStorageBackend` 直接打开

### 未来方向

**NuHub** — 基于 GitHub Releases 分享 `.sqlite` 文件：

```bash
nuself pack publish <name> --repo username/nuhub
nuself pack install <identity>/<name> --from github
```

## Migration 路径

```
v0.2.3  定义 StorageBackend 协议 + FileStorageBackend 适配
         所有 Repo 改为接受 backend
         统一长期对象 ID 格式
         行为不变，零迁移

v0.2.4  加 SqliteStorageBackend
         nuself.sqlite schema + migration system
         FTS5 搜索（可选）
         默认后端仍为 file；用户选择切换
         旧文件数据迁移到 db：nuself dev migrate

v0.2.5  思想包导出/导入基础设施
         nuself pack export/import/inspect
         manifest + identity isolation
         可分享的思想包就绪
```

## 分享场景

他人拿到 `nuself.sqlite` 后：

```python
backend = SqliteStorageBackend("path/to/nuself.sqlite")
repo = MemoryEntryRepository(backend)
for entry in repo.list():
    print(entry.to_wire())
```

或通过 thought pack 导入：

```bash
nuself pack import friend-thoughts.tar.gz
```

无需 unpack 整个 `private/`，一个文件 / 一个包就是一份完整的思想快照。
