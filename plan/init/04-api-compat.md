# 04. Python API 与兼容层设计

## 1. 设计目标

当前 `hubvault` 的公开 Python API 采用一条明确原则：

- 只要 `huggingface_hub` 有真实对标对象，就默认以它为兼容基准
- 除非本地嵌入式仓库场景确有必要，否则不主动发明另一套公开语义
- 仅保留在本地仓库中有真实行为的参数、字段和返回值
- 任何偏差都必须是“有原因的最小偏差”，并在本文件和 `AGENTS.md` 中明确记录

这里说的“兼容”不是逐字复制远端 Hub 的 HTTP/鉴权/PR 机制，而是：

- 方法名和主要参数形状尽量一致
- 返回对象字段名和核心语义尽量一致
- 文件路径、`blob_id`、`oid`、`sha256` 等公开元数据尽量一致
- 缺失路径、commit 列表、树遍历、下载路径等用户可感知行为尽量一致

## 2. 真实 HF 基准

本仓库已直接用真实 `huggingface_hub` 调用公开仓库做过运行验证，当前对齐基线如下：

- `HfApi.repo_info("bert-base-uncased", files_metadata=True)` 返回 `ModelInfo`，不是通用 `RepoInfo`
- `HfApi.get_paths_info("bert-base-uncased", ["config.json", "nonexistent.file", "onnx"])`
  只返回存在路径，缺失路径会被忽略，不抛异常
- `HfApi.list_repo_tree("bert-base-uncased")` 返回 `RepoFile` / `RepoFolder`
- `HfApi.list_repo_tree("gpt2", path_in_repo="onnx", recursive=True)` 会递归返回子树
- `HfApi.list_repo_commits("gpt2", formatted=True)` 返回 `GitCommitInfo`，并填充
  `formatted_title` / `formatted_message`
- `hf_hub_download("gpt2", "config.json")` 返回普通文件路径，并保留
  `.../config.json` 这样的 repo 相对路径后缀

这几条就是 `hubvault` 当前 Phase 0-4 API 对齐的直接行为基准。

补充结论：

- `HfApi.merge_pull_request(...)` 只覆盖远端 PR 合并工作流，HF 当前没有直接对标“本地 branch -> branch merge”的公开 Python API
- 因此 `hubvault.merge()` 作为本地嵌入式仓库扩展保留自有公开模型，但仍尽量遵循 Git 用户熟悉的 merge 结果与冲突语义

## 3. 当前公开入口

当前推荐从包根导入的公开入口如下：

```python
from hubvault import (
    HubVaultApi,
    CommitOperationAdd,
    CommitOperationDelete,
    CommitOperationCopy,
    RepoInfo,
    CommitInfo,
    MergeConflict,
    MergeResult,
    GitCommitInfo,
    GitRefInfo,
    GitRefs,
    ReflogEntry,
    RepoFile,
    RepoFolder,
    LastCommitInfo,
    BlobLfsInfo,
    BlobSecurityInfo,
    VerifyReport,
    StorageSectionInfo,
    StorageOverview,
    GcReport,
    SquashReport,
    RepositoryNotFoundError,
    RepositoryAlreadyExistsError,
    EntryNotFoundError,
    RevisionNotFoundError,
    HubVaultValidationError,
    ConflictError,
    IntegrityError,
    VerificationError,
)
```

兼容层说明：

- 路径相关公开返回值统一为 `RepoFile` / `RepoFolder`
- 异常名统一收敛到与 HF 更接近的 `RepositoryNotFoundError`、`EntryNotFoundError`、`RevisionNotFoundError`

## 4. 模型对齐结论

### 4.1 文件与目录模型

当前公开返回值已经统一对齐到 HF 风格：

| hubvault | HF 对标 | 当前状态 |
| --- | --- | --- |
| `RepoFile.path` | `RepoFile.path` | 已对齐 |
| `RepoFile.size` | `RepoFile.size` | 已对齐 |
| `RepoFile.blob_id` | `RepoFile.blob_id` | 已对齐 |
| `RepoFile.lfs` | `RepoFile.lfs` | 已对齐 |
| `RepoFile.last_commit` | `RepoFile.last_commit` | 字段已对齐，当前 Phase 1 默认未填充 |
| `RepoFile.security` | `RepoFile.security` | 字段已对齐，当前 Phase 1 默认未填充 |
| `RepoFolder.path` | `RepoFolder.path` | 已对齐 |
| `RepoFolder.tree_id` | `RepoFolder.tree_id` | 已对齐 |
| `RepoFolder.last_commit` | `RepoFolder.last_commit` | 字段已对齐，当前 Phase 1 默认未填充 |

本地扩展字段：

- `RepoFile.oid`
- `RepoFile.sha256`
- `RepoFile.etag`

这些字段保留的原因是本地仓库明确把文件身份、下载 ETag 和逻辑内容哈希作为公开契约的一部分，且用户已经要求必须能直接拿到。

对齐补充结论：

- `RepoFolder.tree_id` 现在公开返回 40 位 git tree SHA-1 hex，而不是内部 `sha256:<hex>` 对象 ID
- 普通文件 `RepoFile.blob_id` / `RepoFile.oid` 返回 git blob OID；大文件则返回 canonical LFS pointer 的 git blob OID
- `RepoFile.sha256` 与 `RepoFile.lfs.sha256` 一律返回裸 64 位 hex，与 HF 公开字段风格一致

### 4.2 Commit 列表模型

`GitCommitInfo` 已对齐 HF 公开字段：

- `commit_id`
- `authors`
- `created_at`
- `title`
- `message`
- `formatted_title`
- `formatted_message`

当前行为约束：

- `commit_id` 现在公开返回 40 位 git commit SHA-1 hex
- `formatted=False` 时，两个 `formatted_*` 字段为 `None`
- `formatted=True` 时，按 HF 风格填入 HTML 转义后的内容
- 当存储的 commit 文本包含空行正文时，会自动拆成 title/body，与 Git/HF 列表语义一致

### 4.3 Commit 创建结果模型

`CommitInfo` 现在直接沿用 HF 的公开职责边界，不再混入本地内部 commit 元数据。

公开字段：

- `commit_url`
- `commit_message`
- `commit_description`
- `oid`
- `pr_url`
- `repo_url`
- `pr_revision`
- `pr_num`

额外对齐点：

- `CommitInfo.oid` 现在公开返回 40 位 git commit SHA-1 hex
- `CommitInfo` 保持 HF 风格的 `str` 兼容外观
- `repo_url`、`pr_revision`、`pr_num` 作为计算/派生字段保留
- 本地内部的 revision/tree/parents/message 不再暴露到公开 `CommitInfo`

与 `GitCommitInfo` 的关系：

- `CommitInfo`：用于 `create_commit()`、`reset_ref()` 这类“产生或指向某个 commit 结果”的 API
- `GitCommitInfo`：用于 `list_repo_commits()` 这类“枚举历史记录”的 API

二者同时存在不是本地双轨设计，而是直接遵循 HF 本身就存在的两套公开模型。

### 4.4 Git refs 与 reflog

当前 Phase 2 已新增：

- `GitRefInfo`
- `GitRefs`
- `ReflogEntry`

对齐结论：

- `GitRefInfo` / `GitRefs` 直接按 HF 公开字段命名实现
- `GitRefInfo.target_commit`、`RepoInfo.head`、`ReflogEntry.old_head/new_head`、`MergeResult` 里的 commit 引用字段现在统一公开为 40 位 git commit SHA-1 hex
- `GitRefs.pull_requests` 与 HF 一致，默认 `None`，仅在 `include_pull_requests=True` 时返回 `[]`
- 本地必要偏差只有一处：
  `create_repo()` 现在会自动生成空树 `Initial commit`，因此正常仓库的 branch head 不再为空；但为了兼容恢复场景、历史遗留空 ref 或手工损坏仓库的诊断，`GitRefInfo.target_commit` 仍保持 `Optional[str]`
- `ReflogEntry` 没有直接 HF 对标，属于本地审计/恢复模型
- refs / reflog / 对象存储在磁盘上仍继续使用内部 `sha256:<hex>` 对象 ID；这是实现细节，不再直接泄露到公开表面

### 4.5 Merge 模型

当前 Phase 5 已新增：

- `MergeConflict`
- `MergeResult`

对齐结论：

- HF 没有直接对标“本地 branch merge”的公开返回模型，因此这两者保留本地设计
- 字段命名遵循现有 HF 风格偏好，公开返回短而直观的 `status`、`target_revision`、`source_revision`、`head_after`、`conflicts`
- 冲突不再依赖异常字符串，而是返回结构化 `MergeConflict`
- merge 成功时仍复用 HF 风格 `CommitInfo` 作为结果里的 `commit`

### 4.6 Phase 4 维护模型

以下模型是本地维护与空间治理公开表面：

- `StorageSectionInfo`
- `StorageOverview`
- `GcReport`
- `SquashReport`

对齐结论：

- HF 没有直接对标这些本地嵌入式维护模型，因此保留本地设计
- 字段命名仍遵守 HF 风格偏好，尽量使用短、直观、面向结果的公开字段
- 这些模型只暴露公开维护结果，不暴露内部 pack/object/chunk 路径推导细节

### 4.7 本地专属模型

以下模型当前没有直接 HF 对标，因此保持本地设计：

- `RepoInfo`
- `MergeConflict`
- `MergeResult`
- `ReflogEntry`
- `VerifyReport`
- `StorageSectionInfo`
- `StorageOverview`
- `GcReport`
- `SquashReport`

其中：

- `RepoInfo` 面向本地嵌入式仓库，不复用远端 `ModelInfo` / `DatasetInfo`
- `VerifyReport` 面向本地校验与诊断

## 5. CommitOperation 对齐结论

### 5.1 当前签名

```python
CommitOperationAdd(path_in_repo, path_or_fileobj)
CommitOperationDelete(path_in_repo, is_folder="auto")
CommitOperationCopy(src_path_in_repo, path_in_repo, src_revision=None)
```

### 5.2 与 HF 的对比

- `CommitOperationAdd`：已对齐 HF 主签名
- `CommitOperationDelete`：已对齐 HF 主签名
- `CommitOperationCopy`：已对齐 HF 主签名

刻意未保留的 HF 内部参数：

- `CommitOperationCopy._src_oid`
- `CommitOperationCopy._dest_oid`

原因：

- 它们在本地仓库中没有真实公开行为
- 保留只会形成死参数，违反“无效兼容参数必须删除”的规则

## 6. HubVaultApi 方法对齐结论

### 6.1 当前公开方法

```python
class HubVaultApi:
    def __init__(self, repo_path, revision="main") -> None: ...

    def create_repo(
        self,
        *,
        default_branch="main",
        exist_ok=False,
        large_file_threshold=16777216,
    ) -> RepoInfo: ...

`create_repo()` 当前约束补充：

- 创建仓库后会自动产生一个空树 `Initial commit`
- 因此 `RepoInfo.head` 在正常新仓库中应立即为非空
- `list_repo_commits()` 在新仓库上至少会返回这一条初始历史
    def repo_info(self, *, revision=None) -> RepoInfo: ...

    def create_commit(
        self,
        operations=(),
        *,
        commit_message,
        commit_description=None,
        revision=None,
        parent_commit=None,
    ) -> CommitInfo: ...

    def merge(
        self,
        source_revision,
        *,
        target_revision=None,
        parent_commit=None,
        commit_message=None,
        commit_description=None,
    ) -> MergeResult: ...
    def get_paths_info(self, paths, *, revision=None) -> List[Union[RepoFile, RepoFolder]]: ...
    def list_repo_tree(
        self,
        path_in_repo=None,
        *,
        recursive=False,
        revision=None,
    ) -> List[Union[RepoFile, RepoFolder]]: ...
    def list_repo_files(self, *, revision=None) -> Sequence[str]: ...
    def list_repo_commits(self, *, revision=None, formatted=False) -> Sequence[GitCommitInfo]: ...
    def list_repo_refs(self, *, include_pull_requests=False) -> GitRefs: ...
    def create_branch(self, *, branch, revision=None, exist_ok=False) -> None: ...
    def delete_branch(self, *, branch) -> None: ...
    def create_tag(self, *, tag, tag_message=None, revision=None, exist_ok=False) -> None: ...
    def delete_tag(self, *, tag) -> None: ...
    def list_repo_reflog(self, ref_name, *, limit=None) -> Sequence[ReflogEntry]: ...
    def open_file(self, path_in_repo, *, revision=None) -> BinaryIO: ...
    def read_bytes(self, path_in_repo, *, revision=None) -> bytes: ...
    def read_range(self, path_in_repo, *, start, length, revision=None) -> bytes: ...
    def hf_hub_download(self, filename, *, revision=None, local_dir=None) -> str: ...
    def snapshot_download(
        self,
        *,
        revision=None,
        local_dir=None,
        allow_patterns=None,
        ignore_patterns=None,
    ) -> str: ...
    def upload_file(
        self,
        *,
        path_or_fileobj,
        path_in_repo,
        revision=None,
        commit_message=None,
        commit_description=None,
        parent_commit=None,
    ) -> CommitInfo: ...
    def upload_folder(
        self,
        *,
        folder_path,
        path_in_repo=None,
        commit_message=None,
        commit_description=None,
        revision=None,
        parent_commit=None,
        allow_patterns=None,
        ignore_patterns=None,
        delete_patterns=None,
    ) -> CommitInfo: ...
    def upload_large_folder(self, *, folder_path, revision=None, allow_patterns=None, ignore_patterns=None) -> CommitInfo: ...
    def delete_file(
        self,
        path_in_repo,
        *,
        revision=None,
        commit_message=None,
        commit_description=None,
        parent_commit=None,
    ) -> CommitInfo: ...
    def delete_folder(
        self,
        path_in_repo,
        *,
        revision=None,
        commit_message=None,
        commit_description=None,
        parent_commit=None,
    ) -> CommitInfo: ...
    def reset_ref(self, ref_name, *, to_revision) -> CommitInfo: ...
    def quick_verify(self) -> VerifyReport: ...
    def full_verify(self) -> VerifyReport: ...
    def get_storage_overview(self) -> StorageOverview: ...
    def gc(self, *, dry_run=False, prune_cache=True) -> GcReport: ...
    def squash_history(
        self,
        ref_name,
        *,
        root_revision=None,
        commit_message=None,
        commit_description=None,
        run_gc=True,
        prune_cache=False,
    ) -> SquashReport: ...
```

当前 Phase 5 对齐说明：

- `read_range()` 是本地嵌入式仓库新增的必要读取 API，没有直接 HF Python 方法对标，但语义遵循“只返回请求范围，不暴露可写别名”
- `upload_large_folder()` 保留 HF 方法名，但本地实现坚持单事务原子提交，因此返回一个 `CommitInfo`，而不是像远端多 commit 流程那样返回 `None`
- 对 `storage_kind="chunked"` 的文件，`RepoFile.blob_id` / `RepoFile.oid` 使用 canonical LFS pointer 的 git blob OID，`RepoFile.sha256` 与 `RepoFile.lfs.sha256` 都使用真实文件内容的裸 hex
- `full_verify()`、`get_storage_overview()`、`gc()`、`squash_history()` 没有 HF 远端对标方法，但命名和返回职责遵循“只公开真实可用行为”的同一原则

### 6.2 已对齐行为

#### `create_commit`

当前公开语义：

- `commit_message` 是主标题参数，命名与 HF 一致
- `commit_description` 独立提供正文，命名与 HF 一致
- `parent_commit` 用作乐观并发保护，命名与 HF 一致
- 若 `commit_description` 未提供，但 `commit_message` 自身包含空行正文，仍会按 Git/HF 习惯拆成 title/body
- 若 `parent_commit` 省略，则默认基于当前 branch head 提交，不强制要求显式传入

刻意删除的旧本地参数：

- `expected_head`
- `metadata`

原因：

- `expected_head` 与 `parent_commit` 重复
- `metadata` 当前没有真实落盘和公开语义

#### `get_paths_info`

当前公开语义已经贴齐 HF：

- 接受 `str` 或 `Sequence[str]`
- 缺失路径被忽略，不抛异常
- 返回 `RepoFile` / `RepoFolder`

#### `list_repo_tree`

当前公开语义：

- `path_in_repo=None` 表示根目录
- `recursive=False` 默认只返回直接子项
- `recursive=True` 会递归展开
- 返回 `RepoFile` / `RepoFolder`

当前保留的最小偏差：

- HF 返回可迭代对象；本地当前直接返回具体 `list`
- HF 存在 `expand=True`，可填 `last_commit` / `security`
- 本地当前未提供 `expand`，因为 Phase 1 还没有独立实现这组增强行为

#### `list_repo_commits`

当前公开语义：

- 方法名与 HF 一致
- 保留 `revision`、`formatted` 这两个真实有意义的参数
- 丢弃 `repo_id`、`repo_type`、`token` 这类远端/传输参数
- 当前已经不再把历史遍历限制在 first-parent 线性链，而是按稳定的 parent-first 顺序遍历可达 commit DAG，使 merge commit 与第二父链路可见
- 当 `revision` 传入公开 40 位 git commit OID 时，`hubvault` 会把它解析回对应的内部 commit 对象并继续工作

#### `merge`

这是本地嵌入式仓库新增的公开写 API，没有直接 HF branch-merge 方法对标。

当前公开语义：

- `source_revision` 接受 branch/tag/commit
- `target_revision` 只接受 branch，因为该操作会真实更新目标 ref
- 返回 `MergeResult`，用 `status` 明确区分 `merged` / `fast-forward` / `already-up-to-date` / `conflict`
- 冲突通过 `MergeConflict` 列表结构化返回，而不是靠异常消息让调用方自行解析
- 成功 merge 时仍返回 HF 风格 `CommitInfo` 作为结果里的 `commit`
- `parent_commit` 保留为乐观并发保护参数，因为它在本地仓库中有真实行为

最小必要偏差：

- HF 只有远端 `merge_pull_request(...)`，没有本地 branch merge，因此 `MergeResult` / `MergeConflict` 属于本地扩展
- fast-forward 与 already-up-to-date 结果不会强行伪造新 commit，而是直接返回现有 head 对应的 `CommitInfo`

#### `list_repo_refs` / `create_branch` / `delete_branch` / `create_tag` / `delete_tag`

当前公开语义：

- 方法名、主参数名和返回模型与 HF 一致
- `list_repo_refs()` 返回 `GitRefs`
- `create_branch()` / `delete_branch()` / `create_tag()` / `delete_tag()` 返回 `None`
- `create_*` 的 `exist_ok` 保留，因为在本地确有真实行为
- `include_pull_requests` 保留，但本地只在请求时返回空列表，不伪造 PR refs

必要偏差：

- 本地 default branch 允许为空 ref，因此 branch 列表里的 `target_commit` 可以是 `None`
- 删除 default branch 会直接抛本地 `ConflictError`

#### `upload_file` / `upload_folder`

当前公开语义：

- 方法名、主要参数名和返回类型对齐 HF
- 都返回 `CommitInfo`
- 默认 commit message 也采用 HF 同类风格，只把品牌前缀从 `huggingface_hub` 换成 `hubvault`
- `upload_folder()` 保留 `allow_patterns` / `ignore_patterns` / `delete_patterns`
- `.git/` 子目录会被忽略

当前刻意删除的远端参数：

- `repo_id`
- `repo_type`
- `token`
- `create_pr`
- `run_as_future`

#### `delete_file` / `delete_folder`

当前公开语义：

- 方法名、主要参数名和返回类型对齐 HF
- 默认 commit message 延续 HF 模板，只把品牌从 `huggingface_hub` 换成 `hubvault`
- 返回值直接是 `CommitInfo`

#### `snapshot_download`

当前公开语义：

- 方法名、主要参数名和返回职责对齐 HF
- 保留 `revision`、`local_dir`、`allow_patterns`、`ignore_patterns`
- 默认返回 repo 内部缓存快照目录；传入 `local_dir` 时返回外部目录真实路径
- 外部 `local_dir` 模式会在目录下写入 `.cache/hubvault/snapshot.json` 以维护受管文件清单
- 返回目录中的文件路径仍保留 repo 相对路径

本地必要偏差：

- 不保留 `cache_dir`、`local_files_only`、`force_download`、`local_dir_use_symlinks`、`tqdm_class` 等远端/缓存策略参数
- 为避免把用户读取视图变成 repo 内部可写别名，`local_dir` 不允许指向 repo root 内部
- 默认缓存目录布局仍是 repo 内 `cache/files/<view_key>/...` 与 `cache/snapshots/<view_key>/...`，而不是 HF 的全局缓存目录；这是本地自包含仓库设计的必要偏差

#### `full_verify`

这是本地专属维护 API，没有直接 HF 远端对标。

当前公开语义：

- 返回 `VerifyReport`
- 在 `quick_verify()` 之上继续检查 pack/index/manifest 和 chunk checksum
- 允许把缓存视图污染报告为 warning，而不把用户可重建视图直接等同于仓库损坏

#### `get_storage_overview`

这是本地专属维护 API，没有直接 HF 远端对标。

当前公开语义：

- 返回 `StorageOverview`
- 明确区分总占用、当前 live refs 所需占用、历史保留占用、可立即 GC 的占用、可清缓存占用、临时区域占用
- 以 `StorageSectionInfo` 列出各主要目录/数据类型的占用与安全释放建议

#### `gc`

这是本地专属维护 API，没有直接 HF 远端对标。

当前公开语义：

- 保留 `dry_run` 与 `prune_cache` 这两个真实有意义的参数
- 维护 pass 会先完整校验仓库，再重写 live chunk pack/index，之后隔离并删除不可达对象
- 返回 `GcReport`，显式给出对象、chunk、cache、temporary 各自释放量

#### `squash_history`

这是本地专属维护 API，没有直接 HF 远端对标。

当前公开语义：

- 仅支持 branch ref，不对 tag 做历史重写
- `root_revision` 指定“最老保留 commit”；省略时会把当前 branch head 折叠成一个新的 root commit
- `run_gc=True` 时会在重写后直接执行 `gc()`
- 返回 `SquashReport`，并显式报告仍然阻塞旧历史释放的其他 refs

当前刻意保留的限制：

- 只重写单个 branch，不自动改写其他 refs
- 阻塞 refs 只报告，不自动处理

#### `list_repo_reflog`

这是本地专属公开 API，没有直接 HF 对标，但遵循同一个公开原则：

- 只暴露真实可用且可测试的行为
- 返回稳定的 dataclass 模型 `ReflogEntry`
- 支持 branch/tag 的短名查询和完整 ref 名查询
- 当 branch 与 tag 短名冲突时，要求调用方显式传完整 ref 名

#### `hf_hub_download`

虽然是本地仓库 API，但仍保留 HF 同名方法，因为它对应的是用户最熟悉的单文件下载入口。

当前行为约束：

- 返回值必须是普通文件路径
- 路径末尾必须保留 repo 相对路径与文件名
- 返回的路径必须是与 repo 真相隔离的用户视图
- 用户删除或改写该路径，不得破坏正式对象
- 再次调用时必须能重建该用户视图

### 6.3 当前未保留的远端参数

以下参数当前明确不保留：

- `repo_id`
- `repo_type`
- `token`
- `create_pr`
- `num_threads`
- `run_as_future`
- `cache_dir`
- `force_download`
- `local_files_only`
- `local_dir_use_symlinks`
- `expand`（当前阶段未实现真实增强行为，因此不保留）

删除原则：

- 只要参数在本地 repo 设计中不会改变验证、存储、输出或用户体验，就不应保留

## 7. 异常模型对齐结论

### 7.1 已对齐或接近对齐的异常

| hubvault | HF 对标 | 说明 |
| --- | --- | --- |
| `RepositoryNotFoundError` | `RepositoryNotFoundError` | 语义已对齐 |
| `EntryNotFoundError` | `EntryNotFoundError` | 语义已对齐 |
| `RevisionNotFoundError` | `RevisionNotFoundError` | 语义已对齐 |
| `HubVaultValidationError` | `HFValidationError` | 名字改为项目名，但语义一致；并继承 `ValueError` |
| `UnsupportedPathError` | `HFValidationError` 子类语义 | 作为本地更细的路径/引用名校验错误 |

### 7.2 本地专属异常

以下异常没有直接 HF 公开对标，属于本地嵌入式仓库额外能力：

- `RepositoryAlreadyExistsError`
- `ConflictError`
- `IntegrityError`
- `VerificationError`

这些异常保留的原因都是真实存在的本地事务/校验需求，而不是兼容外观。

## 8. 文件身份与下载语义

当前文件公开语义固定如下：

- `RepoInfo.head` / `CommitInfo.oid` / `GitCommitInfo.commit_id` / `GitRefInfo.target_commit`：Git 风格 commit OID
- `RepoFolder.tree_id`：Git 风格 tree OID
- `blob_id`：Git 风格 blob OID
- `oid`：当前公开 alias，同样指向 Git 风格 blob OID
- `sha256`：逻辑文件内容的裸 64 位 hex 摘要
- `etag`：下载接口面向用户的稳定 ETag
- `hf_hub_download()` 返回的路径：保留 repo 相对路径与文件名，不暴露内部 blob 名

注意：

- commit/tree/blob 这些公开 OID 的格式需要尽可能与 Git / HF 主流行为一致，因此统一使用裸 40 位 hex
- `sha256` 不带 `sha256:` 前缀，这是为了与 HF 公开字段风格保持一致
- repo 内部对象 ID 仍然允许使用带算法前缀的对象命名，不与公开字段混淆

## 8.1 Phase 7 对拍结论

当前已经通过真实 baseline 确认以下对齐结论：

- 小文件历史的公开 commit OID、tree OID、blob OID 可以与真实 `git` 计算结果逐项对齐
- 大文件公开 `blob_id` / `oid` 与 canonical Git-LFS pointer 的 git blob OID 对齐，`sha256` 保持裸 64 位 hex
- `list_repo_commits()`、`list_repo_refs()`、`repo_info()`、`list_repo_reflog()`、`merge()`、`squash_history()` 里的公开 commit 引用字段都不再泄露内部 `sha256:<hex>`
- `hf_hub_download()` / `snapshot_download()` 仍保持 repo 相对路径后缀保真，并且 `snapshot_download()` 对外记录公开 commit OID

当前保留的最小必要偏差：

- repo 内部对象存储、refs 真相和 reflog 真相继续使用内部 `sha256:<hex>` 对象 ID；这是为了保持自包含对象仓库的实现稳定性
- 默认缓存布局仍是 repo 内部的自包含缓存，而不是 HF 全局缓存
- 当前没有作者身份配置 API，因此公开 commit OID 使用固定的本地身份约定生成；`GitCommitInfo.authors` 仍保持空列表

## 9. 当前阶段的明确延后项

以下内容与 HF 还有差距，但当前是有意识延后，而不是遗漏：

- `list_repo_tree(..., expand=True)` / `get_paths_info(..., expand=True)`
- 基于安全扫描的 `RepoFile.security`
- 基于历史反查的 `last_commit` 自动填充
- 远端 Hub 的 PR / token / repo_type / endpoint 体系

这些项进入后续 phase 时，仍然要遵守同一条原则：

- 能对齐 HF 的地方优先对齐
- 真无意义的参数和字段不保留
- 偏差必须有本地设计理由且写入文档
