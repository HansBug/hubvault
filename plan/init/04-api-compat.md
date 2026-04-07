# 04. Python API 与兼容层设计

## 1. 设计目标

API 目标不是逐行复制 `huggingface_hub`，而是：

- 保留 repo/file 操作的主要调用手感
- 以 `HubVaultApi` 为统一公开入口
- 去掉依赖远端 HTTP 平台的能力
- 增加适合本地嵌入式仓库的 `verify`、`gc`、`compact`、`reset` 等能力
- 确保单元测试可以只通过公开 API 完成，不需要触碰 private / protected 实现
- 明确仓库是自包含 artifact，API 不能把仓库正确性建立在外部路径状态之上

## 2. 推荐公开入口

建议对外主入口保持极简：

```python
from hubvault import (
    HubVaultApi,
    CommitOperationAdd,
    CommitOperationDelete,
    CommitOperationCopy,
    RepoInfo,
    CommitInfo,
    GitCommitInfo,
    PathInfo,
    VerifyReport,
)
```

`hubvault.__init__` 应只做薄 re-export，不承载业务逻辑。

### 2.1 当前已落地公开入口

当前 MVP 已经对外暴露如下公开入口与模型：

- `HubVaultApi`
- `CommitOperationAdd`
- `CommitOperationDelete`
- `CommitOperationCopy`
- `RepoInfo`
- `CommitInfo`
- `GitCommitInfo`
- `PathInfo`
- `BlobLfsInfo`
- `VerifyReport`
- `HubVaultError` 及其公开子类

这些符号当前已经由 `hubvault.__init__` 统一 re-export，测试也应优先从这里或其对应公开模块导入。

## 3. 公开数据模型

建议优先定义以下公开 dataclass：

- `RepoInfo`
- `RefInfo`
- `CommitInfo`
- `GitCommitInfo`
- `PathInfo`
- `BlobLfsInfo`
- `VerifyReport`
- `MergeResult`

### 3.1 模型草图

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RepoInfo:
    repo_path: str
    format_version: int
    default_branch: str
    head: Optional[str]
    refs: List[str]


@dataclass(frozen=True)
class PathInfo:
    path: str
    path_type: str
    size: int
    oid: Optional[str]
    blob_id: Optional[str]
    sha256: Optional[str]
    etag: Optional[str]


@dataclass(frozen=True)
class GitCommitInfo:
    commit_id: str
    authors: List[str]
    created_at: datetime
    title: str
    message: str
    formatted_title: Optional[str]
    formatted_message: Optional[str]


@dataclass(frozen=True)
class BlobLfsInfo:
    size: int
    sha256: str
    pointer_size: int


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    checked_refs: List[str]
    warnings: List[str]
    errors: List[str]
```

## 4. Commit 操作模型

建议兼容下列公开操作类：

- `CommitOperationAdd`
- `CommitOperationDelete`
- `CommitOperationCopy`

必要时后续可增加：

- `CommitOperationMove`

但内部实现可以退化为 `copy + delete`。

### 4.1 `CommitOperationAdd` 设计

默认应直接对齐 HF 的公开入口：

- `CommitOperationAdd(path_in_repo, path_or_fileobj)`

其中 `path_or_fileobj` 支持：

- 本地文件路径
- `bytes`
- 二进制 file object

约束：

- 本地文件路径只把外部文件当作导入源，不把其宿主路径写入仓库元数据
- file object 只消费字节内容，不把来源路径作为持久化元数据
- 这三种输入最终都必须产出一致的公开 `oid` / `sha256`
- 辅助方法仅保留真实有用的本地行为，因此不会为了外观兼容额外挂一个无效果的 `with_tqdm` 参数

代表性草图：

```python
@dataclass
class CommitOperationAdd:
    path_in_repo: str
    path_or_fileobj: Union[str, Path, bytes, BinaryIO]
```

### 4.2 `CommitOperationDelete` / `CommitOperationCopy`

默认也应尽量贴近 HF：

- `CommitOperationDelete(path_in_repo, is_folder="auto")`
- `CommitOperationCopy(src_path_in_repo, path_in_repo, src_revision=None)`

当前本地实现刻意不暴露 HF 内部优化字段，例如 `CommitOperationCopy` 上的 `_src_oid` / `_dest_oid`，因为它们在本地仓库中不承载任何真实公开语义，只会变成空兼容参数。

如果本地实现需要在行为上扩展，例如支持 subtree copy，也应保留 HF 风格签名，并把扩展点文档化，而不是重新发明另一套公开形态。

## 5. `HubVaultApi` 方法分层

### 5.1 MVP 必做方法

- `create_repo()`
- `repo_info()`
- `create_commit()`
- `get_paths_info()`
- `list_repo_tree()`
- `list_repo_files()`
- `open_file()`
- `read_bytes()`
- `list_repo_commits()`
- `hf_hub_download()`
- `reset_ref()`
- `quick_verify()`

当前状态：

- 上述方法都已经在 `HubVaultApi` 中落地并接入本地嵌入式仓库实现
- `list_repo_commits()` 当前使用 HF 同名方法名，并保留本地真正有语义的主要参数 `revision` 与 `formatted`
- `hf_hub_download()` 已保证默认返回路径和 `local_dir` 模式都保留 repo 相对路径后缀
- `open_file()` 返回只读二进制流；下载类接口返回的是与 repo 真相隔离、可重建的用户视图路径

MVP 的修改语义必须保持明确：

- 读取类 API：`open_file()`、`read_bytes()`、`hf_hub_download()`
- 读取类 API：`open_file()`、`read_bytes()`、`list_repo_commits()`、`hf_hub_download()`
- 写入类 API：`create_commit()` 以及后续的 `upload_*()` / `delete_*()`
- 不提供“改了下载路径上的文件就自动写回 repo”的工作区语义

### 5.2 紧随 MVP 的方法

- `create_branch()`
- `delete_branch()`
- `create_tag()`
- `delete_tag()`
- `list_repo_refs()`
- `upload_file()`
- `upload_folder()`
- `delete_file()`
- `delete_folder()`
- `snapshot_download()`

### 5.3 后续阶段方法

- `upload_large_folder()`
- `read_range()`
- `merge()`
- `revert_commit()`
- `full_verify()`
- `gc()`
- `compact()`
- `prune_history()`

## 6. 关键方法签名草图

```python
from typing import BinaryIO, Dict, Iterable, Optional, Sequence, Union


class HubVaultApi:
    def __init__(self, repo_path: Union[str, "os.PathLike[str]"], revision: str = "main") -> None:
        ...

    def create_repo(
        self,
        *,
        default_branch: str = "main",
        exist_ok: bool = False,
        metadata: Optional[Dict[str, str]] = None,
    ) -> RepoInfo:
        ...

    def repo_info(self, *, revision: Optional[str] = None) -> RepoInfo:
        ...

    def create_commit(
        self,
        *,
        revision: str = "main",
        operations: Sequence["CommitOperation"],
        parent_commit: Optional[str] = None,
        expected_head: Optional[str] = None,
        commit_message: str = "",
        metadata: Optional[Dict[str, str]] = None,
    ) -> CommitInfo:
        ...

    def list_repo_tree(self, path_in_repo: str = "", *, revision: str = "main") -> Sequence[PathInfo]:
        ...

    def get_paths_info(
        self,
        paths: Sequence[str],
        *,
        revision: str = "main",
    ) -> Sequence[PathInfo]:
        ...

    def open_file(self, path_in_repo: str, *, revision: str = "main") -> BinaryIO:
        ...

    def read_bytes(self, path_in_repo: str, *, revision: str = "main") -> bytes:
        ...

    def list_repo_commits(
        self,
        *,
        revision: Optional[str] = None,
        formatted: bool = False,
    ) -> Sequence[GitCommitInfo]:
        ...

    def hf_hub_download(
        self,
        filename: str,
        *,
        revision: Optional[str] = None,
        local_dir: Optional[Union[str, "os.PathLike[str]"]] = None,
    ) -> str:
        ...

    def reset_ref(self, ref_name: str, *, to_revision: str) -> CommitInfo:
        ...

    def quick_verify(self) -> VerifyReport:
        ...
```

`repo_path` 是运行时打开仓库的位置，不是仓库内部持久化协议的一部分。仓库被整体移动到新路径后，只需用新的 `repo_path` 重新打开即可。

下载路径语义建议严格对齐 `huggingface_hub` 的主流使用方式：

- `filename` 是 repo root 下的相对路径
- 返回值是可直接打开读取的文件路径
- 默认仓库内缓存布局与 `snapshot_download()` 都要保留 repo 相对路径层级
- 即使底层实际指向内容寻址 blob，最终返回给用户的路径也必须以 `filename` 结尾
- `local_dir` 模式下同样要在目标目录内复制 repo 相对路径结构
- 返回路径必须是“只读或可重建视图”，而不是正式对象文件本身
- 用户手动删除或改写返回路径后，后续下载应重建视图，而不是影响 repo 真相

`open_file()` / `read_bytes()` 语义也需要明确：

- `open_file()` 只返回只读二进制流
- 不支持通过返回的句柄执行写入、截断或回写
- 如果调用方需要修改内容，应先读出数据或导出到外部路径，再通过 `create_commit()` 等 API 提交新版本

公开文件哈希字段语义也需要明确：

- `blob_id` / `oid` 使用 HF 风格的 git OID 裸 hex
- `sha256` 使用与 HF `BlobLfsInfo.sha256` 一致的裸 64 位 hex
- 公开 `sha256` 不带 `sha256:` 算法前缀
- `sha256:<hex>` 只用于仓库内部对象 ID、payload 校验和等内部完整性字段

## 7. 关键参数语义

建议保留以下关键参数：

- `revision`
- `parent_commit`
- `expected_head`
- `allow_patterns`
- `ignore_patterns`
- `delete_patterns`

不要保留以下“兼容外观但当前没有真实语义”的参数：

- `repo_id`
- `expand`
- `with_tqdm`
- 其他不会改变本地仓库行为的 transport / progress / UI 占位参数

语义约束：

- `revision` 可以是 branch、tag 或 commit id
- `parent_commit` 与 `expected_head` 用于乐观并发控制
- `allow_patterns` / `ignore_patterns` / `delete_patterns` 优先服务 `upload_folder()` 与 `snapshot_download()`
- `oid` 指对外文件 OID，推荐与 HF `RepoFile.blob_id` 对齐
- `sha256` 指真实文件内容的 SHA-256，格式与 HF `BlobLfsInfo.sha256` 一样使用裸 hex
- 对 LFS 兼容文件，`etag` 推荐等于 `sha256`；对普通文件，`etag` 推荐等于 `oid`
- 对下载出的文件路径进行本地改写，不构成对 repo 的有效修改

## 8. 典型公开使用示例

### 8.1 初始化与提交

```python
from hubvault import HubVaultApi, CommitOperationAdd

api = HubVaultApi("/data/repos/demo")
api.create_repo()
commit = api.create_commit(
    revision="main",
    operations=[
        CommitOperationAdd(
            path_in_repo="weights/config.json",
            path_or_fileobj=b'{"dtype":"float16","hidden_size":4096}',
        ),
    ],
    commit_message="add config",
)
```

### 8.2 读取与导出

```python
payload = api.read_bytes("weights/config.json", revision="main")
download_path = api.hf_hub_download(
    filename="weights/config.json",
    revision=commit.commit_id,
)
```

期望语义：

- `download_path` 可以是缓存中的符号链接、reflink/COW clone 或普通文件
- 但它必须以 `weights/config.json` 结尾，而不是 `.../blobs/<opaque-id>`
- 如果 `download_path` 被用户删除或编辑，重新调用 `hf_hub_download()` 后应由 repo 服务重建它

### 8.3 回滚与校验

```python
api.reset_ref("main", to_revision=commit.commit_id)
report = api.quick_verify()
assert report.ok
```

## 9. 与 `huggingface_hub` 的兼容边界

建议明确如下策略：

- 尽量兼容 repo/file 主操作的命名和参数习惯
- 不兼容远端平台能力，例如 token、discussion、PR、space
- `snapshot_download()` 返回的是本地只读快照缓存，不是工作区
- `hf_hub_download()` 返回的是缓存文件或目标导出文件
- 不保留像 `repo_id` 这类仅为兼容外观而存在、但不会影响本地仓库行为的空参数
- 不保留像 `with_tqdm` 这类仅改变兼容外观、但不会触发本地真实进度/UI 行为的空 flags
- 仓库的全部正确性信息都保存在 repo root 内；导出文件、外部下载目标和调用时传入的源路径都不是仓库真相
- `path` / `blob_id` / `sha256` / `lfs.pointer_size` 等文件公开字段应尽量与 Hugging Face `RepoFile` 语义对齐，其中 `sha256` 使用裸 hex，不带算法前缀
- 真正有效的 repo 变更只能通过 commit 风格 API 显式提交，不能通过修改下载结果或快照目录隐式生效

## 10. 错误模型

建议定义以下公开异常：

- `RepoNotFoundError`
- `RepoAlreadyExistsError`
- `RevisionNotFoundError`
- `PathNotFoundError`
- `ConflictError`
- `IntegrityError`
- `VerificationError`
- `LockTimeoutError`
- `UnsupportedPathError`

这样调用方可以只依赖公开异常类型来做恢复与重试，不必窥探内部实现细节。
