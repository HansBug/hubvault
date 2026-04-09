# 06. 分阶段执行计划

## 总体策略

执行顺序遵循一个原则：先交付最小可用、可验证、可回归的本地仓库核心，再逐步扩充大文件、维护和性能能力。

在当前 Phase 0-11 已经形成稳定基线的前提下，后半程不再把“功能补齐、对拍、异常安全、性能、优化技术引入、文档交付与后续性能演进”混成一个大阶段，而是按下面顺序拆开推进：

1. 先补 `merge()` 本体与冲突模型
2. 再补基于公开 API 的 Git-like 本地 CLI
3. 再与真实 `git` / `git-lfs` / `huggingface_hub` 做行为对拍
4. 再补极端场景与故障注入测试，把“最坏等效于本次操作从未发生过”压实
5. 然后先做性能基线，把当前真实瓶颈和空间行为量出来
6. 再只引入那些 benchmark 已证明值得、且不破坏协议的优化技术，并做前后对比
7. 再统一收尾文档、README、教程与交付检查
8. 然后扩充 benchmark 体系，把带宽、metadata、amplification、稳定性和环境元数据口径补完整
9. 最后只围绕扩容 benchmark 已证明的热点做时间路径收敛，避免重新回到“靠感觉优化”

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
- 当前 Phase 6 已经落地 `hubvault` / `hv` CLI、全局 `-C`、`init/status/branch/tag/log/ls-tree/commit/merge/reset/download/snapshot/verify` 命令，以及 `test/entry/test_*.py` 与 `test/test_phase6.py` 回归。
- 当前 Phase 10 已经落地默认 `fastcdc + blake3` 内容定义分块、写时 chunk/pack reuse，以及与 Phase 9 锚点提交 `edde3cafaaf6f1c99fa4b66912a5b3874132d79d` 的 standard/pressure A-B benchmark 对比。
- 当前 Phase 11 已完成 README、教程、docs landing page 与交付回归的文档收尾。
- 当前 Phase 12 已完成 benchmark 扩容与指标口径固化：benchmark 结果现已覆盖 bandwidth / metadata / maintenance / amplification / stability 五类摘要，携带 machine signature、dataset shape、threshold policy、manifest、same-machine compare 产物，并额外记录 host local sequential I/O reference，以及关键读/校验场景的独立 memory observation。
- 当前剩余工作已经收敛为 Phase 13：基于 Phase 12 的完整 benchmark 与 profiling 结果，收敛剩余时间路径热点与局部回退风险。

优先级排序如下：

1. 公开 API、对象模型、事务协议
2. whole-file blob MVP
3. refs / 历史 / 快照增强
4. chunk / pack / range read
5. full verify / 空间画像 / GC / 历史压缩
6. merge / 冲突模型
7. Git-like 本地 CLI
8. `git` / `git-lfs` / `huggingface_hub` 对拍
9. 异常测试 / 故障注入 / 极端场景安全
10. 性能基线 / benchmark 体系
11. 优化技术引入 / A-B 对比 / 结果复盘
12. 文档 / README / 教程 / 交付收尾
13. benchmark 扩容 / 指标口径 / 长期回归产物
14. benchmark 驱动的热点定位 / 时间路径收敛

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

## Phase 6. CLI 专题

### Goal

基于已经稳定的公开 API，交付一个可日常使用的本地 CLI，让 `hubvault` / `hv` 两个命令名都可用，并在命令名、主要选项和输出手感上尽量贴近 git；同时明确不引入 git 的 workspace / index / staging 概念，CLI 仍然只表达 `hubvault` 当前真实支持的仓库语义。

### Status

已完成。

### Technical Focus

本阶段的 CLI 对齐策略固定如下：

- 对齐真实 git 的优先级只限于命令名、主要选项、帮助结构和常见输出措辞，不为了“更像 git”而发明 workspace、index、staged/unstaged 差异或 checkout 工作树
- 所有命令只通过 `hubvault.api.HubVaultApi` 和公开模型工作，不直接读取 `repo/`、`storage/`、`txn/` 内部细节
- 统一支持 `hubvault` 与 `hv` 两个控制台入口，并补充顶层 `-C <path>`，让 `hv -C /path/to/repo status` 的使用方式尽量接近 `git -C ...`
- CLI 输出允许适度 ANSI 样式，但样式开关必须集中封装，且在设置 `NO_COLOR` 或 `HUBVAULT_NO_COLOR` 时完全退化为无色纯文本
- 优先实现与当前公开能力直接对标、且 Git 用户最容易预期的命令：`init`、`status`、`branch`、`tag`、`log`、`ls-tree`、`commit`、`merge`、`reset`
- 对于 `download`、`snapshot`、`verify` 这类 `hubvault` 特有但非常核心的能力，保留直观的本地命令名，并让输出风格继续保持简洁、脚本友好

命令范围与预期手感规划如下：

- `init [path] [-b|--initial-branch <name>] [--large-file-threshold <bytes>]`
  对齐 `git init` 的基础调用方式，输出仍保持“Initialized empty HubVault repository in ...”这类熟悉措辞，但底层会额外自动生成一个空树 `Initial commit`
- `status [-s|--short] [-b|--branch]`
  不伪造工作区状态；默认输出当前分支/head 与“nothing to commit, repository clean”式摘要，`--short --branch` 提供稳定紧凑输出
- `branch [--show-current] [-v] [name] [start-point] [-d|-D <name>]`
  复用 git 用户熟悉的分支列举和 `*` 当前分支标记
- `tag [-l] [name] [revision] [-d <name>]`
  提供创建、列举、删除标签的最小常用形态
- `log [revision] [-n|--max-count <n>] [--oneline]`
  默认展示 commit、作者、时间和消息；`--oneline` 输出 `<short-oid> <title>`
- `ls-tree [revision] [path] [-r|--recursive]`
  输出接近 `git ls-tree` 的 `mode type oid<TAB>path`
- `commit -m|--message <text> [--description <text>] [--revision <branch>] [--add <repo_path=src>] [--delete <repo_path>] [--copy <src=dest>]`
  保持 `git commit -m` 的主入口手感，但不引入 staging；文件变更直接显式编码为公开 `CommitOperation*`
- `merge <source> [--target <branch>] [-m|--message <text>] [--description <text>]`
  输出尽量接近 git merge 成功、快进和冲突提示，但底层仍使用 `hubvault` 的结构化 merge 结果
- `reset <commit> [--revision <branch>]`
  直达当前已支持的 ref 重置能力，不引入未实现的 mixed/hard/soft 工作区语义
- `download <path> [--revision <rev>] [--local-dir <dir>]`、`snapshot [--revision <rev>] [--local-dir <dir>]`、`verify [--full]`
  作为 `hubvault` 专属补充命令暴露当前公开 API 的核心能力

### Todo

* [x] 在 `hubvault/entry/` 下补充分层结构，拆出 `dispatch.py`、`context.py`、`formatters.py`、`repo.py`、`refs.py`、`history.py`、`content.py` 的责任边界。
* [x] 增加全局 `-C <path>` 语义，并确保 `hubvault` / `hv` 两个入口都指向同一套 CLI。
* [x] 实现 `init`、`status`、`branch`、`tag`、`log`、`ls-tree`、`commit`、`merge`、`reset` 命令。
* [x] 实现 `download`、`snapshot`、`verify` 等 `hubvault` 特有但高频的核心命令。
* [x] 为 CLI 输出补充统一 ANSI 样式 helper，并支持 `NO_COLOR` / `HUBVAULT_NO_COLOR` 完全禁色。
* [x] 用真实 `git` 的帮助与典型输出校准 help、选项命名和常见人类可读文案，但不照搬不适用的 workspace/index 语义。
* [x] 为新增 `hubvault/entry/*.py` 各自补对应的 `test/entry/test_*.py`，只通过公开 CLI 行为断言，不碰 private / protected 细节。
* [x] 为 Phase 6 增加 `test/test_phase6.py` 端到端 CLI 集成测试，覆盖 init、commit、branch、merge、log、下载/读取和 verify 的全周期真实使用场景。

### Checklist

* [x] `hubvault --help` 与 `hv --help` 都能展示同一套命令面。
* [x] CLI 命令只通过公开 API 工作，没有私自读取内部实现细节。
* [x] `status` / `branch` / `tag` / `log` / `ls-tree` 的输出对 Git 用户是熟悉的，但不会伪造 workspace/index 语义。
* [x] 样式输出不在命令里分散判断，且设置禁色环境变量后会退化为纯文本输出。
* [x] `commit` / `merge` / `reset` / `download` / `snapshot` / `verify` 能稳定跑通当前已支持的公开能力。
* [x] 新增 CLI 测试按 `hubvault/entry` 模块树一一对应拆分。
* [x] `make unittest` 通过。

## Phase 7. 对拍

### Goal

在 merge 本体落地后，用真实 `git`、`git-lfs` 和 `huggingface_hub` 行为做系统对拍，证明 `hubvault` 的 VCS 与公开 API 语义不只是“内部自洽”，而是对外部主流基准也成立。

### Status

已完成。

### Todo

* [x] 建立 `hubvault` vs `git` 的行为对拍矩阵，覆盖小文件 commit DAG、tree/list、blob/tree/commit OID 与 revision 解析。
* [x] 建立 `hubvault` vs `git-lfs` 的文件行为对拍，覆盖大文件身份元数据、阈值边界、下载路径后缀保真与对象哈希语义。
* [x] 建立 `hubvault` vs `huggingface_hub` 的公开 API 对拍基线，默认离线比对公开字段格式与下载路径规则，并提供可选 live smoke test。
* [x] 将可离线复现的 `git` / `git-lfs` 对拍纳入常规回归，把需要联网的 HF 实测整理成 `HUBVAULT_LIVE_HF=1` 的可选基线。
* [x] 把经过确认的最小必要偏差回写到 `plan/init/04-api-compat.md`、`README.md` 与公开 docstring。
* [x] 对拍结果不仅校验“能否调用成功”，还校验返回结构、关键字段和值语义。

### Checklist

* [x] 对拍结论能明确说明哪些行为已经严格对齐，哪些行为属于有文档记录的最小偏差。
* [x] `oid` / `blob_id` / `sha256` / size / path suffix 等用户可见文件语义有实测证据支撑。
* [x] 历史列表、refs、下载和快照行为都有真实 VCS/HF 基线可回归或可选 smoke 基线。
* [x] 对拍套件不会回退去依赖 private / protected 内部实现。
* [x] `make unittest` 与相应对拍回归通过。

## Phase 8. 异常测试

### Goal

系统化模拟极端场景、损坏中间态和中断写入，确保仓库真相永远不被半写状态污染；最坏结果只允许等效于“本次操作从未发生过”，而不是留下任何介于“成功提交”和“从未发生过”之间的暧昧状态。

### Status

已完成。

### Technical Focus

这一阶段不只做“抛异常能报错”式测试，而是要直接验证事务线性化边界、对象发布边界和用户可观测恢复语义。

当前实际落地的故障注入与恢复机制如下：

- 通过子进程执行公开 API，并用统一环境变量协议 `HUBVAULT_FAILPOINT=<name>` / `HUBVAULT_FAIL_ACTION=<action>` 在关键边界主动触发 `RuntimeError`、`OSError`、`KeyboardInterrupt` 或直接 `os._exit(...)`
- 当前已覆盖的核心 failpoint 包括 `create_commit.after_publish`、`create_commit.after_ref_write`、`create_commit.after_reflog_append`、`merge.after_publish`、`merge.after_ref_write`、`merge.after_reflog_append`、`create_branch.after_ref_write`、`create_branch.after_reflog_append`、`delete_branch.after_ref_write`、`delete_branch.after_reflog_append`、`create_tag.after_ref_write`、`create_tag.after_reflog_append`、`delete_tag.after_ref_write`、`delete_tag.after_reflog_append`、`reset_ref.after_ref_write`、`reset_ref.after_reflog_append`、`squash_history.after_publish`、`squash_history.after_ref_write`、`squash_history.after_reflog_append`、`gc.after_publish`
- 对 ref-changing 写路径，事务协议已经调整为“先写 journal，再写 ref，再写 reflog，最后才写 `COMMITTED`”；只要 API 没有明确成功返回，中断后都按 rollback-only 语义回到操作前
- 对 storage-only 维护路径（当前重点是 `gc()`），异常测试要求的是“主状态不损坏、公开读取与校验不漂移”；即使产生安全孤儿或未完成回收，也不会出现公开主状态半提交
- 对用户视图与快照缓存，异常测试直接通过真实文件删除、替换为目录等方式验证“视图可损坏但可重建，正式对象不受影响”

这一阶段已经覆盖的代表性异常矩阵如下：

- 提交路径：`create_commit()` 在对象发布后、ref 切换后、reflog 追加后的中断；分别验证同步异常回滚与进程直接退出后的重开恢复
- merge 路径：`merge()` 在 target ref/reflog 线性化边界上的中断；验证主分支 head、文件树和 reflog 都等效于本次操作从未发生过
- refs 路径：`reset_ref()`、`create_branch()`、`delete_branch()`、`create_tag()`、`delete_tag()` 在 ref 切换与 reflog 记录之间的中断；验证 refs 集合与可见历史不漂移
- 历史重写路径：`squash_history()` 在对象发布后和 ref 切换后的中断；验证搬迁后重开仍会回滚到重写前状态
- 维护路径：`gc()` 在 live chunk/index 已发布但尚未完成回收时的中断；验证主状态仍可读、`quick_verify()` / `full_verify()` 继续通过
- 只读视图路径：`hf_hub_download()` / `snapshot_download()` 产物被删掉、截断、替换为目录后的重建
- 可搬迁路径：中断后立即 `mv` 仓库目录，再重新打开并验证主状态仍一致
- 并发/恢复路径：通过子进程 crash + 后续公开 API 读写继续成功，间接验证跨进程锁释放与恢复链路可继续工作

这一阶段的核心断言已经落地如下：

- 当前 head、branch/tag 指向、tree/list/read 结果必须仍然等效于“本次写操作从未发生过”，或者已经完整成功
- 已提交版本的字节内容、大小、`oid`、`blob_id`、`sha256` 不得发生漂移
- 新写到一半的对象即使遗留为孤儿，也必须不可达且不会污染主状态；后续可由 `gc()` 安全清理
- `quick_verify()` / `full_verify()` 必须能把异常态解释成明确问题，而不是沉默吞掉
- 用户视图损坏只影响视图本身，不影响正式对象，可通过重新下载/导出恢复

### Todo

* [x] 建立 failpoint 注入协议 `HUBVAULT_FAILPOINT` / `HUBVAULT_FAIL_ACTION`，明确关键公开写 API 的故障点名称与触发时机。
* [x] 为 `create_commit()` 增加阶段性故障注入测试，覆盖对象发布后、ref 更新后、reflog 追加后的同步异常与进程退出。
* [x] 为 `merge()` 增加阶段性故障注入测试，覆盖 merge ref/reflog 线性化边界上的回滚语义。
* [x] 为 refs 操作增加异常测试，覆盖 branch/tag 创建删除与 `reset_ref()` 在 ref/reflog 之间的原子性。
* [x] 为维护路径增加异常测试，覆盖 `gc()` live pack 发布后的中断安全与 `squash_history()` 历史重写后的 crash 恢复。
* [x] 为用户视图和快照缓存增加破坏性测试，覆盖删除、替换为目录后的重建。
* [x] 为 repo 可搬迁性增加异常后回归，覆盖中断后直接搬迁目录再重开。
* [x] 为校验与诊断接口增加异常态断言，确保 `quick_verify()` / `full_verify()` 在恢复后稳定通过。
* [x] 明确区分“API 失败但主状态必须等效于从未发生过”的 ref-changing 场景与“主状态必须保持安全可读”的 storage-only 维护场景，并把期望写进测试名称和 pydoc。
* [x] 将当前异常恢复机制与范围回写到 Phase 文档，避免文档停留在未来时。

### Checklist

* [x] 任意中断都不会让 `refs/` 指向半成品提交，也不会破坏任何已提交对象。
* [x] 对 ref-changing 写路径，最坏结果等效于“本次操作从未发生过”，不存在第三种半提交状态。
* [x] 损坏的用户视图、快照缓存或临时目录不会被误判成正式仓库数据损坏。
* [x] `gc()` 等 storage-only 维护中断不会污染公开主状态，恢复后仓库仍可读且校验通过。
* [x] 异常测试默认只通过公开 API 与子进程执行，不依赖 private / protected 细节。
* [ ] 异常测试在三平台上至少保有可运行的核心子集。
* [x] `make unittest` 通过。

## Phase 9. 性能

### Goal

在语义、对拍和异常安全都稳定之后，再建立正式性能基线并做可选优化，避免为了吞吐量引入协议漂移或隐藏一致性风险。

### Status

已完成。

### Baseline Anchor

本阶段已经固定出后续优化实验的性能锚点提交：

- benchmark baseline anchor commit：`edde3cafaaf6f1c99fa4b66912a5b3874132d79d`

后续所有 Phase 10 的技术引入，都必须至少对这个 commit 做 `standard` 与 `pressure` 两组同口径对比，不能只拿“优化后单次跑得更快”当结论。

### Technical Focus

Phase 9 不会把“写几个 benchmark case”当成性能工作完成，而是分成四个连续层次：

1. 先建立可重复、可解释、可导出的 benchmark 基线。
2. 再用 profiling 与分项指标定位热点，而不是靠直觉改代码。
3. 再只在“不改变公开语义和磁盘协议”的前提下做安全优化实验。
4. 最后把稳定 benchmark 纳入长期回归，让后续改动有客观退化信号。

这一阶段的核心原则固定如下：

- benchmark 一律只通过公开 API / 公开 CLI 驱动，不依赖 private / protected 实现细节，也不通过 monkeypatch 内部函数来“测假数据”
- 正式性能结论优先看同机同配置下的相对对比，不用跨机器绝对毫秒数做结论
- 任何性能优化都不能改变当前事务语义、原子语义、锁语义、`oid` / `sha256` / 路径保真等公开可观测行为
- 在没有基线和热点证据前，不引入带协议风险或兼容成本的“先上再说”型依赖

### 当前已落地基线

当前仓库已经落地下面这组 benchmark 代码与入口：

- `test/benchmark/test_phase9_small.py`
  已覆盖小文件批量提交、批量读取、冷快照导出。
- `test/benchmark/test_phase9_large.py`
  已覆盖 chunked 大文件上传、范围读取、`hf_hub_download()` cold/warm、阈值扫描、完全重复 live set、chunk 对齐重叠 live set、错位重叠 live set。
- `test/benchmark/test_phase9_history.py`
  已覆盖深历史上的 commit/ref/reflog 查询，以及公开 `merge()` 的非快进路径。
- `test/benchmark/test_phase9_maintenance.py`
  已覆盖历史重复大文件的空间回收、`squash_history()` 跟随 GC，以及 maintenance-heavy 仓库上的 `full_verify()`。
- `test/benchmark/test_phase9_cli.py`
  已覆盖公开 CLI 的只读端到端路径：`status`、`log`、`ls-tree`、`verify`。
- `test/benchmark/conftest.py`
  已提供 scale 驱动的公共 benchmark fixture。
- `tools/benchmark/run_phase9.py`
  已提供独立于 `pytest-benchmark` 终端输出的 JSON 汇总 runner，支持 `full` baseline 套件与 `pressure` 大文件压力子集。
- `tools/benchmark/compare.py`
  已提供两个 benchmark JSON 结果的摘要比较工具。
- `Makefile`
  已新增 `benchmark`、`benchmark_smoke`、`benchmark_standard`、`benchmark_phase9`、`benchmark_phase9_smoke`、`benchmark_phase9_standard`、`benchmark_phase9_pressure`、`benchmark_compare` 入口，并统一优先使用仓库内 `./venv/bin/python`。
- `.github/workflows/benchmark.yml`
  已新增独立 benchmark workflow，在 Linux / Windows / macOS 上跑 smoke 子集，并在 Ubuntu 上产出 curated Phase 9 汇总 JSON。

当前这套 harness 只通过公开 API 驱动，没有回退到 private / protected 细节。

### 当前数据集形状

首轮已落地的数据集并不是完整终版，但已经足够回答当前最关心的吞吐与空间问题：

`small-tree`
    128 个 4 KiB 小文件，按多目录分组；用于小文件提交、读取和快照导出。

`large-single`
    单个 12 MiB chunked 大文件；用于上传与 `read_range()` 基线。

`exact-duplicate-live`
    6 个完全相同的 12 MiB live 大文件；用于测“写后立刻”空间膨胀与 `gc()` 后的物理复用效果。

`aligned-overlap-live`
    6 个共享 8 MiB 对齐前缀、各自再带 1 MiB 独有尾部的大文件；Phase 9 锚点用于测固定大小 chunk 在“边界对齐重叠”场景下的复用程度，Phase 10 则用于对比内容定义分块后的变化。

`shifted-overlap-live`
    6 个来自同一 base payload、但每个文件窗口按 1 KiB 偏移的大文件；Phase 9 锚点用于测固定大小 chunk 对错位相似内容的复用退化，Phase 10 用于验证 FastCDC 是否能改善这一问题。

`historical-duplicate`
    同一路径连续写入 24 个完全相同的大文件 revision；用于测历史累积写入下的短期空间膨胀和 `gc()` 回收效果。

`maintenance-heavy`
    多代大文件、带下载/快照视图痕迹的仓库；用于测 `full_verify()` 基线。

数据生成器已经修正为“全长确定性字节流”，不再把大文件做成固定 1 MiB 周期重复，避免把文件内自重复误判成跨文件 chunk 复用。

### 基线场景矩阵

Phase 9 当前把 benchmark 分成三层：

`micro / hotpath`
    用来测单个公开调用的纯热点，例如单文件 `upload_file()`、`read_bytes()`、`hf_hub_download()`、`read_range()`、`list_repo_commits()`。

`workflow / end-to-end`
    用来测真实用户路径，例如“初始化 -> 多次提交 -> 下载 -> 快照 -> 校验”这类完整生命周期，而不是只看某一个函数调用。

`maintenance / heavy`
    用来测重维护操作，例如 `full_verify()`、`gc()`、`squash_history()`，以及深历史、大文件、宽树形仓库上的最坏路径。

当前已落地或已明确排期的公开 benchmark 场景包括：

- 小文件路径：已覆盖批量 `create_commit()`、`read_bytes()`、`snapshot_download()`。
- 历史路径：已覆盖 `list_repo_commits()`、`list_repo_refs()`、`list_repo_reflog()` 与历史重复写入导致的空间画像。
- 下载路径：已覆盖冷 `snapshot_download()`，以及 `hf_hub_download()` 的 cold/warm 两种 detached view 语义。
- 大文件路径：已覆盖 chunked `upload_file()`、`read_range()`、exact/aligned/shifted overlap，以及阈值扫描与 whole-file vs chunked 边界。
- 维护路径：已覆盖 `full_verify()`、`gc()` 空间治理画像，以及 `squash_history()` 跟随 GC 的完整维护路径。
- merge 路径：已覆盖公开 `merge()` 的非快进成功路径。
- CLI 路径：已覆盖一组 `hubvault` / `hv` 共享 CLI 的只读端到端 benchmark。

### 基线数据集设计

为了避免“这次碰巧快/慢”的偶然性，Phase 9 会使用固定、可复现的数据集形状，而不是手工随便造几个文件。

当前规划中的终版数据集族如下，其中首轮已落地的项会继续沿用：

`flat-small`
    128 个 4 KiB 小文件，单层目录；用于测小文件批量提交、列树和快照导出。

`nested-small`
    32 个目录，每个目录 32 个 4 KiB 小文件；用于测深树遍历、`snapshot_download()` 与 `list_repo_tree()`。

`mixed-model`
    模拟真实模型仓库，包含 README、config、tokenizer、若干 JSON/TXT 小文件，以及 1-2 个 32-128 MiB 大文件；用于测最接近日常使用的真实路径。

`history-deep`
    固定 128 / 512 / 1024 个 commit 深度，持续修改有限路径；用于测 `list_repo_commits()`、`reflog`、merge-base 解析与 `squash_history()`。

`threshold-sweep`
    针对 `large_file_threshold` 的边界扫描集，至少包含 `threshold - 1`、`threshold`、`threshold + 1` 以及 4x / 16x 阈值的大文件；用于确定 whole-file 与 chunked 的分界收益。

`maintenance-heavy`
    多代大文件、多轮下载缓存、多分支历史并存的仓库；用于测 `full_verify()`、`gc()`、`squash_history()` 与空间画像。

数据内容本身也会固定成三类，避免只测一种“容易命中缓存/压缩”的样本：

- 低熵重复字节数据：模拟部分 checkpoint 或 pad-heavy 文件
- 中熵伪随机数据：用固定 seed 生成，模拟更难压缩、更接近真实二进制权重的内容
- 混合文本 + 二进制数据：模拟 HF 风格仓库的常见组合

### Benchmark 方法学

性能基线不会直接沿用 `make unittest`，而是使用独立的 benchmark 运行路径，避免 coverage、xdist、频繁 fixture 重建把结果污染掉。

当前已经采用或明确固定的 benchmark 技术路线如下：

- 主计时框架使用 `pytest-benchmark`
  当前 `requirements-test.txt` 已包含它，`pytest.ini` 也已经声明了 `benchmark` marker，首轮基线已经基于它跑通。
- 对高耗时、IO 型场景优先使用 `benchmark.pedantic(...)`
  当前 benchmark 测试已经统一采用固定 rounds / iterations 的口径，避免 auto-calibration 把大操作拆成难解释的碎片样本。
- 通过 `--benchmark-json build/benchmark/<name>.json` 导出原始结果
  当前 `pytest-benchmark` 基线结果已经输出到 `build/benchmark/pytest-benchmark-smoke.json`，汇总 runner 则输出到 `build/benchmark/phase9-*.json`。
- 用 runner 额外记录 wall-clock、operation-level seconds、throughput 与空间指标
  当前 `tools/benchmark/run_phase9.py` 已同时保留“整场景耗时”和“真实操作耗时”，避免把 repo 初始化成本误算成纯读取/纯写入吞吐。
- 用真实文件系统扫描补充 repo 磁盘占用、可回收空间变化等结果
  对 `gc()`、重复大文件和 overlap 场景，当前已经记录 `chunk_pack_bytes_before_gc/after_gc`、`dedup_gain_after_gc`、`physical_over_*` 等指标。
- `tracemalloc` 与 Python heap peak
  默认 baseline/pressure 套件当前不启用 `tracemalloc`，因为它会显著扭曲多 GiB 压测路径；需要 Python heap 画像时，后续以 opt-in profiling 模式单独启用，而不是混进常规 benchmark 回归。

初版 benchmark 的主要输出指标固定如下：

- latency：以 median 为主，必要时补 IQR / stddev；不拿单次最小值做结论
- throughput：对上传、下载、范围读取按 MiB/s 计算
- repo size delta：操作前后仓库总大小变化
- cache amplification：下载/快照后 `cache/` 占用变化
- Python heap peak：通过 `tracemalloc` 记录峰值
- operation shape：输入规模、文件数、commit 深度、large-file 阈值、是否 cold/warm

其中 cold / warm 的定义会明确区分：

- `cold`：新建 repo 或新开进程，且不复用先前的 detached 视图输出
- `warm`：同一 repo 在一次预热调用后重复执行，允许复用已存在的 managed cache 与磁盘元数据

需要特别说明的是：Phase 9 不会尝试在 CI 中“清空操作系统 page cache”来伪造绝对冷启动，因为那既不跨平台，也不稳定。我们只要求同一 runner、同一轮 benchmark 内部的比较可解释。

### 当前 benchmark 代码组织

为了让 benchmark 可维护，Phase 9 当前已经引入下面这组结构：

- `test/benchmark/test_phase9_small.py`
  小文件、历史列表、下载与快照的公开 API benchmark
- `test/benchmark/test_phase9_large.py`
  大文件、chunk 边界、`read_range()` 和 whole-file vs chunked 对比
- `test/benchmark/test_phase9_maintenance.py`
  `verify()`、`gc()`、`squash_history()`、空间画像 benchmark
- `test/benchmark/conftest.py`
  只放公共 benchmark fixture、确定性数据集生成器和结果辅助函数
- `tools/benchmark/compare.py`
  比较两个 `pytest-benchmark` JSON，输出性能变化摘要、重点退化项和建议关注点
- `.github/workflows/benchmark.yml`
  已落地为手动触发或定时触发的 benchmark workflow，单独上传 JSON 和汇总报告，不与普通单元测试工作流混跑

### 当前执行记录与结论

本轮基线与压测统一使用仓库内 `./venv/bin/python` 执行，已实际跑过以下命令：

- `./venv/bin/python -m tools.benchmark.run_phase9 --scale smoke --output build/benchmark/phase9-smoke-summary.json`
- `HUBVAULT_BENCHMARK_SCALE=smoke ./venv/bin/python -m pytest test/benchmark -sv -m benchmark --benchmark-only --benchmark-json=build/benchmark/pytest-benchmark-smoke.json`
- `make benchmark_phase9_standard`
- `make benchmark_phase9_pressure`
- `make unittest`

更详细的数据集、指标拆分和分析结论已单独写入 `plan/init/07-phase9-benchmark-baseline.md`，避免把执行计划文档本身塞成原始结果转储。

下面这些 `standard` baseline 数值专门对应 Phase 9 锚点提交 `edde3cafaaf6f1c99fa4b66912a5b3874132d79d`，用于和当前 Phase 10 候选实现做 A/B 对比，不再代表当前 HEAD 的实时结果：

- 大文件上传：12 MiB `upload_file()` 实测操作耗时约 `0.361s`，吞吐约 `33.20 MiB/s`
- 大文件范围读取：1 MiB `read_range()` 实测操作耗时约 `0.0297s`，吞吐约 `33.66 MiB/s`
- 小文件批量读取：128 个 4 KiB 文件总计 512 KiB，实测读取耗时约 `0.703s`，吞吐约 `0.71 MiB/s`
- 冷快照导出：512 KiB 小文件树 `snapshot_download()` 实测操作耗时约 `2.30s`，吞吐约 `0.22 MiB/s`
- `full_verify()`：maintenance-heavy 仓库约 9 MiB live 数据，实测校验耗时约 `4.04s`，吞吐约 `2.23 MiB/s`
- 冷 `hf_hub_download()`：12 MiB chunked 文件 detached view 实测约 `0.213s`，缓存增量约 `25.17 MiB`
- warm `hf_hub_download()`：第二次调用缓存增量约 `0`，返回路径保持 repo 相对路径后缀
- 阈值扫描：`large_file_threshold - 1` 保持 whole-file blob，`large_file_threshold` 与 `large_file_threshold + 1` 都稳定进入 chunked storage
- 非快进 merge：公开 `merge()` 在 benchmark 路径下稳定产出结构化 merge commit
- `squash_history()`：历史重写 + 跟随 GC 实测操作耗时约 `1.92s`，吞吐约 `6.24 MiB/s`

作为 Phase 9 锚点提交，当时在空间与 chunk 复用方面得到的结论已经比较明确：

- 完全重复 live 大文件：6 个 12 MiB 文件在写后立刻的 `chunks.packs` 约为 `75.50 MiB`，`gc()` 后降到 `12.58 MiB`，`dedup_gain_after_gc = 6.0x`
- 对齐重叠 live 大文件：6 个文件共享 8 MiB 前缀时，`chunks.packs` 从 `56.62 MiB` 降到 `14.68 MiB`，`dedup_gain_after_gc = 3.86x`
- 错位重叠 live 大文件：同一 base payload 的滑窗错位场景下，`chunks.packs` 从 `75.50 MiB` 到 `75.50 MiB` 几乎不变，`dedup_gain_after_gc ≈ 1.0x`，相对唯一数据体积仍放大约 `6.0x`
- 历史重复写入：同一路径连续 24 个相同 revision 时，`chunks.packs` 从 `301.99 MiB` 降到 `12.58 MiB`，`dedup_gain_after_gc = 24.0x`

在 `pressure` 压测子集下，已经把总数据量拉到 GiB 级别，代表性结果如下：

- 大文件上传：512 MiB chunked 文件实测操作耗时约 `6.33s`，吞吐约 `80.93 MiB/s`
- 大文件范围读取：32 MiB `read_range()` 实测操作耗时约 `0.396s`，吞吐约 `80.80 MiB/s`
- 冷 `hf_hub_download()`：512 MiB detached file view 实测操作耗时约 `9.36s`，缓存增量约 `1.00 GiB`
- 完全重复 live 大文件：3 个 512 MiB 文件，`chunks.packs` 从 `1.50 GiB` 降到 `512 MiB`，`dedup_gain_after_gc = 3.0x`
- 对齐重叠 live 大文件：总逻辑体积约 `1.50 GiB`，`chunks.packs` 从 `1.50 GiB` 降到 `768 MiB`，`dedup_gain_after_gc = 2.0x`
- 错位重叠 live 大文件：`chunks.packs` 从 `1.50 GiB` 降到约 `1.00 GiB`，`dedup_gain_after_gc ≈ 1.49x`，相对唯一体积仍放大约 `1.99x`

据此，Phase 9 锚点提交当时可以下结论：

- 当前实现的时间性能在单机本地路径场景下是可接受的，尤其大文件上传与范围读取已经进入几十 MiB/s 量级
- 在锚点提交中，长期空间利用率主要取决于 `gc()` 之后的压实结果，而不是写入当下；也就是说，当时并没有写时 pack/chunk 物理复用
- 对 exact duplicate 和 chunk 边界对齐的 overlap，`gc()` 之后的空间表现是健康的，能接近唯一数据体积
- 对错位相似内容，固定大小 chunk 的复用几乎失效，这是锚点提交最明确的空间短板
- 公开 `hf_hub_download()` 已经具备稳定的 cold/warm 语义：warm 路径复用现有 detached view，且不再额外膨胀缓存
- 阈值扫描已经证明 `large_file_threshold` 的 whole-file / chunked 分界是稳定且可回归的
- 现在已经同时具备“日常 baseline benchmark”和“GiB 级 pressure benchmark”两层入口，后续既能看趋势，也能看真正压测行为
- 当时最明确的后续方向是“先做写时复用/短期空间膨胀控制，再评估是否值得引入内容定义分块来改善错位重叠复用”

这些结论已经在 Phase 10 中被实装并重写：当前实现默认使用 `fastcdc + blake3` 规划大文件分块，并在提交时直接复用已可见或同事务内已写入的 chunk，exact duplicate / historical duplicate 的写时膨胀已经基本消失，shifted overlap 的空间放大也已明显收敛。详细 A/B 表格和分析见 [07-phase9-benchmark-baseline.md](/home/hansbug/wtf-projects/hubvault/plan/init/07-phase9-benchmark-baseline.md)。

### CI 与回归策略

Phase 9 不会一开始就把性能 benchmark 当成 PR 强制门禁，否则噪声会比信号大。

计划中的执行策略如下：

- 默认 `make unittest` 仍只承担 correctness 回归，不掺 benchmark
- 新增单独 benchmark 命令，例如：
  `pytest test/benchmark -sv -m benchmark --benchmark-only --benchmark-json=build/benchmark/local.json`
- 在 CI 中先提供手动触发或定时跑的 benchmark workflow，使用固定 Python 版本和尽量固定的 runner
- 首轮只记录基线和变化趋势，不用绝对耗时直接 fail CI
- 等积累到足够稳定的结果后，再考虑对少数高稳定场景加“相对退化阈值”告警，例如同 runner 下回退超过 15%-20% 才标红

跨平台策略也会分层：

- Linux x86_64 作为第一组“权威数值基线”环境，因为最容易稳定复现
- Windows / macOS 先保留 benchmark smoke 子集，主要验证 harness 可运行且不会出现数量级异常回退
- 当跨平台波动模式足够清楚后，再决定是否分别维护平台级基线

### 热点分析与优化优先级

Phase 9 的优化顺序不会是“先上可选依赖”，而是先做零协议风险的热点整理。

优先考虑的无协议变更优化包括：

- 减少同一公开调用内重复的 ref 解析、commit/tree 反序列化与目录扫描
- 把哈希计算与文件复制/写入串成单遍流式处理，避免重复读文件
- 对 `snapshot_download()`、`hf_hub_download()`、`verify()`、`gc()` 合并不必要的 `stat()` / `glob()` 扫描
- 对 `read_range()` 评估更合适的 buffered IO / `mmap` 路径，但不能破坏 Windows / Python 3.7 兼容性
- 对历史遍历与 merge-base 解析增加调用级缓存，而不是进程级全局状态，避免语义漂移

只有在 benchmark 明确证明热点存在后，才评估以下可选技术：

- `blake3`
  只允许作为内部临时加速工具，例如快速预哈希、去重前置筛查或 chunk 规划辅助；绝不替代公开 `sha256`、`oid` 或任何 HF/Git 对齐字段
- `zstandard`
  只作为未来可选压缩实验候选；只有在证明确实是 IO/空间双瓶颈，并且格式影响、兼容策略和 fallback 都完全明确后，才考虑进入实现阶段
- `fastcdc` 或同类内容定义分块算法
  只在现有 chunk 方案被 benchmark 证明在大文件写入或空间利用上已成为主要瓶颈时再评估；默认不会为了“高级一点”而先替换

明确不在 Phase 9 做的事情包括：

- 修改公开 `oid` / `blob_id` / `sha256` 语义
- 为了更快而去掉事务、锁、原子发布或 rollback-only 恢复
- 让可选原生依赖变成安装和正确性的前置条件
- 为了迎合 benchmark 结果而牺牲 repo 可搬迁、自包含和 detached view 语义

### Benchmark 建立顺序

这一阶段的实施顺序已经固定为：

1. 先把数据集生成器与 benchmark harness 放到 `test/benchmark/`，并确保只通过公开 API/CLI 驱动。
2. 先跑 baseline-only，不改任何实现，生成第一版 JSON 基线与汇总报告。
3. 根据报告挑出 2-3 个最明显热点，再用 `cProfile` 等手段做定向分析。
4. 优先尝试零协议风险优化，并在每轮优化后重跑同一批 benchmark。
5. 只有在零协议风险优化仍无法解决主要瓶颈时，才进入可选依赖实验分支。

### Todo

* [x] 在 `test/benchmark/` 下建立只通过公开 API / 公开 CLI 驱动的 benchmark harness，并按小文件、大文件、历史/merge、维护、CLI 路径拆分文件。
* [x] 建立固定数据集生成器，覆盖 `small-tree`、深历史、阈值扫描、完全重复 live set、对齐重叠 live set、错位重叠 live set、历史重复写入、maintenance-heavy 等关键仓库形状。
* [x] 用 `pytest-benchmark` + JSON 导出建立 baseline benchmark，覆盖小文件提交/读取、chunked 大文件提交/范围读取、快照导出、历史遍历、merge、校验、`squash_history()` 与 CLI 只读路径。
* [x] 为 benchmark 结果补 wall-clock、operation-level throughput、cache delta、repo/chunk space 画像等辅助指标。
* [x] 明确并固化 cold / warm benchmark 语义，覆盖 `snapshot_download()` cold path 与 `hf_hub_download()` cold/warm path。
* [x] 为结果对比补 `tools/benchmark/compare.py` 汇总工具，避免 benchmark 结果只停留在原始 JSON。
* [x] 为 Phase 3 大文件引擎建立阈值扫描基线，明确“何时 whole-file 更优、何时 chunked 更优”的交界点。
* [x] 建立 `pressure` 压测档位，把总数据量提升到 GiB 级别，并聚焦大文件 IO、detached view、重复/重叠内容空间行为。
* [x] 建立独立 benchmark workflow，在 Linux / Windows / macOS 上跑 smoke 子集，并在 Ubuntu 上产出 curated Phase 9 汇总。
* [x] 明确 Phase 9 的优化优先级：写时复用优先于内容定义分块，零协议风险优化优先于可选依赖实验。
* [x] 统一 Makefile benchmark 入口，并确保 `make unittest` 与 benchmark 命令都优先使用仓库内 `./venv/bin/python`。

### Checklist

* [x] Phase 9 已建立 baseline + pressure 两层 benchmark，后续任何优化前后都必须保持公开 API 行为、存储格式和事务语义不变。
* [x] 同机可重复 benchmark 已经展示出当前瓶颈、收益空间和退化风险。
* [x] benchmark 结果已经包含时间以外的关键辅助指标，而不是只有一个“总耗时”数字。
* [x] cold / warm、whole-file / chunked、small / large、correctness / benchmark 这几组概念边界都被清楚区分。
* [x] 可选原生加速被明确限定为纯增益项，不成为正确性、安装和跨平台支持的前置条件。
* [x] 当前基线已经能说明小文件路径与大文件路径是两类不同瓶颈，后续优化不能只盯大文件吞吐。
* [x] benchmark harness 已具备 Linux / Windows / macOS smoke workflow 入口。
* [x] `make unittest`、`make benchmark_phase9_standard` 与 `make benchmark_phase9_pressure` 已在本地跑通相应回归。

## Phase 10. 优化技术引入与 A/B 对比

### Goal

在 Phase 9 已经固定 benchmark 基线的前提下，只引入那些已经被基线证明“值得做”的新技术或优化手段，并且每项引入都要做前后对比，确保收益真实、协议不漂移、风险可解释。

### Status

已完成。

### Technical Focus

Phase 10 实际采用的技术路线如下：

- 直接把 `fastcdc` 作为默认 chunk 规划算法，不保留兼容层或双实现分支。
- 直接把 `blake3` 作为 FastCDC 的快速边界哈希函数，用于内容定义分块规划与 chunk digest 缓存加速。
- 保持正式对象身份、公开文件 `sha256`、Git 风格 `oid` / `blob_id` 语义不变；`blake3` 只存在于内部规划链路。
- 在提交大文件时，先汇总“当前可见索引 + 当前事务已暂存索引”，仅把真正未出现过的新 chunk 追加写入 pack，从而实现同一次 commit 内、以及跨历史 commit 的写时物理复用。
- 所有技术引入都使用 Phase 9 锚点提交 `edde3cafaaf6f1c99fa4b66912a5b3874132d79d` 做 standard / pressure 两档 benchmark 对比，并把系统性对比表和分析写回 `plan/init/07-phase9-benchmark-baseline.md`。
- 本阶段不再引入额外兼容抽象层，也不把 profiling 工具链塞进运行时路径；更细的热点分析继续留给后续性能演进工作。

### Todo

* [x] 基于 Phase 9 锚点 commit `edde3cafaaf6f1c99fa4b66912a5b3874132d79d` 固定 A/B benchmark 流程，并保留 baseline 汇总结果供当前候选实现对比。
* [x] 直接引入 `blake3` 作为 FastCDC chunk 规划的快速哈希函数，同时保持公开 `sha256` / Git 风格对象哈希不变。
* [x] 直接引入 `fastcdc` 作为默认内容定义分块算法，不保留兼容层。
* [x] 基于“可见索引 + 同事务暂存索引”补齐写时 chunk/pack reuse，覆盖同一次 commit 内与跨历史 commit 的重复 chunk 复用。
* [x] 为 chunk 规划、索引可见视图与 Phase 10 端到端大文件复用场景补齐公开行为测试。
* [x] 重跑 `make benchmark_phase9_standard` 与 `make benchmark_phase9_pressure`，并把标准档/压力档对比表与分析追记到 `plan/init/07-phase9-benchmark-baseline.md`。
* [x] 明确记录收益与回归：exact duplicate / historical duplicate 的写时膨胀已消失，shifted overlap 明显改善，范围读取/冷暖下载与 merge 仍有需要继续观察的时间侧波动。

### Checklist

* [x] 每项已引入技术都能明确回答“它解决的是 Phase 9 哪个真实瓶颈”。
* [x] 所有优化前后都保留公开 API 行为、磁盘协议、哈希语义、detached view 语义和 rollback-only 恢复语义不变。
* [x] `blake3` 只作为内部加速信息，不会变成公开对象身份字段或兼容语义的一部分。
* [x] `fastcdc` 已直接默认化，并在 shifted overlap 场景里带来了可量化收益，因此不再停留在实验分支。
* [x] 当前对比已经具备 baseline anchor、standard/pressure 两档结果、Markdown 表格和详细分析，而不是只有主观体感。
* [x] `make unittest` 与相应 benchmark 回归在技术引入后持续通过。

## Phase 11. 文档、README 与教程

### Goal

在前述功能、对拍和安全结论稳定后，统一收尾用户文档、README、教程与交付检查，让外部使用者看到的公开说明和真实实现完全一致。

### Status

已完成。

### README 组织计划

README 需要从“项目口号 + 状态提示”升级为真正可用的入口文档，至少覆盖以下板块：

* 项目定位：hubvault 是什么、不是什么、适合什么场景。
* 核心能力：本地可搬运仓库、HF 风格 API、Git 风格 commit/refs、chunked 大文件、校验与恢复。
* 快速开始：同时给出 Python API 与 CLI 的最短真实工作流。
* 兼容性边界：哪些公开语义对齐 `huggingface_hub` / `git-lfs` / Git，哪些地方保持 hubvault 自身设计。
* 数据安全语义：只读 detached view、显式写 API、原子提交、锁与恢复模型。
* 文档导航：把安装、快速开始、分支合并、维护治理、内部结构教程全部串起来。
* 交付与开发：支持的平台/Python 版本、常用开发命令、回归入口。

### 教程目录组织计划

参考 `pyfcstm-2` 的 docs 结构，教程统一放在 `docs/source/tutorials/<topic>/` 下，每个主题目录至少包含：

* `index.rst`
* `index_zh.rst`
* 至少一个可直接执行的 `.demo.py` 或 `.demo.sh` 示例文件
* 与示例对应的真实输出快照 `.txt`（必要时）

Phase 11 计划新增并维护以下教程主题：

* `installation`：安装、版本检查、`hubvault` / `hv` CLI 名称、最小安装验证。
* `quick_start`：从 `create_repo()` 到多次提交、列树、读取、`hf_hub_download()`、`snapshot_download()` 的最短上手路径。
* `workflow`：围绕 branch/tag/log/list_repo_commits/list_repo_refs/merge 的真实日常协作流。
* `cli`：围绕 `hubvault` CLI 的 git-like 使用路径，强调“命令形态接近 Git，但没有 workspace”。
* `maintenance`：`quick_verify()`、`full_verify()`、`get_storage_overview()`、`gc()`、`squash_history()` 的治理路径。
* `structure`：仓库磁盘布局、对象/refs/chunks/cache/txn/quarantine、detached view、安全模型与 `how it works`。

### 教程逐篇内容计划

`installation`
    覆盖 PyPI/GitHub 安装、Python 版本要求、Python 导入检查、CLI 帮助输出检查，以及文档入口链接。

`quick_start`
    覆盖初始化仓库、初始空 commit、上传模型文件、再次提交新版本、列出文件和提交、读取字节、下载单文件与快照，并明确指出下载路径是 detached 视图。

`workflow`
    覆盖创建功能分支、在分支上做多次 commit、打 tag、查看 log 与 refs、执行 fast-forward merge / merge commit，以及冲突结果的公开返回形状。

`cli`
    覆盖 `init`、`status`、`commit`、`log`、`branch`、`tag`、`merge`、`download`、`snapshot`、`verify` 的串联工作流，并展示典型输出形状。

`maintenance`
    覆盖校验仓库、分析空间占用、预览 GC、执行 GC、历史压缩（squash）前后的变化，以及“何时该用哪一个维护命令”的判断建议。

`structure`
    覆盖 repo 根目录的组织结构、对象 ID / 文件 `oid` / `sha256` 的公开与内部语义区别、chunk 触发条件、事务目录如何实现“本次操作从未发生过”的原子语义。

### Todo

* [x] 重写 README 的定位、核心能力、快速开始、兼容性边界、数据安全语义、文档导航和开发入口。
* [x] 更新 docs 首页与中英双语 landing page，移除“只有脚手架/尚未实现”的过期描述。
* [x] 扩展 `tutorials/installation/`，明确 `hubvault` / `hv` CLI 名称与最小安装检查流程。
* [x] 新增 `tutorials/quick_start/`，用真实 Python API 示例串起 init、commit、read、download、snapshot。
* [x] 新增 `tutorials/workflow/`，覆盖 branch、tag、log、refs、merge 与公开返回结果。
* [x] 新增 `tutorials/cli/`，覆盖 git-like CLI 的完整工作流与典型输出。
* [x] 新增 `tutorials/maintenance/`，覆盖 verify、storage overview、GC、squash history 与空间治理建议。
* [x] 新增 `tutorials/structure/`，解释 repo 磁盘布局、对象模型、chunk 规则、detached view 与事务/锁语义。
* [x] 为每篇教程补至少一个可直接执行的 `.demo.py` 或 `.demo.sh`，并补齐对应真实输出快照。
* [x] 所有示例都直接展示完整流程、真实输出形状和公开返回模型，不再只引用内部说明。
* [x] 同步记录 HF/Git 对齐结论、最小必要偏差和已知限制，避免用户误以为与 HF/Git 完全等价。
* [x] 在文档收尾阶段跑通 `make docs_en`、`make docs_zh`、`make package`；由于本阶段未修改 API 参考源码与生成结果，`make rst_auto` 无需额外执行。

### Checklist

* [x] README 与 docs 首页已经成为真实入口文档，而不是阶段性占位说明。
* [x] 每个教程主题目录都具备中英双语 `index` 页面与至少一个真实可执行示例文件。
* [x] README、API 文档和教程与当前代码行为一致，没有未来时伪实现。
* [x] 文档示例全部走公开 API / 公开 CLI，不依赖 private / protected 内容。
* [x] 教程覆盖正常路径、分支合并路径、恢复路径和空间治理路径。
* [x] `structure` 教程清楚解释了 repo 组织结构、存储格式和 `how it works`。
* [x] 关键示例中的路径、哈希、commit/refs 输出形状与真实实现一致。
* [x] README 与 docs 明确说明与 HF/Git 的对齐点和保留差异。
* [x] `make docs_en`、`make docs_zh` 和相关交付回归通过；本阶段未涉及 API 参考生成内容，因此未额外执行 `make rst_auto`。

## Phase 12. Benchmark 扩容与指标固化

### Goal

在已有 Phase 9 baseline 与 Phase 10 A/B 对比的基础上，把 benchmark 从“够回答当前瓶颈”的基线套件扩成“可长期决策、可解释、可回归”的完整性能体系。

### Status

已完成。

### Detailed Plan

详细指标口径、外部参考基线、数据集族、产物结构和 CI 策略见 `plan/init/08-phase12-benchmark-expansion.md`。

### Technical Focus

Phase 12 的重点不再是“再加几个 case”，而是把 benchmark 体系补成下面几层：

- 指标口径补全：对 bulk IO 保留 throughput 与 wall-clock，对 metadata-heavy 路径补 operations/s 与 tail latency，对重复/重叠数据补 write/space/cache amplification。
- memory / cache footprint 口径补全：为关键读/校验场景补 `peak_rss_bytes`、`peak_rss_over_baseline_bytes`、`retained_rss_delta_bytes`、`peak_traced_bytes` 与 `retained_traced_bytes`。
- 数据集族补全：在现有 `small-tree`、`large-single`、duplicate/overlap、maintenance-heavy 之外，补 `nested-small`、`mixed-model`、`history-deep`、`merge-heavy`、`cache-heavy` 等更接近日常仓库形状的数据集。
- 产物与环境元数据补全：让 benchmark 结果天然携带 commit id、Python 版本、平台、架构、runner 类型、dataset shape、threshold 与冷暖路径语义，便于长期比较。
- 长期回归口径补全：不再试图压成一个总分，而是至少分成 bandwidth、metadata、maintenance、amplification、stability 五类结果，避免一个单值掩盖真实退化。

### Todo

* [x] 以 Phase 9/10 现有 harness 为底座，补出 `nested-small`、`mixed-model`、`history-deep`、`merge-heavy`、`cache-heavy` 与 `verify-heavy` 数据集族。
* [x] 固化 Phase 12 的指标定义，至少明确 `latency_p50/p95/p99`、`latency_iqr`、`throughput_mib_per_sec`、`operations_per_sec`、`write_amplification`、`space_amplification_live`、`space_amplification_unique`、`cache_amplification` 与可选的 repo-layer `read_amplification`。
* [x] 继续采用 `pytest-benchmark` 的固定 rounds / pedantic 口径，并补齐 autosave / compare 的结果命名规范和产物目录结构。
* [x] 为 Linux 权威 baseline、Windows/macOS smoke、nightly pressure 三层执行口径补统一的 JSON summary schema 与 Markdown 摘要模板。
* [x] 为 benchmark 结果补环境元数据采集，至少包括 commit id、Python 版本、OS、架构、scale、dataset shape、chunk threshold 与 cold/warm 语义。
* [x] 为 memory / cache footprint 补统一指标口径，明确 `peak/retained RSS` 与 `peak/retained traced heap` 的定义、隔离执行方式和解释边界。
* [x] 明确哪些指标进入长期回归阈值，哪些指标只做趋势观察，避免把高噪声场景误设成硬门禁。
* [x] 把 Phase 12 的 metric glossary、MVP cut、deferred items 和 benchmark interpretation 规则固化到 `plan/init/08-phase12-benchmark-expansion.md`。

### Checklist

* [x] Phase 12 的 benchmark 结果不再只有“吞吐 + 总耗时”，而是同时覆盖带宽、metadata、amplification 与稳定性。
* [x] benchmark 指标定义都能明确回答“分子/分母是什么、是 wall-clock 还是 operation time、是 live 还是 unique 口径”。
* [x] benchmark summary 不会把 bandwidth 和 metadata 混成一个总分。
* [x] cold / warm、bulk IO / metadata、wall-clock / operation-seconds、logical bytes / physical bytes 这些口径边界全部被写清楚。
* [x] memory / resident footprint 已进入正式 metric glossary，并与 bandwidth / metadata 结果分离展示，不压成单一总分。
* [x] 基准结果在 Linux 上可长期复用，在 Windows/macOS 上至少保留 smoke 级可运行信号。
* [x] 所有新增 benchmark 场景仍只通过公开 API / 公开 CLI 驱动。

### Execution Record

- benchmarked code commit: `26a198711dc41e1bf2ec091361f4b64543a69210`（`26a1987`）
- complete runs:
  `make benchmark_phase12_smoke`
  `make benchmark_phase12_standard`
  `make benchmark_phase12_pressure`
- compare run:
  `make benchmark_phase12_compare BENCHMARK_BASELINE=build/benchmark/phase12/raw/autosave/Linux-CPython-3.10-64bit/0002_phase12-standard-full.json BENCHMARK_CANDIDATE=build/benchmark/phase12/raw/autosave/Linux-CPython-3.10-64bit/0003_phase12-standard-full.json BENCHMARK_PHASE12_COMPARE_JSON=build/benchmark/phase12/compare/phase12-standard-0002-vs-0003.json`
- core artifacts:
  `build/benchmark/phase12/summary/phase12-standard-full.json`
  `build/benchmark/phase12/summary/phase12-pressure-pressure.json`
  `build/benchmark/phase12/manifests/phase12-standard-full-manifest.json`
  `build/benchmark/phase12/manifests/phase12-pressure-pressure-manifest.json`
  `build/benchmark/phase12/compare/phase12-standard-0002-vs-0003.json`
- representative results:

| scenario | standard throughput / ratio | pressure throughput / ratio | note |
| --- | --- | --- | --- |
| `large_upload` | `208.70 MiB/s` / `57.84%` of host write baseline | `342.37 MiB/s` / `93.42%` of host write baseline | 写路径已经明显接近本机顺序写上限 |
| `large_read_range` | `223.96 MiB/s` / `2.14%` of host read baseline | `1030.40 MiB/s` / `10.35%` of host read baseline | 读路径仍远低于本机热读参考 |
| `hf_hub_download_cold` | `281.80 MiB/s` / `2.69%` of host read baseline | `271.45 MiB/s` / `2.73%` of host read baseline | detached view cold path 仍需继续收敛 |
| `hf_hub_download_warm` | `437.56 MiB/s` / `4.18%` of host read baseline | `349.13 MiB/s` / `3.51%` of host read baseline | warm path 已无缓存增量，但耗时链路仍重 |
- immediate next focus:
  Phase 13 应优先做 `read_range()`、cold/warm `hf_hub_download()`、`snapshot_download()` 的时间路径 profiling 与优化，其次再处理 `history_deep_listing` 与 `merge_heavy_non_fast_forward` 的 metadata 热点。

## Phase 13. Hotspot Profiling 与时间路径收敛

### Goal

基于 Phase 12 扩容后的 benchmark 与 profiling 结果，集中收敛当前仍有回退或波动的时间路径，优先解决真实用户可感知的 latency 与 metadata 热点。

### Status

进行中（13A 第二轮读路径收敛与 memory benchmark 接入已完成；`standard/full` 与 `pressure/pressure` 已复跑；13B metadata-heavy cache 仍未开始）。

### Detailed Plan

详细热点候选、profiling 工作流、优化顺序与回归口径见 `plan/init/09-phase13-hotspot-optimization.md`。

### Technical Focus

Phase 13 不会重新做大范围技术试验，而是只围绕 Phase 12 已证明的热点推进：

- `read_range()`：重点盯 `IndexStore.lookup()` / 可见索引构建 / 逐 chunk 校验链路。
- `hf_hub_download()` 与 `snapshot_download()`：重点盯 detached view 复用、目录扫描与 metadata 解析。
- `merge()` 与历史遍历：重点盯 merge-base、tree 反序列化、refs/reflog 解析与调用级缓存。
- 小文件树路径：重点盯 `list_repo_tree()`、`read_bytes()`、快照物化中的多文件重复扫描。
- memory / cache footprint：重点盯 bounded cache 上限、peak RSS / traced heap 口径，以及 repeated read / verify 下是否出现持续增长。

### Todo

* [x] 用 Phase 12 扩容后的 benchmark 结果重新排序热点，优先锁定 `read_range()`、cold/warm `hf_hub_download()` 与 `snapshot_download()` 的读路径回退。
* [x] 为 `read_range()` 固定 `cProfile` / opt-in memory probe 的 profiling 命令、输入 shape 与产物保存位置。
* [x] 为 warm `hf_hub_download()` 固定 `cProfile` / opt-in memory probe 的 profiling 命令、输入 shape 与产物保存位置。
* [x] 为 cold `hf_hub_download()` 固定 `cProfile` / opt-in memory probe 的 profiling 命令、输入 shape 与产物保存位置。
* [x] 为 `snapshot_download()` 固定 `cProfile` / opt-in memory probe 的 profiling 命令、输入 shape 与产物保存位置。
* [x] 为 `history_deep_listing` / `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()` 固定 profiling 命令、输入 shape 与产物保存位置。
* [x] 为 `merge_heavy_non_fast_forward` 固定 profiling 命令、输入 shape 与产物保存位置。
* [x] 把 `read_bytes()`、`read_range()`、`hf_hub_download()` 从单文件读先 `_snapshot_for_revision()` 的路径上拆下来，新增 direct path resolver。
* [x] 为 `_read_chunked_file_range()` 增加调用级 manifest cache。
* [x] 为 `_read_chunked_file_range()` 增加调用级 index segment cache。
* [x] 为 `_read_chunked_file_range()` 增加 batched chunk resolve，避免 per-chunk 重复 `lookup()`。
* [x] 为 `_read_chunked_file_range()` 增加 pack reader / file descriptor reuse。
* [x] 为 `_read_chunked_file_range()` 引入更低开销的输出 buffer 组织，减少小片段 `bytes` 拼接。
* [x] 为 `read_range()` 增加 bounded recent chunk cache，并用 index / pack state signature 保证命中不会掩盖磁盘损坏。
* [x] 为 commit/tree/file JSON 读取增加 bounded recent object payload cache，降低“刚写完立刻首读”的 path resolver 成本。
* [x] 为 warm `hf_hub_download()` 增加 managed-view metadata fast path，命中时直接返回现有 detached view。
* [x] 为 `_materialize_content_pool()` 增加 unchanged no-op fast path，避免重复落盘与 `fsync`。
* [ ] 为 `_ensure_detached_view()` 增加 sidecar/metadata-first fast path，避免 cold/warm materialization repair 时对现有目标做全文件重哈希。
* [x] 为 `snapshot_download()` 增加 `commit_id + allow_patterns + ignore_patterns` 级 quick return。
* [x] 为 `snapshot_download()` 增加 selective repair，只重建缺失或失配文件。
* [x] 为 `full_verify()` 增加共享 chunk context、对象去重与 chunked file 增量哈希，清除 verify-heavy 回退。
* [x] 为 benchmark runner 增加独立 memory probe 子进程，记录 `peak_rss_bytes` / `peak_rss_over_baseline_bytes` / `retained_rss_delta_bytes` / `peak_traced_bytes` / `retained_traced_bytes`。
* [x] 为关键读/校验路径补 repeated memory stability spot-check，确认没有出现明显单调膨胀。
* [ ] 为 `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()` 增加调用级 object payload cache。
* [ ] 为 `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()` 增加调用级 public commit/tree oid cache。
* [ ] 为 `list_repo_reflog()` 增加调用级或短时受保护的 reflog parse cache。
* [ ] 为 `merge_heavy_non_fast_forward` 增加 merge-base / ancestor distance cache。
* [ ] 为 `merge_heavy_non_fast_forward` 扩展 file identity cache 与 lazy snapshot 策略。
* [ ] 在 `pressure` 档继续收敛 `large_read_range()` 与 cold `hf_hub_download()`，并在必要时再评估 `pread` / `mmap` / 更低 copy 的 pack read path，同时明确跨平台 fallback。
* [x] 每轮优化后都重跑同一批 Phase 12 benchmark，并把“收益、无收益、局部回退”按场景写回计划文档。
* [x] 每轮优化后都记录相对 host local sequential I/O reference 的比值变化，避免只看绝对吞吐数值。
* [x] 明确哪些路径允许做可选的 OS-specific 实验，哪些路径必须继续保持 Python 3.7 与 Windows 兼容优先。

### Checklist

* [x] Phase 13 的每一项优化都能明确指向一个已测得的 benchmark 热点，而不是泛化的“代码看起来可以更快”。
* [x] 所有优化都保持公开 API 行为、磁盘协议、detached view 语义、回滚语义与跨平台兼容边界不变。
* [x] 已知回退路径至少有一轮 profiling 证据，而不是只看 benchmark 表格猜测原因。
* [x] benchmark 结果中的改进和回退都能追溯到具体 commit、具体场景和具体指标。
* [ ] 如果某个热点在零协议风险优化后收益不足，就明确停止，不再为了 benchmark 数字冒格式或兼容风险。
* [x] `large_read_range` 在 `standard` 档达到 `>= 800 MiB/s`。
* [ ] `large_read_range` 在 `pressure` 档达到 `>= 1800 MiB/s`。
* [x] `hf_hub_download_warm` 在 `standard` 档达到 `>= 900 MiB/s`。
* [x] `hf_hub_download_cold` 在 `standard` 档达到 `>= 600 MiB/s`。
* [x] `cache_heavy_warm_download` 在 `standard` 档达到 `>= 900 MiB/s`。
* [ ] `history_deep_listing` 的 `wall_clock_seconds` 降到 `<= 3.2s`。
* [x] `read_range()` 至少获得 `2x` 级别的稳定收益，且没有把写路径和空间放大重新打坏。
* [x] warm `hf_hub_download()` 至少获得 `2x` 级别的稳定收益，且没有把缓存语义和 detached view 语义重新打坏。
* [x] cold `hf_hub_download()` 至少获得 `2x` 级别的稳定收益，且没有把缓存语义和 detached view 语义重新打坏。
* [x] `snapshot_download()` 至少获得 `2x` 级别的稳定收益，且没有把路径保真和 selective repair 语义打坏。
* [ ] metadata-heavy 路径至少完成一轮 benchmark -> profiling -> optimize -> benchmark 的闭环，并把收益与残余风险写回计划文档。
* [x] `verify_heavy_full_verify` 已清除上一轮 compare alert，并回到显著高于 Phase 12 基线的吞吐区间。
* [x] `peak_rss_bytes` / `peak_rss_over_baseline_bytes` / `retained_rss_delta_bytes` / `peak_traced_bytes` / `retained_traced_bytes` 已进入标准 benchmark 摘要。
* [x] repeated memory stability spot-check 没有出现明显的持续单调增长；当前更像 bounded cache / allocator 保留，而不是线性泄漏。
* [x] 读路径新增 cache 具备显式上界：recent chunk cache `64 MiB`，recent object payload cache `256` entries。

### Execution Record

- benchmarked code commit: `cb030e0748d31a1ef79377b4484b6e2b766546d0`（`cb030e0`）
- compare baseline commit: `26a198711dc41e1bf2ec091361f4b64543a69210`（`26a1987`）
- previous Phase 13 checkpoint: `9b5e14010608c31b271459262dcaf1c540b5d1ee`（`9b5e140`）
- completed regression / benchmark:
  `make unittest`
  `./venv/bin/python -m tools.benchmark.run_phase9 --scale standard --scenario-set full --output build/benchmark/phase13/summary/phase13-standard-full-cb030e0.json --manifest-output build/benchmark/phase13/manifests/phase13-standard-full-cb030e0-manifest.json`
  `./venv/bin/python -m tools.benchmark.run_phase9 --scale pressure --scenario-set pressure --output build/benchmark/phase13/summary/phase13-pressure-pressure-cb030e0.json --manifest-output build/benchmark/phase13/manifests/phase13-pressure-pressure-cb030e0-manifest.json`
  `./venv/bin/python -m tools.benchmark.compare build/benchmark/phase12/summary/phase12-standard-full.json build/benchmark/phase13/summary/phase13-standard-full-cb030e0.json > build/benchmark/phase13/compare/phase12-vs-cb030e0.json`
  `./venv/bin/python -m tools.benchmark.compare build/benchmark/phase13/summary/phase13-standard-full-9b5e140.json build/benchmark/phase13/summary/phase13-standard-full-cb030e0.json > build/benchmark/phase13/compare/phase13-9b5e140-vs-cb030e0.json`
- core artifacts:
  `build/benchmark/phase13/summary/phase13-standard-full-cb030e0.json`
  `build/benchmark/phase13/manifests/phase13-standard-full-cb030e0-manifest.json`
  `build/benchmark/phase13/summary/phase13-pressure-pressure-cb030e0.json`
  `build/benchmark/phase13/manifests/phase13-pressure-pressure-cb030e0-manifest.json`
  `build/benchmark/phase13/compare/phase12-vs-cb030e0.json`
  `build/benchmark/phase13/compare/phase13-9b5e140-vs-cb030e0.json`
  `build/profiling/phase13/read_range_standard.prof`
  `build/profiling/phase13/hf_hub_download_warm_standard.prof`
  `build/profiling/phase13/hf_hub_download_cold_standard.prof`
  `build/profiling/phase13/snapshot_download_mixed_standard.prof`
  `build/profiling/phase13/history_deep_listing_standard.prof`
  `build/profiling/phase13/merge_heavy_non_fast_forward_standard.prof`
- representative `standard/full` results vs Phase 12 baseline and the previous Phase 13 checkpoint:

| scenario | Phase 12 baseline | Phase 13 (`9b5e140`) | Phase 13 (`cb030e0`) | delta vs `9b5e140` | note |
| --- | --- | --- | --- | --- | --- |
| `large_upload` | `208.70 MiB/s`, `p50 0.138884s` | `198.18 MiB/s`, `60.91%` of host write baseline, `p50 0.144452s` | `212.21 MiB/s`, `59.28%` of host write baseline, `p50 0.139349s` | throughput `+7.08%`, p50 `-3.53%` | 写路径回到 Phase 12 之上，但仍不是当前第一矛盾 |
| `large_read_range` | `223.96 MiB/s`, `p50 0.126996s` | `204.54 MiB/s`, `3.15%` of host read baseline, `p50 0.129064s` | `1628.66 MiB/s`, `16.22%` of host read baseline, `p50 0.116559s` | throughput `+696.25%`, p50 `-9.69%` | `standard` 已同时超过 hard `800 MiB/s` 与 stretch `1500 MiB/s` |
| `hf_hub_download_cold` | `281.80 MiB/s`, `p50 0.206108s` | `534.09 MiB/s`, `8.24%` of host read baseline, `p50 0.188860s` | `712.84 MiB/s`, `7.10%` of host read baseline, `p50 0.176921s` | throughput `+33.47%`, p50 `-6.32%` | `standard` 已越过 `>= 600 MiB/s` hard target |
| `hf_hub_download_warm` | `437.56 MiB/s`, `p50 0.232882s` | `15768.73 MiB/s`, `243.13%` of host read baseline, `p50 0.191718s` | `30075.19 MiB/s`, `299.44%` of host read baseline, `p50 0.178630s` | throughput `+90.73%`, p50 `-6.83%` | warm path 继续放大收益，不再构成主风险 |
| `cache_heavy_warm_download` | `450.89 MiB/s`, `p50 0.813272s` | `21828.10 MiB/s`, `336.56%` of host read baseline, `p50 0.562698s` | `37558.69 MiB/s`, `373.94%` of host read baseline, `p50 0.473485s` | throughput `+72.07%`, p50 `-15.85%` | cache-heavy warm 继续保持数量级优势 |
| `snapshot_download_small` | `1.06 MiB/s`, `p50 1.338577s` | `15.49 MiB/s`, `cache_amplification 1.053375`, `p50 0.927746s` | `18.24 MiB/s`, `cache_amplification 1.053375`, `p50 0.881316s` | throughput `+17.71%`, p50 `-5.00%` | quick return / selective repair 继续稳定生效 |
| `mixed_model_snapshot` | `228.24 MiB/s`, `p50 0.527436s` | `465.62 MiB/s`, `cache_amplification 1.000066`, `p50 0.474930s` | `778.70 MiB/s`, `cache_amplification 1.000066`, `p50 0.436494s` | throughput `+67.24%`, p50 `-8.09%` | mixed-model cold snapshot 明显继续抬升 |
| `history_deep_listing` | `8157.42 ops/s`, `wall 4.942012s` | `7204.14 ops/s`, `wall 4.662651s` | `14714.14 ops/s`, `wall 4.317284s` | ops/s `+104.25%`, wall `-7.41%` | metadata-heavy 仍未达 `<= 3.2s`，但调用链已有明显收敛 |
| `merge_heavy_non_fast_forward` | `48.56 MiB/s`, `p50 0.441694s` | `82.61 MiB/s`, `p50 0.407254s` | `71.37 MiB/s`, `p50 0.391287s` | throughput `-13.61%`, p50 `-3.92%` | 吞吐低于上一轮，但 wall/p50 继续改善，仍显著好于 Phase 12 |
| `verify_heavy_full_verify` | `43.52 MiB/s`, `p50 1.409059s` | `28.69 MiB/s`, `p50 1.705525s` | `739.34 MiB/s`, `p50 0.526066s` | throughput `+2477.02%`, p50 `-69.16%` | 上一轮 compare alert 已被清除，verify-heavy 不再是当前风险项 |

- representative `pressure/pressure` checkpoint:

| scenario | Phase 13 (`cb030e0`) | same-machine ratio | current judgment |
| --- | --- | --- | --- |
| `large_upload` | `349.26 MiB/s`, `p50 3.864512s` | `92.77%` of host write baseline | 压力档写路径已经非常接近本机顺序写参考 |
| `large_read_range` | `1041.87 MiB/s`, `p50 2.877622s` | `10.00%` of host read baseline | `pressure` 仍未达到 `>= 1800 MiB/s`，后续仍需继续收敛 |
| `hf_hub_download_cold` | `449.78 MiB/s`, `p50 5.910967s` | `4.32%` of host read baseline | 512 MiB 冷下载仍是压力档剩余热点 |
| `hf_hub_download_warm` | `1127753.30 MiB/s`, `p50 6.048054s` | `108.29x` of host read baseline | warm path 仅需继续做“不回退”监控 |
| `cache_heavy_warm_download` | `72234.76 MiB/s`, `p50 0.737435s` | `6.94x` of host read baseline | cache-heavy warm 在压力档也已完成收敛 |

- representative `standard/full` memory observation:

| scenario | peak RSS | peak RSS over baseline | peak traced heap | retained RSS delta | retained traced heap | note |
| --- | --- | --- | --- | --- | --- | --- |
| `host_io_read_baseline` | `54.25 MiB` | `16.94 MiB` | `16.01 MiB` | `1.07 MiB` | `0.01 MiB` | host 读基线本身就会拉起一部分 working set |
| `large_read_range` | `74.94 MiB` | `37.52 MiB` | `36.54 MiB` | `15.40 MiB` | `0.19 MiB` | 首读 fast path 会拉起 bounded chunk/object cache，但 Python retained 很低 |
| `hf_hub_download_cold` | `85.96 MiB` | `48.57 MiB` | `48.25 MiB` | `36.63 MiB` | `0.21 MiB` | 冷下载的 retained RSS 主要来自 detached view / allocator / page cache 保留 |
| `hf_hub_download_warm` | `86.97 MiB` | `49.54 MiB` | `48.22 MiB` | `1.70 MiB` | `0.21 MiB` | warm 路径没有再留下明显额外 resident footprint |
| `cache_heavy_warm_download` | `118.03 MiB` | `80.87 MiB` | `80.27 MiB` | `66.00 MiB` | `0.22 MiB` | process RSS 保留明显，但 traced heap 仍接近常数级 |
| `history_deep_listing` | `41.46 MiB` | `4.03 MiB` | `3.53 MiB` | `3.72 MiB` | `2.70 MiB` | metadata-heavy 路径当前 retained traced heap 最高，但仍在 MiB 级而非线性飙升 |
| `verify_heavy_full_verify` | `118.76 MiB` | `81.45 MiB` | `80.32 MiB` | `33.75 MiB` | `0.23 MiB` | verify-heavy 已不再留下显著 Python heap 残留 |

- supplementary repeated memory stability spot-check（同一进程、公开 API 重复调用）：

| scenario | repeat count | RSS first -> last | traced current first -> last | current judgment |
| --- | --- | --- | --- | --- |
| `large_read_range()` | `8` | `63.33 -> 63.46 MiB` | `1.0101 -> 1.0136 MiB` | 只出现 `~0.12 MiB` RSS 与 `~0.0035 MiB` traced 漂移，没有持续线性上升 |
| warm `hf_hub_download()` | `8` | `87.74 -> 87.74 MiB` | `0.0024 -> 0.0039 MiB` | RSS 完全持平，traced current 只增加 `~0.0015 MiB` |
| `verify_heavy_full_verify()` | `5` | `98.68 -> 98.78 MiB` | `0.0125 -> 0.0148 MiB` | verify 重复执行同样没有出现明显膨胀 |

- current judgment:
  `read_range()` 在 `standard` 档已经不只是过线，而是直接超过了 stretch target；当前最大的未完成项已经从 standard read-path 切换到 pressure read-path 和 metadata-heavy 路径。
  cold `hf_hub_download()`、`snapshot_download_small`、`mixed_model_snapshot` 与 `verify_heavy_full_verify` 都继续上升，其中 cold `hf_hub_download()` 已越过 hard target，verify-heavy compare alert 也已经被完全清除。
  `history_deep_listing` 已获得明显收益，但 `wall_clock_seconds` 仍在 `4.317284s`，说明 Phase 13B 的 object payload / public oid / reflog parse cache 仍然必须做。
  `pressure` 档 `large_read_range()` 目前只有 `1041.87 MiB/s`，距离 `>= 1800 MiB/s` 仍有明显差距；如果还要继续冲压力档目标，需要重点压 32 MiB 范围读和 512 MiB 冷物化上的大对象 working set。
  memory 结果当前更像“bounded cache + allocator / page cache 保留”，而不是“持续线性泄漏”：关键场景的 `retained_traced_bytes` 都保持在 `~0.2 MiB` 量级，repeated spot-check 也没有出现持续增长。
