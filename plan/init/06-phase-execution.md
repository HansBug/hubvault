# 06. 分阶段执行计划

## 总体策略

执行顺序遵循一个原则：先交付最小可用、可验证、可回归的本地仓库核心，再逐步扩充大文件、维护和性能能力。

在当前 Phase 0-4 已经落地的前提下，后半程不再把“功能补齐、对拍、异常安全、性能和文档交付”混成一个大阶段，而是按下面顺序拆开推进：

1. 先补 `merge()` 本体与冲突模型
2. 再补基于公开 API 的 Git-like 本地 CLI
3. 再与真实 `git` / `git-lfs` / `huggingface_hub` 做行为对拍
4. 再补极端场景与故障注入测试，把“最坏等效于本次操作从未发生过”压实
5. 然后再做性能基线与可选优化
6. 最后统一收尾文档、README、教程与交付检查

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
- 当前剩余工作会从 Phase 6 之后继续拆成后续四个顺序 phase，分别处理真实对拍、异常安全、性能与文档交付，避免把 correctness 验证与性能/文档收尾混做。

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
10. 性能基线 / 可选优化
11. 文档 / README / 教程 / 交付收尾

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

## Phase 10. 文档、README 与教程

### Goal

在前述功能、对拍和安全结论稳定后，统一收尾用户文档、README、教程与交付检查，让外部使用者看到的公开说明和真实实现完全一致。

### Status

未开始。

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

Phase 10 计划新增并维护以下教程主题：

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
