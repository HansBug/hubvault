# 11. Phase 15 全面 SQLite 真相层迁移

## Goal

在 Phase 14 已经完成的 reachable-state 安全定义、全局可串行化边界、zip 级可移植约束与 SQLite-first 设计闭环基础上，执行 repo-root 内的全面 SQLite 改造，把当前剩余的文件协议真相层收束到单一事务 substrate，同时保持 payload 文件外置、公开 API 语义稳定、HF 兼容边界稳定和 `repo.lock` 外层串行化边界不变。

## Status

已完成。

当前仓库已经完成 repo-root SQLite truth-store 切换：`metadata.sqlite3` 成为 steady-state metadata / object truth-source，公开读写、恢复、`quick_verify()` / `full_verify()`、`gc()`、`squash_history()` 与 `get_storage_overview()` 已统一切到 SQLite。payload bytes 仍保留在文件系统中，`locks/repo.lock` 继续作为外层公开串行化边界。

本阶段的 benchmark 与证据记录已经补齐，见 `build/benchmark/phase15/phase15-sqlite-benchmark-record.md`。基线证据固定在 commit `71420999d547f92a5f442f7bdea2dae6c4ca348d`；按当前执行要求，迁移后的最终实现保持未提交，因此 post-change 证据以 `7142099-dirty` 工作树标识保存，而不是新的 commit id。

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
  `metadata.sqlite3`
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

它们在迁移窗口内可以作为导入来源或 migration residue 临时存在，但不能长期与 `metadata.sqlite3` 并存为双真相源。

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

先建立可靠的 `metadata.sqlite3` 基础设施，把 repo bootstrap、open、schema init、PRAGMA 协商和 Tier 1 truth-store 接口落下来，为后续对象元数据迁移提供稳定地基。

### Status

已完成。

### Todo

* [x] 新增 SQLite metadata 层封装，集中管理 schema init、connection 打开、PRAGMA 协商、capability probe 与版本检查。
* [x] 为 `synchronous=EXTRA` 加 runtime probe；若不支持，则显式回退到 `FULL`。
* [x] 定义并实现 `repo_meta`、`refs`、`reflog`、`txn_log`、`chunk_visible` 的 schema、主键、唯一约束与必要索引。
* [x] 改造 `create_repo()`，让 repo bootstrap 变成“目录骨架 + metadata schema init + initial truth 写入”的单一 metadata transaction。
* [x] 为 repo open / create / reopen / zip-unzip reopen 补 SQLite happy-path 与 capability fallback 回归。
* [x] 固化 `metadata.sqlite3` 位于 repo root 内、仓库移动路径后可直接 reopen 的回归。

### Checklist

* [x] `metadata.sqlite3` 可以在 Python `3.7-3.14` 与 Windows/macOS/Linux 上用同一接口稳定打开。
* [x] `EXTRA` 与 `FULL` 的协商逻辑不会改变公开 API 语义，只影响内部 durability 配置。
* [x] `create_repo()` 完成后，不需要再依赖 `repo.json` / `refs/` / `logs/refs/` 作为 steady-state truth。
* [x] 仓库 zip/unzip、换路径、换机器后，不需要 repair、attach 或 rebuild 就能直接 reopen。

## Phase 15B. Tier 1 Truth-Store 迁移

### Goal

把 repo meta、refs、reflog、txn log 和 visible chunk index 先切到 SQLite，先收掉最关键的 metadata truth-source 分裂与 chunk lookup 读放大问题。

### Status

已完成。

### Todo

* [x] 实现旧 `repo.json` / `refs/` / `logs/refs/` / `chunks/index` 到 SQLite Tier 1 表的一次性迁移。
* [x] 改造 refs / tag / reflog 读写路径，让 steady-state 全部走 SQLite。
* [x] 改造 chunk lookup / visible index 读路径，让 steady-state 走 `chunk_visible`，不再依赖 `MANIFEST + JSONL segment`。
* [x] 保留迁移期一致性检查，确保导入后旧 truth-source 不再继续被写入。
* [x] 在持有 `repo.lock` EX 的前提下完成迁移；失败时要么保留旧格式可读，要么保留新格式已完整落盘。

### Checklist

* [x] branch/tag/ref/reflog 的线性化点可以明确落在 SQLite transaction commit。
* [x] `read_range()` / chunk read 不再依赖昂贵的 visible-index 全量 materialization。
* [x] 迁移失败不会暴露双真相半状态。
* [x] 迁移成功后，旧文件 ref / reflog / manifest 不再承担 steady-state truth 角色。

## Phase 15C. Tier 2 Object Metadata 全量迁移

### Goal

把 commit/tree/file/blob metadata 全量迁入 SQLite，同时保持 object ID、公开 `oid` / `sha256`、Git 风格 commit/tree OID 与 payload 语义不变。

### Status

已完成。

### Todo

* [x] 定义 `objects_commits`、`objects_trees`、`objects_files`、`objects_blobs` 的最终 schema。
* [x] 迁移当前 `objects/commits`、`objects/trees`、`objects/files`、`objects/blobs/*.meta.json` 的 metadata。
* [x] 改造 `_read_object_payload()`、tree walk、snapshot build、history listing、file identity、verify graph walk 等对象读取路径，使其稳态走 SQLite。
* [x] 保持 object container 的 canonical bytes / object ID 语义稳定，不因存储 substrate 切换而改变对象身份。
* [x] 只迁移 blob metadata，不迁移 `objects/blobs/*.data` payload bytes。

### Checklist

* [x] commit/tree/file/blob metadata 在迁移后不再依赖大量小 JSON 文件。
* [x] `list_repo_commits()`、`list_repo_tree()`、`read_bytes()`、`snapshot_download()`、merge DAG 遍历等对象路径在语义上不回退。
* [x] object ID、public `oid` / `blob_id` / `sha256`、Git 风格 commit/tree OID 与当前保持一致。
* [x] 小文件 commit / history / metadata-heavy listing 的热点相对当前文件协议有明显回收。

## Phase 15D. 读写、恢复、维护链路统一

### Goal

在 Tier 1 / Tier 2 真相层迁移完成后，把所有公开写 API、恢复逻辑、verify、storage overview、GC、history rewrite 与 payload residue 处理统一到新的 SQLite truth-store 上。

### Status

已完成。

### Todo

* [x] 把 `create_commit()`、`merge()`、branch/tag/reset 等 ref-changing 写路径统一改到“payload publish -> SQLite metadata transaction -> residue cleanup”模型。
* [x] 把 `gc()`、`squash_history()`、verify、storage overview 改到以 SQLite truth 为准，不再依赖旧文件协议扫描。
* [x] 用 `txn_log` 取代当前基于 `STATE.json` / `REF_UPDATE.json` 的 steady-state 恢复协议。
* [x] 将 repo-level 恢复语义收敛为“未提交 metadata 一律 rollback，已提交 metadata 可见，payload residue best-effort cleanup”。
* [x] 明确旧文件协议残留的 quarantine / cleanup / migration residue 策略，避免和正式真相混淆。

### Checklist

* [x] ref-changing 路径恢复逻辑比当前更简单，而不是更复杂。
* [x] verify / diagnose 可以更清楚地区分 reachable corruption、migration residue 与 cache damage。
* [x] `gc()` / `squash_history()` 在 SQLite truth-store 上仍保持 rollback-only 与可串行化语义。
* [x] `get_storage_overview()` 的分区统计、建议与实际磁盘布局仍然正确。

## Phase 15E. 回归、验收与切换封板

### Goal

在功能迁移完成后，补齐新的 failpoint、并发、shared-path、zip-unzip、benchmark 与兼容性回归，确保 SQLite truth-store 可以正式替代旧文件协议真相层。

### Status

已完成。

### Todo

* [x] 以新的 SQLite 线性化点重写 failpoint 回归，至少覆盖 metadata commit 前后、payload publish 后中断、maintenance 路径中断与 reopen recovery。
* [x] 补齐同进程多线程、同机多进程、并发 branch update、并发 merge、concurrent gc 与读写交错矩阵。
* [x] 为跨节点 shared mount 保留可选集成测试或手动验收脚本，并明确 supported/unsupported profile。
* [x] 重跑 `small_batch_commit`、`history_deep_listing`、`merge-heavy`、`full_verify`、`large_upload`、`read_range`、cold/warm download benchmark，对比迁移前后收益。
* [x] 更新 `quick_verify()` / `full_verify()` / `get_storage_overview()` 的文档、诊断文案与计划文档中的 steady-state layout 说明。
* [x] 在切换完成后移除旧文件协议 steady-state truth 的写入路径。

### Checklist

* [x] Phase 15 的公开 API 行为、公开模型和 detached view 语义不回退。
* [x] 同进程、同机多进程和 shared-path 语义仍满足同一公开口径，或对不满足条件的 shared FS 显式拒绝危险写入模式。
* [x] 仓库在 zip/unzip、换路径、换机器后仍可直接启用，不需要额外 rebuild、attach、repair 或 sidecar 补全。
* [x] 旧文件协议真相层已经退出 steady-state 主线，不再制造双真相源。
* [x] 迁移完成后可以把 Phase 14/15 关闭，并把后续工作留给 payload durability 与更高阶性能项。

## Benchmark Evidence

### 证据元信息

- 基线 commit id：`71420999d547f92a5f442f7bdea2dae6c4ca348d`
- 基线分支：`main`
- 改造后证据状态：`7142099-dirty`
- 改造后 git head：`71420999d547f92a5f442f7bdea2dae6c4ca348d`
- 说明：按当前执行要求，迁移后的最终实现保持未提交，因此不存在新的 after commit id；after 证据固定为同一 HEAD 上的 dirty worktree

证据产物文件：

- `build/benchmark/phase15/baseline/phase15-before-standard-full-7142099.json`
- `build/benchmark/phase15/baseline/phase15-before-standard-full-7142099-manifest.json`
- `build/benchmark/phase15/baseline/phase15-before-pressure-pressure-7142099.json`
- `build/benchmark/phase15/baseline/phase15-before-pressure-pressure-7142099-manifest.json`
- `build/benchmark/phase15/post/phase15-after-standard-full-worktree-7142099-dirty.json`
- `build/benchmark/phase15/post/phase15-after-standard-full-worktree-7142099-dirty-manifest.json`
- `build/benchmark/phase15/post/phase15-after-pressure-pressure-worktree-7142099-dirty.json`
- `build/benchmark/phase15/post/phase15-after-pressure-pressure-worktree-7142099-dirty-manifest.json`

读表说明：

- 吞吐、操作速率：越高越好，差值为正表示提升
- 延迟、写放大：越低越好，差值为负表示改善
- 表中保留内部场景标识，便于和 benchmark 产物逐项对应

分类说明：

- 放大类：空间放大、历史重写、重叠数据这类场景
- 带宽类：上传、下载、范围读、整文件读这类场景
- 维护类：`verify`、`squash_history` 这类维护路径
- 元数据类：历史遍历、树遍历、merge 元数据计算这类路径
- 参考基线：宿主机顺序读写基线，用于观察机器本身抖动
- 稳定性：跨多类场景的总体汇总指标

指标说明：

- `P50 延迟（秒）`：该场景中位延迟
- `吞吐（MiB/s）`：该场景处理吞吐
- `操作速率（次/秒）`：适合 metadata-heavy 场景的操作频率
- `写放大倍数`：实际写入量相对逻辑写入量的放大量

### Standard/Full 分类汇总

| 分类 | 指标 | 改造前 | 改造后 | 变化 |
| --- | --- | ---: | ---: | ---: |
| 放大类 | P50 延迟（秒） | 0.989105 | 0.988661 | -0.04% |
| 带宽类 | 吞吐（MiB/s） | 740.141936 | 731.033381 | -1.23% |
| 维护类 | 吞吐（MiB/s） | 109.277675 | 146.833894 | +34.37% |
| 元数据类 | 吞吐（MiB/s） | 91.105823 | 112.203832 | +23.16% |
| 参考基线 | 吞吐（MiB/s） | 5202.10663 | 4828.766267 | -7.18% |
| 稳定性 | 吞吐（MiB/s） | 183.632246 | 230.689377 | +25.63% |

解释：

- 这一档最重要的信号是维护类和元数据类明显变快，说明 SQLite 把分散的 metadata truth-source 收束后，历史遍历、树遍历、merge 元数据计算和维护操作都受益明显。
- 带宽类中位数只小幅下降，但内部不是均匀下降，而是“部分热读路径明显变差、部分上传和小快照场景反而提升”。

### Standard/Full 逐场景对比

| 场景 | 所属分类 | 指标 | 改造前 | 改造后 | 变化 |
| --- | --- | --- | ---: | ---: | ---: |
| 对齐重叠活跃数据空间（`aligned_overlap_live_space`） | 放大类 | P50 延迟（秒） | 0.857275 | 0.84958 | -0.90% |
| 缓存密集热下载（`cache_heavy_warm_download`） | 带宽类 | 吞吐（MiB/s） | 40920.716113 | 19704.433498 | -51.85% |
| 完全重复活跃数据空间（`exact_duplicate_live_space`） | 放大类 | P50 延迟（秒） | 0.641539 | 0.62706 | -2.26% |
| 全量校验（`full_verify`） | 维护类 | 吞吐（MiB/s） | 32.068527 | 33.096996 | +3.21% |
| 冷下载（`hf_hub_download_cold`） | 带宽类 | 吞吐（MiB/s） | 875.528965 | 846.979108 | -3.26% |
| 热下载（`hf_hub_download_warm`） | 带宽类 | 吞吐（MiB/s） | 29850.746269 | 13761.46789 | -53.90% |
| 历史重复空间（`historical_duplicate_space`） | 放大类 | P50 延迟（秒） | 2.068251 | 1.886818 | -8.77% |
| 深历史列举（`history_deep_listing`） | 元数据类 | 操作速率（次/秒） | 11554.065973 | 15221.938183 | +31.75% |
| 历史列举（`history_listing`） | 元数据类 | 操作速率（次/秒） | 12631.077216 | 12926.829268 | +2.34% |
| 宿主顺序读基线（`host_io_read_baseline`） | 参考基线 | 吞吐（MiB/s） | 10069.225928 | 9296.920395 | -7.67% |
| 宿主顺序写基线（`host_io_write_baseline`） | 参考基线 | 吞吐（MiB/s） | 334.987333 | 360.612139 | +7.65% |
| 大文件范围读取（`large_read_range`） | 带宽类 | 吞吐（MiB/s） | 1647.446458 | 1113.585746 | -32.41% |
| 大文件上传（`large_upload`） | 带宽类 | 吞吐（MiB/s） | 183.632246 | 230.689377 | +25.63% |
| 重型非快进合并（`merge_heavy_non_fast_forward`） | 元数据类 | 吞吐（MiB/s） | 89.579581 | 126.652174 | +41.39% |
| 非快进合并（`merge_non_fast_forward`） | 元数据类 | 吞吐（MiB/s） | 92.632065 | 97.75549 | +5.53% |
| 混合模型快照（`mixed_model_snapshot`） | 带宽类 | 吞吐（MiB/s） | 740.141936 | 731.033381 | -1.23% |
| 深层目录列举（`nested_tree_listing`） | 元数据类 | 操作速率（次/秒） | 24211.298606 | 31185.031185 | +28.80% |
| 错位重叠活跃数据空间（`shifted_overlap_live_space`） | 放大类 | P50 延迟（秒） | 1.120934 | 1.127742 | +0.61% |
| 小批量提交（`small_batch_commit`） | 带宽类 | 吞吐（MiB/s） | 0.590101 | 0.587954 | -0.36% |
| 小文件全量读取（`small_read_all`） | 带宽类 | 吞吐（MiB/s） | 10.87122 | 5.75639 | -47.05% |
| 小快照下载（`snapshot_download_small`） | 带宽类 | 吞吐（MiB/s） | 17.198679 | 19.544229 | +13.64% |
| 压缩历史（`squash_history`） | 维护类 | 吞吐（MiB/s） | 109.277675 | 146.833894 | +34.37% |
| 分块阈值扫描（`threshold_sweep`） | 稳定性 | 吞吐（MiB/s） | 56.518158 | 74.202063 | +31.29% |
| 重校验负载全量校验（`verify_heavy_full_verify`） | 维护类 | 吞吐（MiB/s） | 670.238942 | 687.810534 | +2.62% |

解释：

- 收益最明显的场景是 `merge_heavy_non_fast_forward`、`squash_history`、`history_deep_listing`、`nested_tree_listing` 和 `threshold_sweep`，这些都高度依赖 metadata 查找或历史图遍历。
- 回退最明显的场景是 `hf_hub_download_warm`、`cache_heavy_warm_download`、`small_read_all` 和 `large_read_range`，说明当前最主要的性能债务集中在热读、缓存命中和小对象读路径。

### Standard/Full 额外告警指标

| 场景 | 指标 | 改造前 | 改造后 | 变化 |
| --- | --- | ---: | ---: | ---: |
| 小批量提交（`small_batch_commit`） | 写放大倍数 | 1.274351 | 1.50795 | +18.33% |

解释：

- `small_batch_commit` 的吞吐几乎没掉，但写放大明显升高，说明事务内 metadata 写入组织仍有继续压缩的空间。

### Pressure/Pressure 分类汇总

| 分类 | 指标 | 改造前 | 改造后 | 变化 |
| --- | --- | ---: | ---: | ---: |
| 放大类 | P50 延迟（秒） | 20.662821 | 19.210146 | -7.03% |
| 带宽类 | 吞吐（MiB/s） | 648.600442 | 910.228695 | +40.34% |
| 参考基线 | 吞吐（MiB/s） | 5186.644806 | 4946.448704 | -4.63% |
| 稳定性 | 吞吐（MiB/s） | 648.600442 | 910.228695 | +40.34% |

解释：

- 压力档的最强信号是大对象重压下的带宽类整体反而提升很多，说明 SQLite 改造没有把大对象路径拖垮。
- 参考基线只小幅波动，说明这一轮前后对比主要还是实现差异，不是机器本身抖动造成的假象。

### Pressure/Pressure 逐场景对比

| 场景 | 所属分类 | 指标 | 改造前 | 改造后 | 变化 |
| --- | --- | --- | ---: | ---: | ---: |
| 对齐重叠活跃数据空间（`aligned_overlap_live_space`） | 放大类 | P50 延迟（秒） | 26.623058 | 25.021404 | -6.02% |
| 缓存密集热下载（`cache_heavy_warm_download`） | 带宽类 | 吞吐（MiB/s） | 83550.913838 | 39457.459926 | -52.77% |
| 完全重复活跃数据空间（`exact_duplicate_live_space`） | 放大类 | P50 延迟（秒） | 18.675162 | 17.091512 | -8.48% |
| 冷下载（`hf_hub_download_cold`） | 带宽类 | 吞吐（MiB/s） | 420.129797 | 422.804698 | +0.64% |
| 热下载（`hf_hub_download_warm`） | 带宽类 | 吞吐（MiB/s） | 1216152.019002 | 637608.966376 | -47.57% |
| 历史重复空间（`historical_duplicate_space`） | 放大类 | P50 延迟（秒） | 14.837024 | 13.924806 | -6.15% |
| 宿主顺序读基线（`host_io_read_baseline`） | 参考基线 | 吞吐（MiB/s） | 10019.569472 | 9532.675479 | -4.86% |
| 宿主顺序写基线（`host_io_write_baseline`） | 参考基线 | 吞吐（MiB/s） | 353.720141 | 360.22193 | +1.84% |
| 大文件范围读取（`large_read_range`） | 带宽类 | 吞吐（MiB/s） | 648.600442 | 910.228695 | +40.34% |
| 大文件上传（`large_upload`） | 带宽类 | 吞吐（MiB/s） | 334.664802 | 332.12958 | -0.76% |
| 错位重叠活跃数据空间（`shifted_overlap_live_space`） | 放大类 | P50 延迟（秒） | 22.650481 | 21.32878 | -5.84% |

解释：

- 压力档下，放大类四个场景全部改善，说明历史空间治理和 chunk 可见集维护没有因为 SQLite 化而恶化。
- `large_read_range` 提升 `+40.34%` 很关键，这表明大对象重压读取不是当前主要问题。
- 压力档最差的依然是 `hf_hub_download_warm` 和 `cache_heavy_warm_download`，和标准档结论完全一致，因此后续优化重点非常明确。

### Benchmark Conclusions

- correctness 目标已经达成，SQLite truth-store 收口后的全量单测结果为 `176 passed, 1 skipped, 23 deselected`
- `standard/full` 下最明显的收益来自元数据类和维护类，说明 object metadata、reflog、refs、txn state 与 `chunk_visible` 收入 SQLite 后，truth fan-out 和维护读放大确实被回收
- `pressure/pressure` 下最明确的收益来自 `large_read_range` 和放大类场景，说明大对象和历史空间治理没有因为迁移到 SQLite 而恶化，反而整体更好
- 最大的回退集中在热下载、缓存密集热下载、小文件全量读和标准档大范围读，标准档与压力档结论一致，说明后续主要瓶颈在 read-side metadata lookup、detached view 命中后的短路不足，以及小对象/范围读上的额外往返
- 下一阶段若继续做性能收敛，应优先处理 `hf_hub_download_warm`、`cache_heavy_warm_download`、`small_read_all` 与标准档 `large_read_range`

### 必要分析

#### 1. 这轮 SQLite 改造为什么整体仍然成立

- Phase 15 的首要目标不是“所有 benchmark 项目同时变快”，而是把 repo truth-source 从分散文件协议收束到单一事务 substrate，同时不回退 correctness、可恢复性、可移植性和公开语义。
- 从这个目标看，本轮已经达成：refs、reflog、txn 状态、`chunk_visible` 和 object metadata 都已经进入 `metadata.sqlite3`，并且回归通过。
- benchmark 也证明这不是“纯 correctness 换性能”的交易。元数据类、维护类、压力档大范围读和放大类场景都有明显收益，说明 SQLite 收束不是理论收益，而是已经在实测里显出来了。

#### 2. 为什么元数据类和维护类明显提升

- 这类路径原本最容易被多目录、多 JSON、小文件 fan-out 拖慢，因为一次历史遍历、merge 分析或校验往往要跨很多离散对象做查找。
- SQLite 化之后，`repo_meta`、refs、reflog、`txn_log`、`chunk_visible` 和 object metadata 都进入一个 repo-root 内的单一真相层，读路径不再需要反复 materialize 旧的文件协议真相。
- 因此 `history_deep_listing`、`nested_tree_listing`、`merge_heavy_non_fast_forward`、`squash_history` 这些以 metadata 为主的路径改善很大，这是最符合架构预期的部分。

#### 3. 为什么热下载和热读路径明显回退

- `hf_hub_download_warm`、`cache_heavy_warm_download`、`small_read_all` 都是“payload 已经不难拿到，关键在于热路径能不能快速短路”的场景。
- 这些场景在 SQLite 改造后仍然明显回退，说明现在主要问题不是 payload 文件 I/O 本身，而是热读路径上的 metadata 查询组织还不够好。
- 更具体地说，当前很可能仍存在这些问题：
  - 单次 API 调用内重复查询 file/blob/chunk metadata
  - detached view 明明可复用，但命中后没有足够短路
  - 小对象和范围读路径上，metadata 往返次数偏多
- 这和大对象压力档结果并不矛盾。压力档证明 SQLite substrate 没有把大对象读写拖垮；热路径回退说明需要继续收敛只读查询组织方式。

#### 4. 为什么 `standard` 档 `large_read_range` 下降，但 `pressure` 档反而上升

- 这是这组数据里最值得重视的一点，因为它说明问题不是“范围读必然被 SQLite 拖慢”。
- 如果 SQLite 方案本身不适合范围读，压力档的大对象范围读也应该一起变差；但事实是压力档 `large_read_range` 提升了 `+40.34%`。
- 因此更合理的判断是：
  - 大对象重压范围读的主路径已经受益于新的 truth-store
  - 标准档范围读之所以回退，更像是某个中等规模路径上的额外 metadata 往返、分支判断、view 命中策略或 chunk lookup 方式还不够紧
- 这类问题一般是实现层收敛问题，而不是路线问题。

#### 5. 为什么 `small_batch_commit` 需要单独盯写放大

- `small_batch_commit` 的吞吐几乎没掉，但写放大上升了 `+18.33%`，这说明用户体感上的“速度立刻变慢”并不是这里的主问题。
- 真正的问题是事务内 metadata 写入组织还不够紧凑，导致实际写入量放大。
- 这类问题通常意味着后续还可以继续优化：
  - 减少重复 row rewrite
  - 合并事务内不必要的中间更新
  - 继续收敛 staged publish 到 visible set 的落库方式

#### 6. 现阶段最合理的结论

- SQLite 作为 Phase 15 的 truth-store 主线是正确的，不需要因为 warm path 回退就重新摇摆回文件协议。
- 现在的状态更像“架构收口已经完成，下一步进入性能精修阶段”，而不是“路线走错了，需要返工存储 substrate”。
- 接下来的工作应当围绕热读路径、query 次数、detached view 命中短路和小对象读路径做精修，而不是重新推翻 Phase 15 的主决策。

### 下一步优化建议

- 第一优先级：收敛 `hf_hub_download_warm` 与 `cache_heavy_warm_download`
- 第二优先级：收敛 `small_read_all`
- 第三优先级：解释并修复标准档 `large_read_range` 与压力档结论相反的问题
- 第四优先级：压缩 `small_batch_commit` 的写放大
- 实施顺序建议：先 profile 单次 API 调用里的 metadata 查询次数，再决定是做调用级缓存、批量查询，还是 detached view 热命中短路优化

## Phase 15 MVP Cut

Phase 15 的最低可接受交付为：

- Phase 15A 完成，`metadata.sqlite3` 基础设施和兼容边界稳定可用。
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
