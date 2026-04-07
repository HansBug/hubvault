# 02. 磁盘格式与对象模型

## 1. 目录布局

### 1.1 Phase 1 MVP 布局

MVP 为了尽快交付，不直接引入 chunk / pack，而是先落地 whole-file blob：

```text
repo_root/
  FORMAT
  repo.json

  refs/
    heads/
      main
    tags/

  logs/
    refs/
      heads/
        main.log
      tags/

  objects/
    commits/
    trees/
    files/
    blobs/

  txn/
  locks/
  cache/
    files/
    snapshots/
  quarantine/
```

说明：

- `FORMAT`：仓库格式版本，例如 `hubvault-repo/v1`
- `repo.json`：仓库配置，例如默认分支、哈希算法、大小阈值
- `refs/`：分支与标签
- `logs/refs/`：append-only reflog
- `objects/`：不可变 commit/tree/file/blob 对象
- `txn/`：写事务暂存目录
- `locks/`：写锁与 GC 锁目录
- `cache/`：可丢弃缓存
- `quarantine/`：待删对象隔离区

### 1.2 自包含与可搬迁约束

repo root 必须是完整仓库的唯一持久化边界。

强制规则：

- 正式仓库状态只能存放在 repo root 内
- 持久化元数据中不得写入宿主绝对路径
- 不使用指向 repo root 之外的符号链接、sidecar 数据目录或外部数据库来承载仓库真相
- 所有对象定位都应由对象 ID、逻辑路径和 repo 内固定布局推导出来

结果要求：

- 关闭仓库后，直接 `mv repo_root new_path/` 不影响可读性和正确性
- 将 repo root 打包再解压到其他位置后，仓库仍可直接打开
- 运行时可导出到仓库外的临时文件不属于仓库真相，删除后不能影响仓库恢复

### 1.3 Phase 3 扩展布局

大文件能力在 Phase 3 再引入：

```text
repo_root/
  chunks/
    packs/
    index/
      MANIFEST
      L0/
      L1/
      L2/
```

这样可以保证 Phase 1 的格式已经可运行，同时为 Phase 3 预留稳定扩展点。

## 2. 仓库内部组织结构规范

仅给出目录名还不够，首版就应固定到“每类文件应该落在哪儿、叫什么、按什么分片”的粒度。

### 2.1 顶层固定文件

- `FORMAT`
  单行文本，记录仓库格式版本，例如 `hubvault-repo/v1`。
- `repo.json`
  仓库级配置文件，保存默认分支、格式版本、对象哈希算法、大小阈值与兼容开关。

建议 `repo.json` 最小结构如下：

```json
{
  "format_version": 1,
  "default_branch": "main",
  "object_hash": "sha256",
  "file_mode": "whole-blob-first",
  "large_file_threshold": 16777216
}
```

### 2.2 `refs/` 组织

`refs/` 只保存当前可见头指针，不混入历史与冗余字段：

```text
refs/
  heads/
    main
    release
  tags/
    v1.0.0
```

规则：

- branch 名直接映射为 `refs/heads/<branch_name>`
- tag 名直接映射为 `refs/tags/<tag_name>`
- ref 文件内容只保存目标 commit ID 和结尾换行
- ref 名校验必须拒绝空段、`.`、`..` 与平台不安全名称

示例：

```text
sha256:7cb3...d5f1
```

### 2.3 `logs/refs/` 组织

reflog 采用与 `refs/` 对称的目录结构：

```text
logs/
  refs/
    heads/
      main.log
    tags/
      v1.0.0.log
```

规则：

- 每条日志一行，推荐使用 JSON Lines
- 文件名与 ref 一一对应，避免额外索引
- 追加写，不做原地编辑

### 2.4 `objects/` 组织

对象必须按“对象类型 + 哈希算法 + 前缀分片”组织，避免单目录文件数失控。

推荐布局：

```text
objects/
  commits/
    sha256/
      ab/
        cdef...7890.json
  trees/
    sha256/
      12/
        3456...abcd.json
  files/
    sha256/
      98/
        76ab...cdef.json
  blobs/
    sha256/
      54/
        3210...fedc.meta.json
        3210...fedc.data
```

规则：

- 第一层按对象类型分目录
- 第二层按哈希算法分目录，为后续算法升级留接口
- 第三层使用摘要前 2 个 hex 字符做前缀分片
- commit/tree/file 建议保存为单个 `.json`
- blob 建议拆为 `.meta.json` 与 `.data` 两个文件

### 2.5 `txn/` 组织

事务目录必须能独立表达一个正在进行的提交。

推荐布局：

```text
txn/
  20260408T102233Z-3f9a2c1d/
    STATE.json
    meta.json
    objects/
    refs/
    logs/
```

规则：

- `txid` 推荐使用 `UTC 时间戳 + 随机后缀`
- `STATE.json` 保存状态机状态与最近步骤
- `meta.json` 保存事务级元数据，例如目标 revision、预期 head、创建时间
- `objects/` 内部布局与正式 `objects/` 保持同构，便于发布时原子迁移

### 2.6 `locks/` 组织

锁目录保持极简：

```text
locks/
  write.lock/
    owner.json
  gc.lock/
    owner.json
```

规则：

- 锁是否存在，以目录创建成功与否为准
- `owner.json` 只用于诊断与接管判断
- 不允许在锁目录中保存仓库正确性所依赖的状态

### 2.7 `cache/` 组织

`cache/` 要同时满足两个目标：

- 保持 repo 相对路径保真
- 允许内部共享底层内容对象

推荐布局：

```text
cache/
  materialized/
    sha256/
      ab/
        cdef...7890.data
  snapshots/
    <snapshot_key>/
      xxx/
        yyy/
          zzz.safetensors
  files/
    <snapshot_key>/
      xxx/
        yyy/
          zzz.safetensors
```

规则：

- `materialized/` 是按内容去重后的共享实体文件池
- `snapshots/<snapshot_key>/<repo_relative_path>` 提供完整只读目录树
- `files/<snapshot_key>/<repo_relative_path>` 可作为 `hf_hub_download()` 的单文件返回路径根
- `snapshots/` 与 `files/` 下的实际文件可以是 symlink、hardlink 或实体复制
- 但用户最终拿到的路径必须总是保留 `repo_relative_path`

### 2.8 `quarantine/` 组织

隔离区按来源类型分目录，便于恢复与人工检查：

```text
quarantine/
  objects/
  packs/
  manifests/
```

规则：

- 进入 `quarantine/` 的内容默认不参与读路径
- 删除前必须保留来源信息，例如原路径、隔离时间、原因

### 2.9 `chunks/` Phase 3 组织

大文件能力启用后，推荐固定如下布局：

```text
chunks/
  packs/
    20260408T102233Z-000001.pack
  index/
    MANIFEST
    L0/
      seg-20260408T102233Z-000001.idx
    L1/
    L2/
```

规则：

- pack 文件名按生成时间和序号排序
- 索引段文件名与生成批次绑定，避免覆写
- `MANIFEST` 是当前可见索引段集合的唯一真相

### 2.10 组织结构设计原则

内部组织结构应持续满足以下原则：

- 当前视图与历史对象分离
- 正式对象与事务中间态分离
- 用户可见路径与内部对象名分离
- 所有查找都可由 repo root 内固定规则推导
- 单个目录中的文件数量可通过前缀分片或时间分桶控制
## 3. 对象 ID 与哈希策略

### 2.1 MVP 选择

为了减少外部依赖并兼容 Python 3.7-3.14，格式 v1 的默认对象 ID 建议采用：

- 主哈希：`sha256`
- ID 形式：`sha256:<hex_digest>`

原因：

- `hashlib.sha256` 为标准库能力，零额外依赖
- 对象 ID 仍然是算法标记形式，后续可以平滑扩展
- 不会因早期引入 `blake3` 依赖而拖慢 MVP 交付

### 2.2 后续扩展

后续可以增加：

- `blake3` 作为更快的可选校验或新仓库默认算法
- `zstd` 压缩
- `fastcdc` 分块

但格式上始终保留“算法标签 + 十六进制摘要”的模式。

## 4. 核心对象定义

### 3.1 Commit 对象

推荐字段：

- `format_version`
- `tree_id`
- `parents`
- `author`
- `committer`
- `created_at`
- `message`
- `metadata`

### 3.2 Tree 对象

Tree 记录目录项列表，每个目录项包含：

- `name`
- `entry_type`，取值为 `tree` 或 `file`
- `object_id`
- `mode`
- `size_hint`

目录项按规范化名称排序，保证序列化可重现。

### 3.3 File 对象

`File` 是“逻辑文件元信息对象”，负责连接目录树和底层内容：

- `format_version`
- `storage_kind`，取值为 `blob` 或 `chunked`
- `logical_size`
- `sha256`
- `oid`
- `etag`
- `content_type_hint`
- `content_object_id`
- `chunks`

说明：

- Phase 1 只允许 `storage_kind="blob"`
- Phase 3 之后才允许 `storage_kind="chunked"`
- `content_object_id` 是内部内容对象引用，不是对外兼容层里的 `blob_id`
- `oid` / `etag` / `sha256` 是面向公开文件元数据的稳定字段

### 3.4 Blob 对象

MVP 新增 `Blob` 概念，表示一个 whole-file 内容对象：

- `format_version`
- `compression`
- `logical_size`
- `logical_hash`
- `stored_size`
- `payload_sha256`

对应的 payload 可以直接存储在对象文件中，或以 sidecar 二进制文件保存；MVP 优先选择“对象元信息 JSON + payload 文件”方案，编码简单、调试友好。

这里的 sidecar 仅指 repo root 内、与对象同属仓库布局的一部分，不是 repo 外的外置数据目录。

### 3.5 内部对象 ID 与公开文件身份分离

为了避免与 Hugging Face 兼容层的 `blob_id` 语义冲突，必须明确区分：

- 内部对象 ID：`objects/*` 下对象的仓库内部标识
- 公开文件 `oid`：对外暴露的 HF 兼容文件 OID
- 公开文件 `sha256`：文件逻辑内容的 SHA-256

对齐规则建议如下：

- 普通文件：`oid` 使用 git blob OID 语义，`sha256` 为文件内容 SHA-256
- 大文件 / LFS 兼容模式：`oid` 使用 canonical LFS pointer 的 git blob OID，`sha256` 为真实文件内容 SHA-256
- `etag` 采用 HF 风格：普通文件用 `oid`，LFS 兼容模式用 `sha256`

### 3.6 Chunk 记录

Phase 3 之后，chunk 元信息通过索引维护：

- `chunk_id`
- `pack_id`
- `offset`
- `stored_size`
- `logical_size`
- `compression`
- `checksum`

## 5. 对象编码格式

### 4.1 MVP 编码策略

首版优先选择“稳定 JSON 编码 + payload 校验”，避免过早设计过重的二进制容器。

建议对象文件采用如下结构：

```json
{
  "format_version": 1,
  "object_type": "commit",
  "payload_sha256": "sha256:...",
  "payload": {
    "...": "..."
  }
}
```

稳定编码要求：

- `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
- 先对 `payload` 做稳定编码并计算 `payload_sha256`
- 再根据完整稳定编码计算对象 ID
- 编码内容只能包含逻辑路径、对象 ID、版本信息和业务元数据，不得包含宿主绝对路径

### 4.2 代表性编码片段

```python
import json
from hashlib import sha1, sha256


def encode_payload(payload):
    payload_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return payload_bytes, "sha256:" + sha256(payload_bytes).hexdigest()


def git_blob_oid(data):
    header = "blob %d\0" % len(data)
    return sha1(header.encode("utf-8") + data).hexdigest()


def canonical_lfs_pointer(file_sha256, size):
    return (
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:%s\n"
        "size %d\n"
    ) % (file_sha256, size)
```

## 6. 文件内容存储策略

### 5.1 MVP

- 小文件和普通文件统一走 whole-file blob
- `Blob` 的 payload 存于 `objects/blobs/`
- `File` 对象引用 `content_object_id`
- `CommitOperationAdd.from_file()` 的源文件绝对路径只用于读取输入字节，绝不写入仓库持久化元数据
- 提交时同步计算文件 `sha256` 与 git blob 语义 `oid`

### 5.2 Phase 3

- 大于阈值的文件默认改走 `chunked`
- 引入 `chunks/packs/` 与 `chunks/index/`
- `read_range()` 才在该阶段成为高价值 API

### 5.3 大小阈值建议

- 小于 `16 MiB`：默认 whole-file blob
- 大于等于 `16 MiB`：Phase 3 之后默认 chunked

阈值设为 `16 MiB` 而不是更小，是为了让 MVP 阶段的大多数测试和典型模型配置文件直接走 blob，减少早期复杂度。

## 7. 索引设计

### 6.1 MVP

MVP 不做 chunk 索引；blob 查找只依赖对象 ID 到对象文件路径的确定性映射。

这意味着对象查找不需要任何 repo 外的数据库、注册表或路径映射。

下载路径与缓存布局也必须由 repo 相对路径推导，不能退化成仅暴露内部 blob 名的用户路径。

### 6.2 Phase 3 设计

chunk 索引采用文件版 LSM：

- 每次事务生成不可变索引段
- `MANIFEST` 记录可见段
- 读路径按 `MANIFEST` 查找
- compact 时做多段合并

## 8. 路径规范化与跨平台约束

仓库逻辑路径统一使用 POSIX 风格 `/`。

必须拒绝以下非法路径：

- 空路径
- 绝对路径
- 包含空段、`.` 或 `..` 的路径
- 包含 Windows 保留名的路径段
- 包含 NUL 或平台不安全字符的路径段

为兼容 Windows/macOS 默认大小写不敏感文件系统，需要增加 casefold 冲突检测：

- 同一目录下如果两个逻辑名称在 `casefold()` 后相同，则拒绝提交
- 所有持久化路径字段都必须是相对 repo root 的逻辑路径，不能是宿主绝对路径
- 所有导出/下载路径都必须能从 repo 相对路径稳定映射出来

### 7.1 代表性规范化片段

```python
from pathlib import PurePosixPath


def normalize_repo_path(path_in_repo):
    normalized = PurePosixPath(str(path_in_repo).replace("\\", "/"))
    parts = normalized.parts
    if not parts or normalized.is_absolute():
        raise ValueError("path_in_repo must be a non-empty relative path")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("path_in_repo contains illegal path segment")
    return "/".join(parts)
```

## 9. 缓存设计

缓存始终不是仓库真相，损坏后必须可重建。

建议包含两类缓存：

- `cache/files/<file_id>`：完整文件缓存
- `cache/snapshots/<commit_id>`：只读快照缓存

缓存规则：

- 缓存绝不参与 commit 的真实可达性判断
- quick verify 可忽略缓存
- GC 只把活跃快照缓存作为额外 root，而不是把缓存内容当正式对象
- 缓存必须位于 repo root 内部，确保仓库整体搬迁或归档恢复后不需要重建外部路径约定

针对下载路径的额外约束：

- repo 内部快照缓存应优先使用 `<snapshot_root>/<repo_relative_path>` 的布局
- `hf_hub_download()` 返回的文件路径可以是 symlink、hardlink 或实体文件
- 无论实现细节如何，返回路径都必须以原始 repo 相对路径结尾，例如 `xxx/yyy/zzz.safetensors`
