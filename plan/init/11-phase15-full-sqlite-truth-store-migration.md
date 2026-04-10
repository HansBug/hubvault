# 11. Phase 15 全面 SQLite 真相层迁移

## Goal

在 Phase 14 已经完成的 reachable-state 安全定义、全局可串行化边界、zip 级可移植约束与 SQLite-first 设计闭环基础上，执行 repo-root 内的全面 SQLite 改造，把当前剩余的文件协议真相层收束到单一事务 substrate，同时保持 payload 文件外置、公开 API 语义稳定、HF 兼容边界稳定和 `repo.lock` 外层串行化边界不变。

## Status

待开始。

Phase 15 是明确的执行阶段，而不是继续选型或继续讨论“要不要上 SQLite”。

本阶段直接承接 Phase 14 已定稿的结论：

- 继续使用 repo-root 内单一 `locks/repo.lock` shared/exclusive 文件锁。
- 默认使用标准库 `sqlite3`，不引入 LMDB 或外部数据库服务。
- 默认使用 rollback journal（`DELETE`），不把 WAL 作为默认模式。
- `synchronous` 优先使用 `EXTRA`；若运行时 SQLite 不支持，则回退到 `FULL`，以保持 Python `3.7-3.14` 与旧系统平台面。
- payload bytes 继续留在文件系统，SQLite 只承担 metadata / object-truth store 职责。

## Scope

Phase 15 的执行范围如下。

- 将 repo 级元数据收进 SQLite：
  `repo_meta`
- 将 ref 真相层收进 SQLite：
  `refs`
- 将 reflog 真相层收进 SQLite：
  `reflog`
- 将事务与恢复状态收进 SQLite：
  `txn_log`
- 将 chunk 可见索引真相层收进 SQLite：
  `chunk_visible`
- 将 commit/tree/file/blob metadata 真相层收进 SQLite：
  `objects_commits`、`objects_trees`、`objects_files`、`objects_blobs`
- 将 `create_repo()`、`create_commit()`、`merge()`、refs/tag 管理、`gc()`、`squash_history()`、verify/storage overview 等读写维护路径统一切到 SQLite truth-store
- 在迁移完成后，移除旧的文件协议真相职责，避免长期双真相源

## Non-Goals

下面这些内容明确不属于 Phase 15：

- 全量把 `objects/blobs/*.data` 或 `chunks/packs/*.pack` 的 payload bytes 搬进 SQLite
- 去掉 `repo.lock`，让 SQLite 直接承担仓库级公开并发协议
- 默认启用 WAL
- 因 SQLite 迁移而抬高 Python 最低版本
- 依赖 JSON1、`RETURNING`、`UPSERT`、generated column、外部 extension 等高版本或可选 SQLite 能力作为正确性前提
- 引入仓库外 sidecar、首次打开 repair 步骤、外部数据库服务或外部注册状态
- 改动 detached view、HF-style path suffix、公开 `oid` / `blob_id` / `sha256`、rollback-only 与 zip 级可移植语义

## Target Layout

Phase 15 目标布局如下：

- 继续保留：
  `FORMAT`
- 继续保留：
  `locks/repo.lock`
- 新增并长期保留：
  `metadata.db`
- 继续保留：
  `objects/blobs/*.data`
- 继续保留：
  `chunks/packs/*.pack`
- 继续保留：
  `cache/`
- 继续保留：
  `quarantine/`
- 继续保留：
  `txn/` 作为 payload staging / residue 区

迁移完成后，下面这些路径不再承担 steady-state truth-source 职责：

- `repo.json`
- `refs/`
- `logs/refs/`
- `chunks/index/MANIFEST`
- `chunks/index/*.idx`
- `objects/commits/`
- `objects/trees/`
- `objects/files/`
- `objects/blobs/*.meta.json`

它们在迁移窗口内可以作为导入来源或 migration residue 临时存在，但不能长期与 `metadata.db` 并存为双真相源。

## SQLite Baseline

Phase 15 的 SQLite 使用约束固定如下：

- 使用标准库 `sqlite3`
- connection 生命周期为“每次公开 API 调用在持有 `repo.lock` 期间创建短连接，用完即关”
- 不共享跨线程 connection
- `journal_mode=DELETE`
- `synchronous=EXTRA` 优先；若 runtime probe 失败，则回退 `FULL`
- `temp_store=MEMORY`
- 默认禁用 WAL
- SQL 只使用对旧 SQLite 版本足够保守的子集
- 不把 SQLite 特性可用性当成跨节点 shared-FS 正确性的替代

## Truth Mapping

Phase 15 的真相层边界固定如下：

| 区域 | Phase 15 目标真相层 | 备注 |
| --- | --- | --- |
| repo config / schema version / default branch | SQLite `repo_meta` | `repo.json` 不再是 steady-state truth |
| branch / tag refs | SQLite `refs` | 文件 ref 退出真相职责 |
| reflog | SQLite `reflog` | 文件 append/truncate rollback 退出主线 |
| txn state / recovery journal | SQLite `txn_log` | 文件 `STATE.json` / `REF_UPDATE.json` 退出主线 |
| visible chunk index | SQLite `chunk_visible` | `MANIFEST + JSONL segment` 退出真相职责 |
| commit/tree/file/blob metadata | SQLite `objects_*` | 保持 object ID 与 payload 语义不变 |
| blob payload bytes | 文件系统 | 继续使用 `objects/blobs/*.data` |
| pack payload bytes | 文件系统 | 继续使用 `chunks/packs/*.pack` |
| detached views / cache | 文件系统 | 非真相，可重建 |
| quarantine / residue | 文件系统 | 调试、隔离、手工清理或后续维护 |

## Phase 15A. SQLite Foundation 与 Bootstrap 切换

### Goal

先建立可靠的 `metadata.db` 基础设施，把 repo bootstrap、open、schema init、PRAGMA 协商和 Tier 1 truth-store 接口落下来，为后续对象元数据迁移提供稳定地基。

### Status

待开始。

### Todo

* [ ] 新增 SQLite metadata 层封装，集中管理 schema init、connection 打开、PRAGMA 协商、capability probe 与版本检查。
* [ ] 为 `synchronous=EXTRA` 加 runtime probe；若不支持，则显式回退到 `FULL`。
* [ ] 定义并实现 `repo_meta`、`refs`、`reflog`、`txn_log`、`chunk_visible` 的 schema、主键、唯一约束与必要索引。
* [ ] 改造 `create_repo()`，让 repo bootstrap 变成“目录骨架 + metadata schema init + initial truth 写入”的单一 metadata transaction。
* [ ] 为 repo open / create / reopen / zip-unzip reopen 补 SQLite happy-path 与 capability fallback 回归。
* [ ] 固化 `metadata.db` 位于 repo root 内、仓库移动路径后可直接 reopen 的回归。

### Checklist

* [ ] `metadata.db` 可以在 Python `3.7-3.14` 与 Windows/macOS/Linux 上用同一接口稳定打开。
* [ ] `EXTRA` 与 `FULL` 的协商逻辑不会改变公开 API 语义，只影响内部 durability 配置。
* [ ] `create_repo()` 完成后，不需要再依赖 `repo.json` / `refs/` / `logs/refs/` 作为 steady-state truth。
* [ ] 仓库 zip/unzip、换路径、换机器后，不需要 repair、attach 或 rebuild 就能直接 reopen。

## Phase 15B. Tier 1 Truth-Store 迁移

### Goal

把 repo meta、refs、reflog、txn log 和 visible chunk index 先切到 SQLite，先收掉最关键的 metadata truth-source 分裂与 chunk lookup 读放大问题。

### Status

待开始。

### Todo

* [ ] 实现旧 `repo.json` / `refs/` / `logs/refs/` / `chunks/index` 到 SQLite Tier 1 表的一次性迁移。
* [ ] 改造 refs / tag / reflog 读写路径，让 steady-state 全部走 SQLite。
* [ ] 改造 chunk lookup / visible index 读路径，让 steady-state 走 `chunk_visible`，不再依赖 `MANIFEST + JSONL segment`。
* [ ] 保留迁移期一致性检查，确保导入后旧 truth-source 不再继续被写入。
* [ ] 在持有 `repo.lock` EX 的前提下完成迁移；失败时要么保留旧格式可读，要么保留新格式已完整落盘。

### Checklist

* [ ] branch/tag/ref/reflog 的线性化点可以明确落在 SQLite transaction commit。
* [ ] `read_range()` / chunk read 不再依赖昂贵的 visible-index 全量 materialization。
* [ ] 迁移失败不会暴露双真相半状态。
* [ ] 迁移成功后，旧文件 ref / reflog / manifest 不再承担 steady-state truth 角色。

## Phase 15C. Tier 2 Object Metadata 全量迁移

### Goal

把 commit/tree/file/blob metadata 全量迁入 SQLite，同时保持 object ID、公开 `oid` / `sha256`、Git 风格 commit/tree OID 与 payload 语义不变。

### Status

待开始。

### Todo

* [ ] 定义 `objects_commits`、`objects_trees`、`objects_files`、`objects_blobs` 的最终 schema。
* [ ] 迁移当前 `objects/commits`、`objects/trees`、`objects/files`、`objects/blobs/*.meta.json` 的 metadata。
* [ ] 改造 `_read_object_payload()`、tree walk、snapshot build、history listing、file identity、verify graph walk 等对象读取路径，使其稳态走 SQLite。
* [ ] 保持 object container 的 canonical bytes / object ID 语义稳定，不因存储 substrate 切换而改变对象身份。
* [ ] 只迁移 blob metadata，不迁移 `objects/blobs/*.data` payload bytes。

### Checklist

* [ ] commit/tree/file/blob metadata 在迁移后不再依赖大量小 JSON 文件。
* [ ] `list_repo_commits()`、`list_repo_tree()`、`read_bytes()`、`snapshot_download()`、merge DAG 遍历等对象路径在语义上不回退。
* [ ] object ID、public `oid` / `blob_id` / `sha256`、Git 风格 commit/tree OID 与当前保持一致。
* [ ] 小文件 commit / history / metadata-heavy listing 的热点相对当前文件协议有明显回收。

## Phase 15D. 读写、恢复、维护链路统一

### Goal

在 Tier 1 / Tier 2 真相层迁移完成后，把所有公开写 API、恢复逻辑、verify、storage overview、GC、history rewrite 与 payload residue 处理统一到新的 SQLite truth-store 上。

### Status

待开始。

### Todo

* [ ] 把 `create_commit()`、`merge()`、branch/tag/reset 等 ref-changing 写路径统一改到“payload publish -> SQLite metadata transaction -> residue cleanup”模型。
* [ ] 把 `gc()`、`squash_history()`、verify、storage overview 改到以 SQLite truth 为准，不再依赖旧文件协议扫描。
* [ ] 用 `txn_log` 取代当前基于 `STATE.json` / `REF_UPDATE.json` 的 steady-state 恢复协议。
* [ ] 将 repo-level 恢复语义收敛为“未提交 metadata 一律 rollback，已提交 metadata 可见，payload residue best-effort cleanup”。
* [ ] 明确旧文件协议残留的 quarantine / cleanup / migration residue 策略，避免和正式真相混淆。

### Checklist

* [ ] ref-changing 路径恢复逻辑比当前更简单，而不是更复杂。
* [ ] verify / diagnose 可以更清楚地区分 reachable corruption、migration residue 与 cache damage。
* [ ] `gc()` / `squash_history()` 在 SQLite truth-store 上仍保持 rollback-only 与可串行化语义。
* [ ] `get_storage_overview()` 的分区统计、建议与实际磁盘布局仍然正确。

## Phase 15E. 回归、验收与切换封板

### Goal

在功能迁移完成后，补齐新的 failpoint、并发、shared-path、zip-unzip、benchmark 与兼容性回归，确保 SQLite truth-store 可以正式替代旧文件协议真相层。

### Status

待开始。

### Todo

* [ ] 以新的 SQLite 线性化点重写 failpoint 回归，至少覆盖 metadata commit 前后、payload publish 后中断、maintenance 路径中断与 reopen recovery。
* [ ] 补齐同进程多线程、同机多进程、并发 branch update、并发 merge、concurrent gc 与读写交错矩阵。
* [ ] 为跨节点 shared mount 保留可选集成测试或手动验收脚本，并明确 supported/unsupported profile。
* [ ] 重跑 `small_batch_commit`、`history_deep_listing`、`merge-heavy`、`full_verify`、`large_upload`、`read_range`、cold/warm download benchmark，对比迁移前后收益。
* [ ] 更新 `quick_verify()` / `full_verify()` / `get_storage_overview()` 的文档、诊断文案与计划文档中的 steady-state layout 说明。
* [ ] 在切换完成后移除旧文件协议 steady-state truth 的写入路径。

### Checklist

* [ ] Phase 15 的公开 API 行为、公开模型和 detached view 语义不回退。
* [ ] 同进程、同机多进程和 shared-path 语义仍满足同一公开口径，或对不满足条件的 shared FS 显式拒绝危险写入模式。
* [ ] 仓库在 zip/unzip、换路径、换机器后仍可直接启用，不需要额外 rebuild、attach、repair 或 sidecar 补全。
* [ ] 旧文件协议真相层已经退出 steady-state 主线，不再制造双真相源。
* [ ] 迁移完成后可以把 Phase 14/15 关闭，并把后续工作留给 payload durability 与更高阶性能项。

## Phase 15 MVP Cut

Phase 15 的最低可接受交付为：

- Phase 15A 完成，`metadata.db` 基础设施和兼容边界稳定可用。
- Phase 15B 完成，Tier 1 truth-store 已全部切到 SQLite。
- Phase 15C 完成，commit/tree/file/blob metadata 已全部切到 SQLite。
- Phase 15D 完成，公开写 API、恢复、verify、GC 和 storage overview 都以 SQLite truth 为准。
- Phase 15E 完成，新的 failpoint / 并发 / zip-unzip / benchmark 回归已补齐。

## Deferred Items

下面这些内容明确不属于 Phase 15：

- 全量 payload bytes 入库
- WAL 默认化
- 去掉 `repo.lock`
- 因 JSON codec / compression 收益而抬高 Python 最低版本
- 为了 benchmark 数字而改动公开路径、公开模型或 rollback-only 语义
