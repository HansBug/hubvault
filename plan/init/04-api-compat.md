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

这几条就是 `hubvault` 当前 Phase 0-1 API 对齐的直接行为基准。

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
    GitCommitInfo,
    RepoFile,
    RepoFolder,
    LastCommitInfo,
    BlobLfsInfo,
    BlobSecurityInfo,
    VerifyReport,
    RepositoryNotFoundError,
    RepositoryAlreadyExistsError,
    EntryNotFoundError,
    RevisionNotFoundError,
    HubVaultValidationError,
    ConflictError,
    IntegrityError,
    VerificationError,
    LockTimeoutError,
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

- `CommitInfo` 保持 HF 风格的 `str` 兼容外观
- `repo_url`、`pr_revision`、`pr_num` 作为计算/派生字段保留
- 本地内部的 revision/tree/parents/message 不再暴露到公开 `CommitInfo`

与 `GitCommitInfo` 的关系：

- `CommitInfo`：用于 `create_commit()`、`reset_ref()` 这类“产生或指向某个 commit 结果”的 API
- `GitCommitInfo`：用于 `list_repo_commits()` 这类“枚举历史记录”的 API

二者同时存在不是本地双轨设计，而是直接遵循 HF 本身就存在的两套公开模型。

### 4.4 本地专属模型

以下模型当前没有直接 HF 对标，因此保持本地设计：

- `RepoInfo`
- `VerifyReport`

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

    def create_repo(self, *, default_branch="main", exist_ok=False) -> RepoInfo: ...
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
    def open_file(self, path_in_repo, *, revision=None) -> BinaryIO: ...
    def read_bytes(self, path_in_repo, *, revision=None) -> bytes: ...
    def hf_hub_download(self, filename, *, revision=None, local_dir=None) -> str: ...
    def reset_ref(self, ref_name, *, to_revision) -> CommitInfo: ...
    def quick_verify(self) -> VerifyReport: ...
```

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
- `LockTimeoutError`

这些异常保留的原因都是真实存在的本地事务/校验需求，而不是兼容外观。

## 8. 文件身份与下载语义

当前文件公开语义固定如下：

- `blob_id`：Git 风格 blob OID
- `oid`：当前公开 alias，同样指向 Git 风格 blob OID
- `sha256`：逻辑文件内容的裸 64 位 hex 摘要
- `etag`：下载接口面向用户的稳定 ETag
- `hf_hub_download()` 返回的路径：保留 repo 相对路径与文件名，不暴露内部 blob 名

注意：

- `sha256` 不带 `sha256:` 前缀，这是为了与 HF 公开字段风格保持一致
- repo 内部对象 ID 仍然允许使用带算法前缀的对象命名，不与公开字段混淆

## 9. 当前阶段的明确延后项

以下内容与 HF 还有差距，但当前是有意识延后，而不是遗漏：

- `list_repo_tree(..., expand=True)` / `get_paths_info(..., expand=True)`
- `snapshot_download()`
- branch/tag 全生命周期 API
- upload/delete 便捷 API
- 基于安全扫描的 `RepoFile.security`
- 基于历史反查的 `last_commit` 自动填充

这些项进入后续 phase 时，仍然要遵守同一条原则：

- 能对齐 HF 的地方优先对齐
- 真无意义的参数和字段不保留
- 偏差必须有本地设计理由且写入文档
