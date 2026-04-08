# 01. 总体架构

## 1. 面向当前仓库的总体思路

当前仓库已经具备本地嵌入式仓库的 Phase 0-4 基线，因此后续架构演进必须满足两个条件：

- 不推翻已经落地的磁盘格式、公开 API 和测试制度
- 后续补 merge、做真实对拍、补异常安全、进一步拆分后端模块和文档交付收尾时，不引入协议漂移

推荐采用如下组合：

- Git 风格的不可变元数据 DAG
- Phase 1 使用 whole-file blob 存储
- Phase 3 再引入 chunk / pack / range read
- 基于成熟第三方跨进程文件锁与事务暂存目录的原子提交协议
- repo-root-contained 的持久化布局，不依赖外置数据库或路径映射
- API-first 的本地仓库访问层，CLI 仅作薄包装

这意味着 `hubvault` 的本质是“嵌入式事务化对象仓库”，不是 git workspace 包装器。

## 2. 包结构

### 2.1 当前已落地结构

截至当前仓库状态，公开包结构已经演进到如下布局：

```text
hubvault/
  __init__.py
  api.py
  errors.py
  models.py
  operations.py
  repo/
    __init__.py
    backend.py
    constants.py

  storage/
    __init__.py
    chunk.py
    pack.py
    index.py

  config/
    __init__.py
    meta.py

  entry/
    __init__.py
    base.py
    cli.py
    dispatch.py
```

含义：

- `api.py`
  公开 `HubVaultApi`，保持对外入口稳定且尽量贴近 HF 风格调用手感。
- `errors.py`
  公开异常模型，避免调用方依赖内部实现细节。
- `models.py`
  公开 `RepoInfo`、`CommitInfo`、`GitCommitInfo`、`GitRefInfo`、`GitRefs`、`ReflogEntry`、`RepoFile`、`RepoFolder`、`BlobLfsInfo`、`VerifyReport`、`StorageSectionInfo`、`StorageOverview`、`GcReport`、`SquashReport`。
- `operations.py`
  公开 `CommitOperationAdd/Delete/Copy`。
- `repo/`
  当前本地仓库后端包，`backend.py` 负责主协调逻辑，包括提交、refs、读取、大文件、校验、空间画像、GC 与历史压缩，`constants.py` 固化仓库级常量，`__init__.py` 保持 `hubvault.repo` 导入入口稳定。
- `storage/`
  当前 Phase 3 大文件存储包，`chunk.py` 负责分块规划与 canonical LFS pointer 元数据，`pack.py` 负责 append-only pack 读写，`index.py` 负责 manifest 与不可变索引段。

### 2.2 后续推荐拆分结构

在当前 MVP 稳定后，建议在当前仓库基础上逐步扩展为：

```text
hubvault/
  __init__.py
  api.py
  errors.py
  models.py
  operations.py
  repo/
    __init__.py
    backend.py
    constants.py
  layout.py

  entry/
    __init__.py
    base.py
    cli.py
    dispatch.py

  services/
    repository.py
    commit.py
    refs.py
    verify.py
    gc.py

  storage/
    object_store.py
    blob_store.py
    chunk.py
    pack.py
    index.py

  txn/
    manager.py
    recovery.py
```

分阶段实现建议：

- Phase 0-2 已经落地 `api.py`、`errors.py`、`models.py`、`operations.py` 与 `repo/`
- Phase 3 已经落地 `storage/chunk.py`、`storage/pack.py`、`storage/index.py`
- 后续再按需要继续拆分 `repo/backend.py`、`services/repository.py`、`services/commit.py`、`storage/object_store.py`、`storage/blob_store.py`

## 3. 分层职责

### 3.1 API 层

公开给用户的 Python API，风格尽量接近 `huggingface_hub.HfApi`。

职责：

- 参数校验
- 路径规范化
- revision 解析
- 向下调用 repo/service 层
- 返回公开 dataclass，而不是泄露内部实现对象
- 对外暴露 HF 兼容的文件路径与文件身份元数据，而不是内部 blob 命名
- 保证所有读取接口都只返回只读句柄或与 repo 真相解耦的用户视图

### 3.2 仓库服务层

负责协调事务、refs、对象读取和历史查询。

职责：

- 打开或初始化仓库
- 执行 commit / reset / branch / tag
- 维护 ref 与 reflog
- 构造 `RepoInfo`、`CommitInfo`、`GitCommitInfo`、`GitRefInfo`、`GitRefs`、`ReflogEntry`、`RepoFile`、`RepoFolder`
- 确保持久化记录只写逻辑路径、对象 ID 与相对布局，不写宿主绝对路径
- 为下载类 API 生成保留 repo 相对路径后缀的可读文件路径
- 为 `snapshot_download()` 维护目录级用户视图与最小元数据
- 维护公开文件 `oid` / `sha256` 与内部对象引用之间的映射
- 在用户视图被删除、替换或污染时，能够从仓库真相重建该视图

### 3.3 存储层

负责不可变对象和文件内容的落盘、查找与校验。

职责：

- 固定 repo root 下各子目录的组织结构与命名规则
- commit/tree/file/blob 对象编码与存储
- whole-file blob 读写
- Phase 3 之后的 chunk / pack / index 能力
- 区分正式不可变内容池与用户可见视图目录，避免可写别名

### 3.4 事务层

负责锁协议、事务状态机、恢复和发布顺序。

职责：

- 通过成熟第三方文件锁获取/释放跨进程 RW 锁
- 管理 `txn/<txid>/` 生命周期
- 原子发布对象与更新 ref
- 将中断写事务回滚到操作前状态，而不是继续补完

### 3.5 维护层

负责仓库体检和空间回收。

职责：

- `quick_verify()` 与 `full_verify()`
- `get_storage_overview()` 空间画像与安全释放建议
- `gc()` 的 mark-sweep + live-pack compact + cache prune
- `squash_history()` 的单分支历史压缩与阻塞 ref 诊断
- 诊断报告输出

## 4. 核心对象关系

逻辑关系固定如下：

- `Ref -> Commit`
- `Commit -> Tree`
- `Tree -> Tree | File`
- `File -> Blob | Chunk[]`

设计含义：

- branch / tag 只是 ref 名称到 commit 的映射
- rollback 默认只改 ref，不直接删除物理对象
- merge 的核心是根据三个 tree 计算一个新 tree，再生成新 commit

## 5. MVP 简化架构

为了让 MVP 更快可交付，Phase 1 采用显式瘦身：

- `File` 只支持 `storage_kind="blob"`
- 不实现 pack 和索引段
- `quick_verify()` 只校验 refs、对象和 blob 引用闭包
- `snapshot_download()` 已在 Phase 2 先构建 detached 快照缓存目录，不处理 chunk 级共享
- `upload_large_folder()` 在 Phase 3 前可退化为多次 whole-file 提交
- 所有缓存、事务和诊断状态都放在 repo root 下，保证仓库整体搬迁后仍然自洽
- 默认下载路径可以使用 symlink、reflink/COW clone 或实体文件，但不能使用会形成可写别名的 hardlink；用户拿到的最终路径必须保留 repo 相对路径后缀
- 先把 refs / objects / txn / cache 的内部组织结构冻结到文件级命名规则，再开始实现读写逻辑
- 真正的修改入口只保留 `create_commit()` 等显式写 API，不提供基于视图路径的隐式回写

这样可以先把一致性、对象关系、公开 API 和公开测试体系做稳。

## 6. 代表性 API / 模型草图

```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Union


@dataclass(frozen=True)
class RepoInfo:
    repo_path: str
    default_branch: str
    head: Optional[str]
    format_version: int


@dataclass
class CommitInfo(str):
    commit_url: str
    commit_message: str
    commit_description: str
    oid: str


@dataclass(frozen=True)
class GitCommitInfo:
    commit_id: str
    authors: List[str]
    created_at: datetime
    title: str
    message: str


@dataclass(frozen=True)
class RepoFile:
    path: str
    size: int
    blob_id: str
    oid: Optional[str]
    sha256: Optional[str]


@dataclass(frozen=True)
class RepoFolder:
    path: str
    tree_id: str


class HubVaultApi:
    def __init__(self, repo_path: str, revision: str = "main") -> None:
        ...

    def create_repo(self, *, default_branch: str = "main") -> RepoInfo:
        ...

    def create_commit(
        self,
        operations: Sequence["CommitOperation"] = (),
        *,
        commit_message: str,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        ...

    def get_paths_info(
        self,
        paths: Union[Sequence[str], str],
        *,
        revision: Optional[str] = None,
    ) -> Sequence[Union[RepoFile, RepoFolder]]:
        ...
```

## 7. 模块依赖约束

- `api.py` 可以依赖 `errors.py`、`models.py`、`operations.py`、`repo.py`
- `services/` 可以依赖 `storage/` 与 `txn/`
- `storage/` 不能依赖 `click` 或 CLI 模块
- `entry/` 只能依赖公开 API，不应直接操作内部存储实现
- `models.py` 只定义公开 dataclass / enum，不放业务逻辑
- 任何持久化实现都不得要求仓库外的 sidecar 目录、外部索引库或绝对路径配置才能工作
- 内部对象 ID、公开文件 `oid`、以及下载导出路径三者必须显式分层，避免语义混淆

## 8. 写路径与读路径

### 8.1 写路径

1. `HubVaultApi.create_commit()` 校验参数并规范化路径
2. 仓库服务层解析 revision，并在提供 `parent_commit` 时执行乐观并发校验
3. 事务层获取写锁并创建 `txn/<txid>/`
4. 存储层生成 blob/tree/commit 对象并先写入事务目录
5. 事务层发布对象并原子更新 ref
6. 返回 `CommitInfo`

### 8.2 读路径

1. 解析 revision 到 commit
2. 递归解析 tree
3. 定位目标 file/blob
4. 读取 blob 或未来的 chunk range

读路径只读取“已发布对象”，永远不读事务暂存目录。

补充语义：

- `open_file()` 返回的句柄必须以只读模式打开
- `read_bytes()` / `read_range()` 直接返回内存数据，不暴露可写别名
- `hf_hub_download()` / `snapshot_download()` 返回的是“用户读取视图”，不是仓库真相路径
- 用户删除或改写这些视图后，repo 服务应能根据正式对象与视图元数据重新生成它们

## 9. 仓库内部组织职责分工

为了避免后续实现时出现“目录有了但命名规则还在飘”的问题，建议把 repo root 下的组织职责固定如下：

- `refs/`
  只保存当前可见的 branch/tag 头指针，文件内容保持最小化。
- `logs/refs/`
  保存 append-only reflog，负责审计、恢复和保留策略输入。
- `objects/`
  保存 commit/tree/file/blob 的正式不可变对象，是仓库真相主体之一。
- `txn/`
  保存未提交或待清理事务的 staging 内容，是唯一允许出现半成品文件的区域。
- `cache/`
  保存公开 API 使用的派生只读路径，例如 snapshot 目录树和下载路径映射。
- `quarantine/`
  保存待删除对象或 pack 的隔离副本，不参与正常读路径。
- `chunks/`
  仅在 Phase 3 之后启用，用于 pack 与索引组织。

这个分工意味着：

- “当前可见版本”只看 `refs/`
- “历史不可变内容”只看 `objects/`
- “事务中间态”只看 `txn/`
- “用户可读导出路径”优先看 `cache/`
