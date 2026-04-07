# 04. Python API 与兼容层设计

## 1. 设计目标

API 目标不是逐行复制 `huggingface_hub`，而是：

- 保留 repo/file 操作的主要使用手感
- 保留以 `HfApi` 风格为中心的调用方式
- 去掉依赖远端 HTTP 平台的非本地能力
- 增加适合嵌入式本地仓库的 verify、gc、compact、reset 等能力

## 2. 建议包结构

```text
hubvault/
  __init__.py
  api.py
  errors.py
  models.py
  repo.py
  storage/
  txn/
  merge/
  gc/
  verify/
  _native/
```

建议对外主入口：

```python
from hubvault import HubVaultApi
```

## 3. 核心类

### 3.1 `HubVaultApi`

主要职责：

- 打开仓库
- 对外暴露所有 repo/file 级操作
- 管理默认 revision
- 封装异常类型与参数行为

### 3.2 `CommitOperation*`

建议兼容下列操作模型：

- `CommitOperationAdd`
- `CommitOperationDelete`
- `CommitOperationCopy`

必要时可增加：

- `CommitOperationMove`

但内部可退化为 `copy + delete`。

## 4. 首版建议支持的方法

### 4.1 repo 与 refs

- `create_repo()`
- `delete_repo()`
- `repo_info()`
- `create_branch()`
- `delete_branch()`
- `create_tag()`
- `delete_tag()`
- `list_repo_refs()`
- `list_repo_commits()`
- `reset_ref()`
- `revert_commit()`
- `merge()`

### 4.2 写操作

- `create_commit()`
- `upload_file()`
- `upload_folder()`
- `upload_large_folder()`
- `delete_file()`
- `delete_folder()`

### 4.3 读操作

- `file_exists()`
- `get_paths_info()`
- `list_repo_tree()`
- `list_repo_files()`
- `open_file()`
- `read_bytes()`
- `read_range()`
- `hf_hub_download()`
- `snapshot_download()`

### 4.4 维护操作

- `verify_repo()`
- `quick_verify()`
- `full_verify()`
- `gc()`
- `compact()`
- `prune_history()`

## 5. 关键参数语义

建议保留以下关键参数语义：

- `revision`
- `parent_commit`
- `expected_head`
- `allow_patterns`
- `ignore_patterns`
- `delete_patterns`

其中：

- `parent_commit` 或 `expected_head` 用于乐观并发控制
- `revision` 允许 branch、tag、commit id

## 6. 典型使用示例

### 6.1 初始化与分支

```python
from hubvault import HubVaultApi

api = HubVaultApi("/data/repos/demo")
api.create_repo()
api.create_branch("exp", revision="main")
```

### 6.2 提交文件

```python
from hubvault import CommitOperationAdd, CommitOperationDelete

api.create_commit(
    revision="main",
    parent_commit=api.repo_info().head,
    operations=[
        CommitOperationAdd(
            path_in_repo="weights/model.safetensors",
            path_or_fileobj="/tmp/model.safetensors",
        ),
        CommitOperationDelete(
            path_in_repo="legacy/old.bin",
        ),
    ],
    commit_message="update weights",
)
```

### 6.3 读取文件

```python
with api.open_file("weights/model.safetensors", revision="main") as f:
    head = f.read(1024)
```

### 6.4 回滚与校验

```python
api.reset_ref("main", to_revision="blake3:abcd...")
api.quick_verify()
api.gc(prune_unreachable=True)
```

## 7. 与 `huggingface_hub` 的兼容边界

建议明确以下兼容策略：

- 尽量兼容 repo/file 主操作的命名和参数习惯
- 不兼容远端平台侧功能，例如 token、space、discussion、pull request
- `snapshot_download()` 返回的是派生快照缓存，不是工作区
- `hf_hub_download()` 返回的是缓存文件或目标目录中的导出文件

## 8. 错误模型

建议定义明确异常类型：

- `RepoNotFoundError`
- `RevisionNotFoundError`
- `ConflictError`
- `IntegrityError`
- `VerificationError`
- `LockTimeoutError`
- `UnsupportedPathError`

这样调用方可以精确处理一致性、并发和数据损坏问题。
