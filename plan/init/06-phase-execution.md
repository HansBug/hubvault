# 06. 分阶段执行计划

## 总体策略

执行顺序遵循一个原则：先交付最小可用、可验证、可回归的本地仓库核心，再逐步扩充大文件、维护和性能能力。

## 当前状态

截至当前仓库实现状态：

- Phase 0 的协议冻结、测试制度、repo 自包含/可搬迁约束、HF 风格路径与文件元数据语义已经落入 `plan/init/`、`AGENTS.md` 与公开源码接口。
- Phase 1 的 MVP 公开模块 `hubvault.api`、`hubvault.errors`、`hubvault.models`、`hubvault.operations`、`hubvault.repo` 已经落地。
- 当前 MVP 已支持 `create_repo -> create_commit -> refs -> list -> list_repo_commits -> read -> hf_hub_download -> snapshot_download -> reset_ref -> quick_verify` 的闭环。
- 当前单元测试已经按 `hubvault/` 模块树拆分为对应的 `test/**/test_<module>.py` 文件，不再依赖单一 MVP 汇总测试文件。
- 当前回归基线应至少包括 `make unittest` 与 `make rst_auto`，并且 Phase 2 公开集成回归已补到 `test/test_phase2.py`。
- 当前仓库并发与恢复基线已经收敛为 `fasteners.InterProcessReaderWriterLock` + rollback-only 恢复：多个 reader 可并发，writer 独占；中断写事务只回滚，不继续补完。

优先级排序如下：

1. 公开 API、对象模型、事务协议
2. whole-file blob MVP
3. refs / 历史 / 快照增强
4. chunk / pack / range read
5. merge / full verify / GC / compact
6. 性能优化与发布

## Phase 0. 规范冻结与脚手架

### Goal

冻结格式、API 名称、异常模型和测试制度，确保后续实现不会频繁推翻协议。

### Status

已完成。

### Todo

* [x] 冻结 `plan/init` 中的对象模型、目录布局、事务状态机和 API 命名。
* [x] 冻结 repo root 下 `refs/`、`logs/refs/`、`objects/`、`txn/`、`locks/`、`cache/`、`quarantine/`、`chunks/` 的组织结构与命名规则。
* [x] 明确 `HubVaultApi`、`CommitOperation*`、`RepoInfo`、`CommitInfo`、`GitCommitInfo`、`RepoFile`、`RepoFolder`、`VerifyReport` 的公开字段与职责边界。
* [x] 固化 `AGENTS.md` 中的测试制度、公开表面约束和回归要求。
* [x] 冻结“repo root 自包含且可整体搬迁/归档恢复”的格式红线，禁止把真相写到仓库外部。
* [x] 冻结 HF 兼容文件元数据语义，明确公开 `oid` / `blob_id` / `sha256` 与内部对象 ID 的区别，并规定公开 `sha256` 使用裸 hex。
* [x] 冻结 HF commit 模型分工，`CommitInfo` 用于 commit 创建结果，`GitCommitInfo` 用于 commit 历史列表，不再混出本地 hybrid 公开模型。
* [x] 审查现有单元测试策略，确保测试对象只覆盖 `hubvault/` 公开源码行为，不把文档本身作为单测对象。
* [x] 冻结“读取视图只读且可重建、真正修改只能走 commit API”的数据安全语义。

### Checklist

* [x] `plan/init` 文档与当前仓库骨架状态一致，没有假设已存在的实现。
* [x] 所有 Phase 都包含可执行范围、Todo 和 Checklist。
* [x] 新增测试只依赖公开文件和公开表面，不使用 private / protected 细节。
* [x] 自包含/可搬迁要求已经在范围、格式、API 和测试路线图中明确落地。
* [x] 下载路径保真和文件 `oid` / `sha256` 语义已经写入 API 与存储设计。
* [x] 仓库内部组织结构已经细化到目录、文件名和分片规则级别。
* [x] 单元测试只覆盖 `hubvault/` 源码路径下的公开行为。
* [x] 读取视图与正式对象的隔离语义已经写入缓存组织、API 和一致性设计。
* [x] `make unittest` 通过。

## Phase 1. MVP 仓库核心

### Goal

做出第一个真正可用的本地版本仓库 MVP，先只支持 whole-file blob。

### Status

已完成。

### Todo

* [x] 新增 `hubvault/errors.py`，定义公开异常类型。
* [x] 新增 `hubvault/models.py` 与 `hubvault/operations.py`，定义公开 dataclass 和 `CommitOperation*`。
* [x] 新增 `hubvault/api.py` 与 `hubvault/repo.py`，提供 `HubVaultApi` 公开入口。
* [x] 实现 repo 初始化、打开、`repo_info()` 与默认分支解析。
* [x] 按固定组织结构创建 `FORMAT`、`repo.json`、`refs/`、`logs/refs/`、`objects/`、`txn/`、`locks/`、`cache/`、`quarantine/`。
* [x] 实现 whole-file blob 存储、commit/tree/file/blob 对象写入和读取。
* [x] 实现 `create_commit()`、`get_paths_info()`、`list_repo_tree()`、`list_repo_files()`、`list_repo_commits()`、`open_file()`、`read_bytes()`、`hf_hub_download()`。
* [x] 实现 `reset_ref()` 与最小 `quick_verify()`。
* [x] 保证所有持久化元数据不包含宿主绝对路径，且仓库移动后可以直接重新打开。
* [x] 为每个文件计算并持久化公开 `oid` / `sha256` / `etag`。
* [x] 让 `hf_hub_download()` 返回以 repo 相对路径结尾的可读文件路径。
* [x] 让 `open_file()` 只返回只读句柄，`hf_hub_download()` 只返回与 repo 真相隔离的用户视图路径。
* [x] 为上述能力补齐只经由公开 API 的单元测试和必要的临时目录集成测试。

### Checklist

* [x] 可以在空目录中初始化仓库并生成 `FORMAT`、`repo.json`、`refs/`、`objects/`、`txn/`、`locks/`。
* [x] `refs/`、`logs/refs/`、`objects/`、`txn/`、`cache/` 的内部组织符合已冻结命名规则。
* [x] 可以提交新增文件并通过公开 API 读回内容。
* [x] 可以列出目录树和文件清单。
* [x] 可以通过公开 API 列出当前 revision 的 commit 历史。
* [x] 可以将分支回退到历史 commit。
* [x] `quick_verify()` 能在正常仓库上返回成功报告。
* [x] 仓库关闭后整体移动路径，再次打开仍能读取、回滚和校验。
* [x] 公开文件信息中可以拿到 HF 兼容 `oid` / `sha256`，其中 `sha256` 为裸 64 位 hex。
* [x] `hf_hub_download()` 返回路径以 repo 原始相对路径结尾。
* [x] 用户删除或改写下载结果后，不会影响正式对象，再次读取时可以重建视图。
* [x] `make unittest` 通过。

## Phase 2. 可用性增强

### Goal

在不引入 chunk/pack 的前提下，把仓库从“能用”推进到“日常可用”。

### Status

已完成。

### Todo

* [x] 实现 `create_branch()`、`delete_branch()`、`create_tag()`、`delete_tag()`、`list_repo_refs()`。
* [x] 实现公开 reflog 查询模型 `ReflogEntry` 与 `list_repo_reflog()`。
* [x] 实现 `upload_file()`、`upload_folder()`、`delete_file()`、`delete_folder()`。
* [x] 实现 `snapshot_download()`，支持 repo 内缓存快照和外部 `local_dir` 导出。
* [x] 增强 `quick_verify()` 输出，增加 snapshot 视图、锁目录和异常 `txn/` 条目的诊断。
* [x] 增加仓库打包/解包恢复后的公开 API 回归用例。
* [x] 增加 `snapshot_download()` 与 `hf_hub_download(local_dir=...)` 的路径保真回归。
* [x] 增加“删除/污染用户视图后重新下载可恢复，repo 真相不变”的公开 API 回归。
* [x] 增加公开 API 的用例测试，覆盖 refs、reflog、便捷上传/删除、快照缓存和回滚。
* [x] 新增 `test/test_phase2.py`，覆盖 Phase 2 的真实全周期使用场景。
* [x] 用成熟第三方 RW 文件锁替换自造锁协议，并补上跨进程 reader/writer 阻塞回归。
* [x] 将中断写事务的恢复策略固定为 rollback-only，不再继续补完未完成写入。

### Checklist

* [x] branch/tag 生命周期通过公开 API 可完整操作。
* [x] 目录上传与删除行为不依赖内部 helper。
* [x] `snapshot_download()` 产出的目录内容与目标 revision 一致。
* [x] reflog 至少能支持审计与恢复诊断。
* [x] 仓库归档恢复后不需要任何外部 sidecar 状态即可继续工作。
* [x] 外部导出模式下仍能拿到与 repo 相对路径一致的文件路径后缀。
* [x] 快照目录和单文件下载目录都与 repo 真相隔离，污染后可重建。
* [x] 读写并发语义已经收敛为“纯读并发、写独占、写时阻塞其余读写”。
* [x] 中断写事务在恢复后等效于未发生，不会被继续推进到完成状态。
* [x] `make unittest` 通过。

## Phase 3. 大文件引擎

### Goal

补齐 chunked file、pack 和 range read，使仓库真正适合中大型模型产物。

### Todo

* [ ] 新增 `chunk_store.py`、`pack_store.py`、`index_store.py`。
* [ ] 引入 `storage_kind="chunked"` 和 chunk 元信息模型。
* [ ] 实现 append-only pack 写入与 `MANIFEST` 管理。
* [ ] 实现 `read_range()` 与 `upload_large_folder()`。
* [ ] 增加 chunk/hash、pack 截断、索引查找和范围读取测试。
* [ ] 为大文件补齐 HF 风格 LFS 兼容 `oid` / `sha256` / `pointer_size` 语义。

### Checklist

* [ ] 大文件可以通过 chunk/pack 存储并稳定读回。
* [ ] `read_range()` 在大文件上可工作且不需要重组全量文件。
* [ ] pack/manifest 更新遵守事务发布原则。
* [ ] 旧的 whole-file blob 仓库仍可兼容读取。
* [ ] chunk/pack 引入后仍不破坏仓库整体搬迁与归档恢复能力。
* [ ] 大文件公开元数据与 HF `RepoFile.blob_id + lfs.sha256` 语义对齐。
* [ ] `make unittest` 通过。

## Phase 4. 一致性与维护能力

### Goal

补齐 merge、full verify、GC、compact 和保留策略，让仓库具备长期运行能力。

### Todo

* [ ] 实现 `merge()` 和结构化冲突结果。
* [ ] 实现 `full_verify()`，覆盖 chunk、pack、manifest 和逻辑 hash。
* [ ] 实现 mark-sweep `gc()` 与 `quarantine/`。
* [ ] 实现 `compact()` 和 pack/索引段合并。
* [ ] 实现 reflog 保留窗口、pin 与历史保留策略。
* [ ] 增加故障注入测试，覆盖崩溃恢复和回收安全边界。

### Checklist

* [ ] merge 冲突通过公开结果对象返回，而不是暴露内部工作区。
* [ ] `full_verify()` 能定位损坏对象和范围。
* [ ] GC 不会删除任何可达对象。
* [ ] compact 只在新 pack 和新索引发布后才删除旧数据。
* [ ] GC/compact 后仓库仍然保持自包含和可搬迁。
* [ ] `make unittest` 通过。

## Phase 5. 性能、文档与发布

### Goal

在协议正确性稳定后，再做原生加速、构建发布和用户文档完善。

### Todo

* [ ] 评估可选原生加速模块，例如 `blake3`、`zstd`、`fastcdc`。
* [ ] 增加 benchmark 和跨平台性能基线。
* [ ] 完善公开 API 文档、MVP 教程和恢复/诊断文档。
* [ ] 视需要扩展 CLI，但保持其为公开 API 的薄封装。
* [ ] 跑通 `make package`、必要时跑 `make build` 与 `make test_cli`。

### Checklist

* [ ] 性能优化不改变格式与公开语义。
* [ ] 文档示例全部走公开 API。
* [ ] 打包产物和基础安装路径可验证。
* [ ] 对 Python 3.7-3.14 与主要平台的兼容性假设有回归证据。
* [ ] `make unittest` 以及相关发布回归通过。
