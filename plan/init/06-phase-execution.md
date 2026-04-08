# 06. 分阶段执行计划

## 总体策略

执行顺序遵循一个原则：先交付最小可用、可验证、可回归的本地仓库核心，再逐步扩充大文件、维护和性能能力。

在当前 Phase 0-4 已经落地的前提下，后半程不再把“功能补齐、对拍、异常安全、性能和文档交付”混成一个大阶段，而是按下面顺序拆开推进：

1. 先补 `merge()` 本体与冲突模型
2. 再与真实 `git` / `git-lfs` / `huggingface_hub` 做行为对拍
3. 再补极端场景与故障注入测试，把“最坏等效于本次操作从未发生过”压实
4. 然后再做性能基线与可选优化
5. 最后统一收尾文档、README、教程与交付检查

## 当前状态

截至当前仓库实现状态：

- Phase 0 的协议冻结、测试制度、repo 自包含/可搬迁约束、HF 风格路径与文件元数据语义已经落入 `plan/init/`、`AGENTS.md` 与公开源码接口。
- Phase 1 的 MVP 公开模块 `hubvault.api`、`hubvault.errors`、`hubvault.models`、`hubvault.operations`、`hubvault.repo/` 已经落地。
- 当前 MVP 已支持 `create_repo -> create_commit -> refs -> list -> list_repo_commits -> read -> hf_hub_download -> snapshot_download -> reset_ref -> quick_verify` 的闭环。
- 当前单元测试已经按 `hubvault/` 模块树拆分为对应的 `test/**/test_<module>.py` 文件，不再依赖单一 MVP 汇总测试文件。
- 当前回归基线应至少包括 `make unittest` 与 `make rst_auto`，并且 Phase 2 公开集成回归已补到 `test/test_phase2.py`。
- 当前仓库并发与恢复基线已经收敛为 `fasteners.InterProcessReaderWriterLock` + rollback-only 恢复：多个 reader 可并发，writer 独占；中断写事务只回滚，不继续补完。
- 当前 Phase 3 已经落地 `hubvault/storage/` 大文件引擎与 `test/test_phase3.py` 集成回归，并把 `hubvault/repo.py` 包化为 `hubvault/repo/`。
- 当前 Phase 3 已补齐阈值边界回归，明确验证“只有大小大于等于 `large_file_threshold` 的文件才进入 chunked storage，小文件保持 whole-file blob”。
- 当前 Phase 4 已经落地 `full_verify()`、`get_storage_overview()`、`gc()`、`squash_history()` 与对应公开模型，并补上 `test/test_phase4.py` 全周期维护回归。
- 当前 Phase 5 已经落地 `merge()`、`MergeConflict`、`MergeResult`、merge DAG 历史遍历与 `test/test_phase5.py` 集成回归，并明确把冲突结果收敛成结构化返回而不是半提交异常状态。
- 当前剩余工作会从原单一 Phase 5 继续拆成后续四个顺序 phase，分别处理真实对拍、异常安全、性能与文档交付，避免把 correctness 验证与性能/文档收尾混做。

优先级排序如下：

1. 公开 API、对象模型、事务协议
2. whole-file blob MVP
3. refs / 历史 / 快照增强
4. chunk / pack / range read
5. full verify / 空间画像 / GC / 历史压缩
6. merge / 冲突模型
7. `git` / `git-lfs` / `huggingface_hub` 对拍
8. 异常测试 / 故障注入 / 极端场景安全
9. 性能基线 / 可选优化
10. 文档 / README / 教程 / 交付收尾

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
* [x] 新增 `hubvault/api.py` 与 `hubvault/repo/`，提供 `HubVaultApi` 公开入口。
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

### Status

已完成。

### Todo

* [x] 新增 `hubvault/storage/chunk.py`、`hubvault/storage/pack.py`、`hubvault/storage/index.py`，并通过 `hubvault/storage/__init__.py` 统一导出。
* [x] 引入 `storage_kind="chunked"` 和 chunk 元信息模型。
* [x] 实现 append-only pack 写入与 `MANIFEST` 管理。
* [x] 实现 `read_range()` 与 `upload_large_folder()`。
* [x] 增加 chunk/hash、pack 截断、索引查找和范围读取测试。
* [x] 为大文件补齐 HF 风格 LFS 兼容 `oid` / `sha256` / `pointer_size` 语义。
* [x] 将 `hubvault/repo.py` 调整为 `hubvault/repo/` 包结构，保留 `hubvault.repo` 导入入口。
* [x] 增加阈值边界回归，验证“小于阈值不 chunk、等于阈值会 chunk、大于阈值会 chunk”。

### Checklist

* [x] 大文件可以通过 chunk/pack 存储并稳定读回。
* [x] `read_range()` 在大文件上可工作且不需要重组全量文件。
* [x] pack/manifest 更新遵守事务发布原则。
* [x] 旧的 whole-file blob 仓库仍可兼容读取。
* [x] chunk/pack 引入后仍不破坏仓库整体搬迁与归档恢复能力。
* [x] 大文件公开元数据与 HF `RepoFile.blob_id + lfs.sha256` 语义对齐。
* [x] chunk 使用判定与 `large_file_threshold` 语义一致，不会把不满足条件的小文件误写入 pack。
* [x] `make unittest` 通过。

## Phase 4. 维护、空间治理与历史压缩

### Goal

补齐长期运行所需的维护与空间治理能力：完整校验、空间画像、安全 GC、pack/索引清理，以及“把某个 commit 之前的历史压缩后再回收旧数据”的显式历史重写能力。

### Status

已完成。

### Todo

* [x] 实现 `full_verify()`，覆盖 refs、commit/tree/file/blob、chunk、pack、manifest 和逻辑 hash。
* [x] 实现公开空间画像 API，输出仓库总体占用、各目录/各数据类型占用、可安全释放建议和主要阻塞项。
* [x] 实现 mark-sweep `gc()` 与 `quarantine/`，并能输出 dry-run / 实删报告。
* [x] 实现受控历史压缩 API，可把指定 commit 之前的历史压缩后再执行回收。
* [x] 将 refs 保留语义与 `gc()`、历史压缩联动，避免“看起来压缩了、实际上旧对象仍被保留”，并把阻塞 refs 明确报告给调用方。
* [x] 增加集成测试，覆盖 full verify、空间画像、历史压缩后回收、以及回收前后读取正确性。

### Checklist

* [x] `full_verify()` 能定位损坏对象、损坏 pack/索引和受影响范围。
* [x] 用户可以直接拿到仓库总占用与分项占用，并能据此判断“删缓存、做 GC、做历史压缩”各自能释放什么空间。
* [x] GC 不会删除任何可达对象，也不会在中断后留下半删半不删状态。
* [x] 历史压缩后，指定边界之前的旧历史可变为不可达并被后续 GC 安全清理。
* [x] `squash_history()` 会显式报告仍然阻塞历史释放的其他 refs，避免误判可回收空间。
* [x] Phase 4 的空间治理能力不会破坏仓库自包含、可搬迁和公开 API 读取语义。
* [x] `make unittest` 通过。

## Phase 5. merge

### Goal

先补齐版本控制核心中最后一个大的写路径能力：`merge()` 本体、三方 tree merge 规则和结构化冲突模型，同时继续遵守当前对象协议、事务协议与 rollback-only 恢复红线。

### Status

已完成。

### Todo

* [x] 冻结 `merge()` 的公开 API 形状，尽量贴近 Git/HF 用户能理解的语义，同时删除没有真实行为的兼容占位参数。
* [x] 实现首版三方 tree merge，覆盖 `target revision`、`source revision` 与 merge-base 自动解析。
* [x] 明确并实现首版冲突模型，至少覆盖同路径双改、增删冲突、文件/目录冲突、二进制大文件冲突。
* [x] 让 merge 复用现有事务发布、reflog 记录与 rollback-only 恢复链路，确保“要么产生一个新 merge commit，要么什么都没发生”。
* [x] 增加 merge commit、快进、非快进、冲突返回等公开 API 与集成回归。
* [x] 在 `plan/init/04-api-compat.md` 中同步记录 merge 与 Git/HF 的对齐结论及最小必要偏差。

### Checklist

* [x] merge commit 仍使用现有 commit/tree/file/chunk 对象协议，不引入新的真相源。
* [x] 冲突不会写入半成品 ref，也不会污染任何已提交对象。
* [x] 快进、非快进和冲突三类结果都能通过公开 API 稳定区分。
* [x] merge 相关回归覆盖普通小文件、chunked 大文件和 branch/tag 组合场景。
* [x] `make unittest` 通过。

## Phase 6. 对拍

### Goal

在 merge 本体落地后，用真实 `git`、`git-lfs` 和 `huggingface_hub` 行为做系统对拍，证明 `hubvault` 的 VCS 与公开 API 语义不只是“内部自洽”，而是对外部主流基准也成立。

### Status

未开始。

### Todo

* [ ] 建立 `hubvault` vs `git` 的行为对拍矩阵，覆盖 commit DAG、branch/tag、reset、tree/list、历史遍历与 merge 结果。
* [ ] 建立 `hubvault` vs `git-lfs` 的文件行为对拍，覆盖大文件身份元数据、阈值边界、下载路径后缀保真与对象哈希语义。
* [ ] 建立 `hubvault` vs `huggingface_hub` 的公开 API 对拍，覆盖 `get_paths_info()`、`list_repo_tree()`、`list_repo_commits()`、`hf_hub_download()`、`snapshot_download()` 等已实现表面。
* [ ] 将可离线复现的 `git` / `git-lfs` 对拍纳入常规或条件回归，把需要联网的 HF 实测整理成可选或夜间基线。
* [ ] 把经过确认的最小必要偏差回写到 `plan/init/04-api-compat.md`、`README.md` 与公开 docstring。
* [ ] 对拍结果不仅校验“能否调用成功”，还要校验返回结构、关键字段和值语义。

### Checklist

* [ ] 对拍结论能明确说明哪些行为已经严格对齐，哪些行为属于有文档记录的最小偏差。
* [ ] `oid` / `blob_id` / `sha256` / size / path suffix 等用户可见文件语义有实测证据支撑。
* [ ] 历史列表、refs、下载和快照行为都有真实 VCS/HF 基线可回归。
* [ ] 对拍套件不会回退去依赖 private / protected 内部实现。
* [ ] `make unittest` 与相应对拍回归通过。

## Phase 7. 异常测试

### Goal

系统化模拟极端场景、损坏中间态和中断写入，确保仓库真相永远不被半写状态污染；最坏结果只允许等效于“本次操作从未发生过”，而不是留下任何介于“成功提交”和“从未发生过”之间的暧昧状态。

### Status

未开始。

### Technical Focus

这一阶段不只做“抛异常能报错”式测试，而是要直接验证事务线性化边界、对象发布边界和用户可观测恢复语义。

故障注入的技术手段规划如下：

- 通过子进程执行公开 API，并用受控 failpoint 在 `flush/fsync`、对象发布、`os.replace(ref)`、reflog 追加、`MANIFEST` 切换等关键点主动触发 `RuntimeError`、`OSError`、`KeyboardInterrupt` 或直接 `os._exit(...)`
- 对 pack/index/manifest、txn 元数据和 cache 视图构造“只写了一半”的预制损坏夹具，然后只通过重新打开仓库和公开 API 观察恢复结果
- 对跨进程读写锁使用真实多进程阻塞/中断场景，而不是 mock 锁对象
- 对需要模拟磁盘层失败的场景，优先注入精确的 `OSError(errno.ENOSPC)`、`PermissionError`、`InterruptedError`，而不是笼统 `except Exception`

这一阶段计划覆盖的代表性异常矩阵如下：

- 提交路径：`create_commit()` 在写 blob/file/tree/commit、发布对象、更新 ref、写 reflog、删除事务目录前后的中断
- merge 路径：`merge()` 在 merge-base 解析后、冲突判定后、生成 merge commit 前后、更新目标 ref 前后的中断
- refs 路径：`reset_ref()`、`create_branch()`、`delete_branch()`、`create_tag()`、`delete_tag()` 在 ref 切换与 reflog 记录之间的中断
- 大文件路径：chunk 写入中断、pack append 中断、index/manifest 切换中断、阈值边界文件在异常下不得被错误 chunk 化
- 维护路径：`full_verify()` 面对损坏 pack/index/manifest、`gc()`/`squash_history()` 在 live pack 重写和发布中的中断
- 只读视图路径：`hf_hub_download()` / `snapshot_download()` 产物被删改、替换成目录/文件/坏 symlink 后的重建
- 可搬迁路径：中断后直接 `mv` 仓库、打包/解包恢复，再重新打开并验证主状态仍一致
- 并发路径：writer 崩溃时 reader/writer 阻塞释放、长读期间写阻塞、写锁持有者异常退出后的后续恢复

这一阶段的核心断言也固定如下：

- 当前 head、branch/tag 指向、tree/list/read 结果必须仍然等效于“本次写操作从未发生过”，或者已经完整成功
- 已提交版本的字节内容、大小、`oid`、`blob_id`、`sha256` 不得发生漂移
- 新写到一半的对象即使遗留为孤儿，也必须不可达且不会污染主状态；后续可由 `gc()` 安全清理
- `quick_verify()` / `full_verify()` 必须能把异常态解释成明确问题，而不是沉默吞掉
- 用户视图损坏只影响视图本身，不影响正式对象，可通过重新下载/导出恢复

### Todo

* [ ] 建立 failpoint 目录与统一注入协议，明确每个公开写 API 可触发的故障点名称、触发时机和预期结果。
* [ ] 为 `create_commit()` 增加阶段性故障注入测试，至少覆盖写对象前、对象发布后/ref 更新前、ref 更新后/提交标记前、reflog 追加前后、事务清理前后。
* [ ] 为 `merge()` 增加与 `create_commit()` 同等级别的阶段性故障注入测试，并显式覆盖快进 merge、非快进 merge 和冲突 merge。
* [ ] 为 refs 操作增加异常测试，覆盖 branch/tag 创建删除、`reset_ref()` 和 reflog 之间的原子性。
* [ ] 为大文件写路径增加异常测试，覆盖 chunk append、pack flush、index 发布、manifest 切换、阈值边界文件误分流防护。
* [ ] 为维护路径增加异常测试，覆盖 `gc()` live pack 重写、`squash_history()` 历史重写与阻塞 ref 分析中的中断恢复。
* [ ] 为用户视图和快照缓存增加破坏性测试，覆盖删除、截断、追加脏数据、替换为目录、替换为坏链接后的重建。
* [ ] 为 repo 可搬迁性增加异常后回归，覆盖中断后直接搬迁目录、打包/解包恢复再重开。
* [ ] 为跨进程并发增加异常回归，覆盖持写锁进程崩溃后锁释放、阻塞 reader/writer 恢复和只读并发不互相阻塞。
* [ ] 为校验与诊断接口增加异常态断言，确保 warning / error / blocking refs / quarantined objects 等结果可解释且稳定。
* [ ] 明确区分“允许 API 失败但仓库主状态必须等效于从未发生过”的场景与“必须自动恢复成功”的场景，并把期望写进测试名称和 pydoc。
* [ ] 对所有异常态补充恢复指南文档，说明哪些情况由系统自动回滚，哪些需要用户显式处理。

### Checklist

* [ ] 任意中断都不会让 `refs/` 指向半成品提交，也不会破坏任何已提交对象。
* [ ] 最坏结果等效于“本次操作从未发生过”，不存在第三种半提交状态。
* [ ] 损坏的用户视图、快照缓存或临时目录不会被误判成正式仓库数据损坏。
* [ ] 半写 pack/index/manifest 等异常态能够被识别、隔离或回滚，而不是悄悄进入主状态。
* [ ] 异常测试在三平台上至少保有可运行的核心子集。
* [ ] `make unittest` 通过。

## Phase 8. 性能

### Goal

在语义、对拍和异常安全都稳定之后，再建立正式性能基线并做可选优化，避免为了吞吐量引入协议漂移或隐藏一致性风险。

### Status

未开始。

### Todo

* [ ] 建立公开场景性能基线，覆盖小文件提交/读取、chunked 大文件提交/范围读取、快照导出、历史遍历、校验、GC 与历史压缩。
* [ ] 在不改变磁盘协议和公开语义的前提下，识别热点并评估 hash、压缩、chunk 规划与索引查找等优化点。
* [ ] 评估可选依赖 `blake3`、`zstd`、`fastcdc` 等的收益与兼容成本，确保没有它们时仍保持完全正确。
* [ ] 为性能回归增加固定输入规模和结果记录，避免“感觉更快”式优化。
* [ ] 明确区分默认路径与可选加速路径，确保 Python 3.7-3.14 与三平台兼容红线不被突破。
* [ ] 针对 Phase 3 大文件引擎增加“何时 chunk、何时 whole-file 更优”的基线分析，避免不必要的 chunk 化。

### Checklist

* [ ] 性能优化前后公开 API 行为、存储格式和事务语义保持不变。
* [ ] 至少一组可重复 benchmark 能展示当前瓶颈与优化收益。
* [ ] 可选原生加速是纯增益项，不成为正确性与可安装性的前置条件。
* [ ] 小文件路径不会因为追求大文件性能而出现明显回退。
* [ ] `make unittest` 与性能基线回归通过。

## Phase 9. 文档、README 与教程

### Goal

在前述功能、对拍和安全结论稳定后，统一收尾用户文档、README、教程与交付检查，让外部使用者看到的公开说明和真实实现完全一致。

### Status

未开始。

### Todo

* [ ] 重写 README 的定位、快速开始、能力矩阵和与 `huggingface_hub` / `git-lfs` 的关系说明，确保内容与 Phase 0-8 的真实实现一致。
* [ ] 补齐公开 API 文档、docstring 示例、MVP 教程、merge 使用教程、异常恢复与空间治理教程。
* [ ] 所有示例都直接展示完整流程、真实输出形状和公开返回模型，不再只引用内部说明。
* [ ] 为常见真实场景编排端到端教程，包括初始化仓库、提交多个版本、分支/merge、下载、校验、GC/历史压缩与异常后恢复。
* [ ] 同步记录对拍结论、最小必要偏差和已知限制，避免用户误以为与 HF/Git 完全等价。
* [ ] 在文档收尾阶段跑通 `make rst_auto`、`make package`，必要时补 `make build` 与 `make test_cli`，确保交付面一致。

### Checklist

* [ ] README、API 文档和教程与当前代码行为一致，没有未来时伪实现。
* [ ] 文档示例全部走公开 API / 公开 CLI，不依赖 private / protected 内容。
* [ ] 教程覆盖正常路径、恢复路径和空间治理路径。
* [ ] 关键示例中的路径、哈希、commit/refs 输出形状与真实实现一致。
* [ ] `make rst_auto` 和相关交付回归通过。
