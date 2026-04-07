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
    PathInfo,
    VerifyReport,
)
```

`hubvault.__init__` 应只做薄 re-export，不承载业务逻辑。

## 3. 公开数据模型

建议优先定义以下公开 dataclass：

- `RepoInfo`
- `RefInfo`
- `CommitInfo`
- `PathInfo`
- `BlobLfsInfo`
- `VerifyReport`
- `MergeResult`

### 3.1 模型草图

```python
from dataclasses import dataclass
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

建议支持三种公开构造方式：

- `from_bytes(path_in_repo, data)`
- `from_file(path_in_repo, path)`
- `from_fileobj(path_in_repo, fileobj)`

约束：

- `from_file()` 只把外部文件当作导入源，不把其宿主路径写入仓库
- `from_fileobj()` 只消费字节流，不把 file object 的来源路径作为持久化元数据
- 这三种入口最终都必须产出一致的公开 `oid` / `sha256`

代表性草图：

```python
@dataclass(frozen=True)
class CommitOperationAdd:
    path_in_repo: str
    data: bytes
    content_type: Optional[str] = None

    @classmethod
    def from_bytes(cls, path_in_repo: str, data: bytes) -> "CommitOperationAdd":
        return cls(path_in_repo=path_in_repo, data=data)
```

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
- `hf_hub_download()`
- `reset_ref()`
- `quick_verify()`

### 5.2 紧随 MVP 的方法

- `create_branch()`
- `delete_branch()`
- `create_tag()`
- `delete_tag()`
- `list_repo_refs()`
- `list_repo_commits()`
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
        expand: bool = False,
    ) -> Sequence[PathInfo]:
        ...

    def open_file(self, path_in_repo: str, *, revision: str = "main") -> BinaryIO:
        ...

    def read_bytes(self, path_in_repo: str, *, revision: str = "main") -> bytes:
        ...

    def hf_hub_download(
        self,
        repo_id: str,
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

## 7. 关键参数语义

建议保留以下关键参数：

- `revision`
- `parent_commit`
- `expected_head`
- `allow_patterns`
- `ignore_patterns`
- `delete_patterns`

语义约束：

- `revision` 可以是 branch、tag 或 commit id
- `parent_commit` 与 `expected_head` 用于乐观并发控制
- `allow_patterns` / `ignore_patterns` / `delete_patterns` 优先服务 `upload_folder()` 与 `snapshot_download()`
- `oid` 指对外文件 OID，推荐与 HF `RepoFile.blob_id` 对齐
- `sha256` 指真实文件内容的 SHA-256
- 对 LFS 兼容文件，`etag` 推荐等于 `sha256`；对普通文件，`etag` 推荐等于 `oid`

## 8. 典型公开使用示例

### 8.1 初始化与提交

```python
from hubvault import HubVaultApi, CommitOperationAdd

api = HubVaultApi("/data/repos/demo")
api.create_repo()
commit = api.create_commit(
    revision="main",
    operations=[
        CommitOperationAdd.from_bytes(
            path_in_repo="weights/config.json",
            data=b'{"dtype":"float16","hidden_size":4096}',
        ),
    ],
    commit_message="add config",
)
```

### 8.2 读取与导出

```python
payload = api.read_bytes("weights/config.json", revision="main")
download_path = api.hf_hub_download(
    repo_id="demo",
    filename="weights/config.json",
    revision=commit.commit_id,
)
```

期望语义：

- `download_path` 可以是缓存中的符号链接、硬链接或普通文件
- 但它必须以 `weights/config.json` 结尾，而不是 `.../blobs/<opaque-id>`

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
- `repo_id` 在本项目中只是逻辑名称；真正的存储根仍是本地路径
- 仓库的全部正确性信息都保存在 repo root 内；导出文件、外部下载目标和调用时传入的源路径都不是仓库真相
- `path` / `blob_id` / `sha256` / `lfs.pointer_size` 等文件公开字段应尽量与 Hugging Face `RepoFile` 语义对齐

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
