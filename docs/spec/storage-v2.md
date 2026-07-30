# Storage v2 — Unified Storage Layer → SQLite → Thought Packs

Status: implemented current storage and migration contract.

## Goal

Replace scattered file-backed repositories with a unified storage abstraction,
then migrate to a single SQLite database
(`<authority-root>/nuself.sqlite`) that can be copied and shared as a complete
thought pack.

## Directory Architecture

```
<authority-root>/          ← selected user or workspace authority
  config.yaml               ← local configuration
  threads/                  ← chat conversations (semi-durable)
  exports/                  ← export jobs + output
  imports/                  ← import staging
  backups/                  ← auto-backups of nuself.sqlite
  nuself.sqlite                 ← v0.2.4+: all durable user data

<short-runtime-base>/       ← owner-private, short Unix socket paths
  <authority-id>.sock
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
2. 实现 `FileStorageBackend` 适配器，映射到现有 `<authority-root>/` 下的目录
3. 所有 Repository 构造函数改为接受 `StorageBackend`，不再接受 `project_root`
4. Repository 内部读写从 `write_json_atomic` / `read_json` 换成 `col.put(id, obj.to_wire())`
5. 统一长期对象 ID 格式（各子系统 ID 前缀规范化）
6. 正式定义 `<authority-root>/` 目录结构（本文件）

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
| `memory_entries` | `<authority-root>/memory/entries/` |
| `memory_candidates` | `<authority-root>/memory/candidates/` |
| `memory_relations` | `<authority-root>/memory/relations/` |
| `reason_threads` | `<authority-root>/reason/threads/` |
| `reason_steps` | `<authority-root>/reason/steps/` |
| `trace_nodes` | `<authority-root>/traces/` |
| `trace_edges` | `<authority-root>/trace_edges/` |
| `persona_prompts` | `<authority-root>/persona/` |
| `profile_items` | `<authority-root>/profile/` |
| `source_documents` | `<authority-root>/sources/documents/` |
| `source_chunks` | `<authority-root>/sources/chunks/` |
| `notification_outbox` | `<authority-root>/notifications/outbox/` |
| `reflection_entries` | `<authority-root>/reflection/entries/` |

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

File collection keys are opaque stable record identifiers, never paths.
`get`, `put`, and `delete` reject empty keys, absolute paths, `.`/`..`, NUL,
and either path separator. The resolved record must be a direct regular-file
child of the configured collection directory; symlinked collection
directories or record paths are rejected. `list` scans direct `*.json`
children only and rejects symlink records rather than traversing them.

When a value written through `put` contains an `id` field, it must be a string
equal to the collection key. A mismatch is a producer contract error and no
file is created or replaced.

File collection deletion uses the shared durable-delete boundary. Returning
from `delete` means the unlink and parent-directory synchronization both
succeeded; a post-unlink sync failure raises the typed visible-but-uncertain
delete error rather than reporting a normal failure or silently succeeding.

Each live `FileStorageBackend` holds a shared cross-process authority lease on
`<authority-root>/.storage-authority.lock` until `close()`. Lease acquisition is
non-blocking: a command that races an authority migration fails rather than
waiting and then continuing to use the obsolete file backend. File-to-SQLite
migration takes the exclusive lease before inspecting source or destination
state and holds it through atomic publication. If any daemon, CLI, or other
file-backed runtime still owns a shared lease, migration fails without reading,
copying, or publishing data. This is the enforced stop-the-world authority
switch for v0.3.0.

Shared lease acquisition and selection of file authority are one atomic
decision. After acquiring the shared lease, a backend must re-check the
canonical `<authority-root>/nuself.sqlite` path while still holding that lease. If the
database exists or is a symlink, explicit file-backend construction fails and
`auto_backend()` selects SQLite instead. Thus a process paused before lease
acquisition cannot resume after migration publication and write to obsolete
files. A closed file backend is permanently unusable: `collection()`,
`transaction()`, and every operation on collections created before closure
must fail.

Opening and creating SQLite storage are separate operations.
`open_sqlite_backend()` and direct `SqliteStorageBackend` construction require
an existing regular database file and never create one. Project-managed paths
validate their parent without following symlinks before inspecting or
hardening the file. Explicit external paths validate the existing regular file
but never chmod its parent or the file.

Before any writable SQLite connection, schema change, or business write,
opening uses a `mode=ro` connection with normal SQLite locking, change
detection, and WAL coordination to require a valid NuSelf `_schema_version`,
every known collection table, and each collection's `id` primary key.
Canonical authority is live mutable state and must never be opened with
`immutable=1`. The lock-aware read-only connection may access or create
SQLite's WAL/SHM coordination artifacts. Empty files, unrelated SQLite
databases, incomplete NuSelf schemas, corruption encountered while reading
identity metadata, and future schema versions fail closed without schema
initialization or business mutation.
Recognized supported versions may then perform their documented controlled
upgrade.

An existing v1 database is upgraded under a stable sibling schema lease shared
by every process opening that database path. A process that first observes v1
must acquire the exclusive lease and then re-read and revalidate the schema
version. Only a lease holder that still observes v1 may create the pre-v2
backup and run the v2 transaction. Later holders observe v2 and do neither.
The backup must therefore remain a genuine v1 database with its `payload`
columns, and `_schema_version` contains only one row for each applied version.
The unpublished migration creator does not need this lease because its
database is unreachable until the separate authority publication completes.

Ordinary authority identity validation is metadata-only and must not run
`PRAGMA quick_check`. Full integrity checking remains part of thought-pack
import and inspection, where the database is an explicit external artifact
rather than every CLI startup path.

Creation is an
internal migration operation used only for the unpublished
`nuself.sqlite.migrating-<uuid>` database while the exclusive file-authority
lease is held. Ordinary runtime, developer inspection, and repository
composition cannot publish the canonical database as a side effect.

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

Every operation on one `SqliteStorageBackend` connection uses the backend's
single reentrant lock. This includes `get`, `list`, `find`, dynamic-column
inspection, `collection`, `collection_names`, and `table_info`, as well as
writes, transactions, backup, and close. An outer transaction retains that
lock until commit or rollback, so another thread sharing the connection can
never observe uncommitted writes. Reads inside the owning thread remain valid
through reentrant acquisition.

Dynamic-column metadata is read from SQLite for each operation rather than
cached for the backend lifetime. A second process may add a column through a
different connection; the next read on an already-running backend must
immediately select and decode that field without a restart.

SQLite and file collections share the same record identity contract. If a
value passed to `put(key, value)` contains `id`, it must be a string equal to
`key`; mismatches are producer errors and no database mutation occurs.

### SQLite Backend Lifecycle

NuSelf-owned database directories use mode `0700`; the main database,
workspace databases, WAL/SHM sidecars, and internal import/export snapshots use
mode `0600`. Existing active files are hardened before use. SQLite must not
create a broader-permission database and narrow it only after private content
has been written. Explicit external SQLite paths, including paths passed to
`open_sqlite_backend(db_path=...)` outside the canonical managed location, are
not owned by this invariant: their parent and existing database mode remain
unchanged, while SQLite coordination artifacts retain normal
directory/`umask` semantics.

Canonical ownership is determined by the database path and authority root, not
only by which factory called the backend. Direct construction of
`<authority-root>/nuself.sqlite` receives the same no-follow validation and
hardening as `open_sqlite_backend(authority_root)`. An explicit external path is
unmanaged unless a private internal creator marks it as an unpublished managed
migration database.

Every SQLite backup operation carries destination ownership explicitly.
Managed v1 safety backups and managed internal snapshots use no-follow private
directory handling and owner-only modes. A v1 backup beside an external
database and the default public `backup_to(destination)` path preserve the
existing parent mode and create a new regular file according to the caller's
normal `umask`; they never route through private-directory hardening.

The managed authority root and its managed directory descendants are opened
component-by-component with no-follow directory handles. A symlink or
non-directory component fails before NuSelf changes permissions, creates
storage/lock/runtime files, or reads redirected state.

The creator of a `SqliteStorageBackend` owns it and must call `close()` when
the backend is no longer needed. Process-default backends are owned by the
default-backend registry and released by `reset_default_backend()`; temporary
thought-pack backends are owned by the command that opens them.
Owners must quiesce concurrent users before closing the backend.

Ordinary repositories and long-lived service/tool composition must obtain
their implicit backend through `get_default_backend(project_root)`. They share
that backend by normalized project root and never close it individually.
Passing an explicit `backend=` remains an isolation boundary: the caller owns
that backend, the repository uses only the supplied instance, and the default
registry is not consulted. `auto_backend()` is a low-level owned-backend
factory for migration, diagnostics, and the default registry itself; ordinary
repository constructors must not call it directly.

The outer `nuself.cli.main()` invocation owns the default backend used by local
one-shot and interactive work. It resets that project-root backend exactly
once after dispatch finishes or raises. For interactive mode, this outer reset
runs only after transcript and curator cleanup. Daemon server cleanup may have
already reset the same backend; reset is idempotent when no backend remains.

Developer storage and schema inspection read the project default backend and
leave closure to the outer CLI lifecycle. Schema inspection succeeds only
when the active backend is SQLite. On file authority it returns a diagnostic
directing the user to `nuself dev migrate` and leaves the canonical path and
file-backed records untouched.

`nuself dev migrate` is the in-authority storage switch and therefore has
exactly one destination: canonical `<authority-root>/nuself.sqlite`. It does not expose a
custom `--db` destination; non-authoritative database copies belong to
snapshot/export workflows. The command must never create or mutate its final
database path while copying authoritative file data. It writes a uniquely
named `nuself.sqlite.migrating-<uuid>` sibling, performs the complete migration inside
one SQLite transaction, validates the migrated collection IDs and wire values,
then checkpoints and closes that temporary backend. Only after the temporary
database file is synchronized may the command atomically replace the final
path and synchronize its parent directory. A failure before replacement must
leave an existing final database byte-for-byte unchanged and must remove all
temporary database files and SQLite sidecars. A failure synchronizing the
parent after replacement is reported as a visible-but-durability-unknown
commit.

Migration reads are strict even though ordinary file collection listing
isolates corrupt neighbors. Every source record must be a direct, non-symlink
JSON object with a non-empty string `id` matching its filename. Missing or
invalid IDs, corrupt JSON, nested paths, and symlinks fail the entire migration;
they are never silently skipped. File migration is a one-time authority switch,
not a database merge: the final destination must not already exist. Operators
must explicitly move or remove an obsolete destination before retrying; the
old `--clear` in-place mutation option is not part of the atomic contract.
Final-name SQLite WAL/SHM/journal sidecars without a main database are also an
incomplete/conflicting destination and block migration. Conversely,
`auto_backend()` ignores uniquely named `.migrating-*` siblings: before atomic
replacement they are never evidence that SQLite owns runtime authority.

`close()` is lock-protected and idempotent after the underlying connection has
closed successfully. Ordinary live backends first request a passive WAL
checkpoint so shutdown cooperates with concurrent readers and writers. The
unpublished migration backend, which is protected by the exclusive authority
lease, instead requires a truncating checkpoint before publication. Close
always attempts to close the connection even if its checkpoint fails. A
checkpoint exception or invalid status is surfaced after a successful
connection close. A non-zero `busy` result is normal for a passive checkpoint
when another process is checkpointing and does not fail ordinary close; it is
an error for the migration backend's required truncating checkpoint because
publication must not discard a live WAL. In either failure case data remains
recoverable in the WAL but the requested lifecycle operation was degraded. A
connection-close failure is authoritative: the backend remains open and the
failure is retryable. If both operations fail, the close error exposes the
checkpoint error as secondary diagnostic context without replacing the close
failure.

Schema initialization failures remain the primary cause. The constructor
attempts to close its partially initialized connection; if that cleanup also
fails, it raises a stable initialization-cleanup error whose cause is the
original initialization failure and whose secondary diagnostic retains the
close failure.

Concurrent process-local backend construction is serialized through one
initialization lock before WAL and schema setup. Connections also configure a
finite SQLite busy timeout before initialization so a competing process can
finish its transaction instead of causing an immediate `database is locked`
failure. Non-lock initialization errors retain the lifecycle behavior above.

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

将核心持久状态迁移到 `<authority-root>/nuself.sqlite`，引入 migration system + schema version
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
  操作错误为 cause，同时通过 `primary_error` 和 `rollback_error` 保留两个
  `BaseException` 对象；不得要求调用方从 message 反向解析错误类型。
- transaction body、`KeyboardInterrupt` / `SystemExit`、commit 以及
  rollback-only 检查都遵守同一个双重失败契约。Rollback 无论成功或失败都复位
  thread-local depth/rollback-only 状态并清空 column cache，不做隐式重试。
- 事务内的动态 `ALTER TABLE` 也会被 SQLite rollback。每次 rollback（包括
  rollback 自身报错、数据库状态未知的情况）都必须清空共享 column cache，后续
  collection 操作重新读取真实 schema，不能使用已回滚的列集合。
- 多个 backend 连接可能同时首次发现同一动态字段。`ALTER TABLE` 的
  duplicate-column 失败只有在重新读取实际 schema 并确认目标列已经由竞争连接
  创建后才可视为成功；其他 `OperationalError` 必须原样传播。每次 DDL 尝试后
  都要使连接本地 column cache 失效。
- 文件后端无法提供跨文件数据库事务；它通过 `<authority-root>/` 根目录下稳定、不会在
  正常操作中删除的 advisory lock 跨线程、backend instance 和进程序列化批次，
  并继续依赖单文件 atomic replace。同一线程嵌套 transaction 复用最外层锁，
  不得再次获取文件锁而自死锁。调用方不得把它描述为跨文件原子提交。

Reason 的 step + thread 更新必须使用 backend transaction，避免只写入 step
但没有推进 thread 的半完成状态。

### Schema migration safety

- schema migration 必须在数据库事务中执行，任一步失败都不得提升版本号。
- 破坏性 migration 前必须使用 SQLite backup API 创建同目录备份。
- v1 `payload` 数据升级为动态列时，先解析每行完整 JSON object，将其展开并
  验证 ID，再删除旧列；不允许直接 drop `payload`。
- migration 测试必须从真实旧 schema fixture 开始，验证条数、ID 和完整 wire
  数据在升级后保持一致，并验证失败时回滚。
- 从文件后端迁移 0.2.x memory entry、candidate 或 profile item 时，迁移边界
  必须把旧顶层及嵌入 payload 的 `supersedes` 合并到
  `relations.supersedes`，把 `related_memory_ids` 合并到
  `relations.related_to`，随后删除旧字段。当前领域解码器仍必须拒绝未经显式
  迁移的旧关系形状。

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
- `PRAGMA busy_timeout=5000`
- 当前 schema 的同一进程初始化通过共享 lock 串行化；已有旧 schema 的首次
  可写打开、WAL setup、备份和升级还通过稳定 sibling lease 跨进程串行化，并在
  lease 内重新读取版本
- 写操作通过 `threading.Lock` 串行化（当前每个 repo 已有 RLock）
- WAL 模式读写互不阻塞

## Phase v0.2.5 — Thought Pack Infrastructure

### 目标

建立思想包（Thought Pack）导出与导入基础设施，实现跨实例知识分享。

### 包格式

思想包就是一份 `nuself.sqlite`。导出 = cp，导入 = cp，不需要中间格式。

```
<authority-root>/
  nuself.sqlite             ← 当前思想（完整）
  exports/
    <name>.sqlite           ← 导出快照
  imports/
    <filename>.sqlite       ← 导入的他人思想
```

### CLI 接口

```
nuself pack export <name>         → SQLite online backup → exports/<name>.sqlite
nuself pack import <path>         → validate + SQLite backup → imports/<filename>.sqlite
nuself pack inspect [<path>]      → 展示 <path> 或主库的表统计
                                   (默认展示主库)
```

### 导出约束

- Export names are portable file names, not paths. After an optional trailing
  `.sqlite` is removed, the name must start with an ASCII letter or digit and
  contain only ASCII letters, digits, `.`, `_`, or `-`. Empty names, hidden
  names, separators, absolute paths, and traversal components are rejected
  before opening the destination. Names must not end in `.` and their
  case-insensitive first component must not be a Windows device name (`CON`,
  `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, or `LPT1`-`LPT9`), including a reserved
  name followed by another extension.
- The destination is always exactly
  `<authority-root>/exports/<name>.sqlite`; user input
  cannot select another directory.
- Export uses SQLite's online backup API through the shared project backend;
  it never copies only the main database file. The snapshot includes committed
  WAL data and remains consistent while another connection is writing.
- The source default backend remains owned by the outer CLI lifecycle. The
  backup operation owns and always closes its destination connection.
- Managed `exports/` and `imports/` snapshots under the selected authority inherit
  the owner-only SQLite file contract.
- Runtime export, validated import, and pre-migration backup all use one
  connection-to-path backup primitive. It creates the destination directory,
  owns exactly one destination connection, and closes it once. If backup and
  close both fail, the cleanup error is retained without replacing the backup
  error as the explicit cause.
- **不包含 runtime state**（chat threads, daemon state, logs, cache — 这些不在 nuself.sqlite 里）
- **不包含本地配置**（config.yaml — 不在库里）
- **保持 identity 来源信息**（出处可追溯）
- 导出的 `.sqlite` 可用 `SqliteStorageBackend` 直接打开

### 导入约束

- Import opens the external source in SQLite read-only mode and never runs
  schema initialization or migration against it.
- Before creating the destination it requires `PRAGMA quick_check` success, a
  non-empty `_schema_version` within NuSelf's supported range, every known
  collection table, and an `id` primary key on each collection table.
- A future schema version is rejected by both import validation and ordinary
  runtime backend initialization. Legacy supported versions may be imported
  without modifying the source and migrate only if a later owned runtime opens
  the imported copy.
- Validation and copy use the same source connection. Copy uses SQLite online
  backup so committed source WAL data is included. Validation failure leaves
  no destination file.

### 检查约束

- Inspect uses the same read-only connection and compatibility validator as
  import. It never constructs a mutable backend for the inspected file.
- The storage inspection API returns schema version and per-collection counts
  from that validated connection. CLI rendering does not query SQLite
  directly.
- Supported legacy packs remain byte-for-byte unmodified; corrupt, foreign,
  partial, and future schemas render a concise validation error and fail.

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

无需 unpack 整个 `<authority-root>/`，一个文件 / 一个包就是一份完整的思想快照。
