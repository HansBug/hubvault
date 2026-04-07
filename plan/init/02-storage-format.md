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

## 2. 对象 ID 与哈希策略

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

## 3. 核心对象定义

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
- `logical_hash`
- `content_type_hint`
- `blob_id`
- `chunks`

说明：

- Phase 1 只允许 `storage_kind="blob"`
- Phase 3 之后才允许 `storage_kind="chunked"`

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

### 3.5 Chunk 记录

Phase 3 之后，chunk 元信息通过索引维护：

- `chunk_id`
- `pack_id`
- `offset`
- `stored_size`
- `logical_size`
- `compression`
- `checksum`

## 4. 对象编码格式

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
from hashlib import sha256


def encode_payload(payload):
    payload_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return payload_bytes, "sha256:" + sha256(payload_bytes).hexdigest()
```

## 5. 文件内容存储策略

### 5.1 MVP

- 小文件和普通文件统一走 whole-file blob
- `Blob` 的 payload 存于 `objects/blobs/`
- `File` 对象引用 `blob_id`
- `CommitOperationAdd.from_file()` 的源文件绝对路径只用于读取输入字节，绝不写入仓库持久化元数据

### 5.2 Phase 3

- 大于阈值的文件默认改走 `chunked`
- 引入 `chunks/packs/` 与 `chunks/index/`
- `read_range()` 才在该阶段成为高价值 API

### 5.3 大小阈值建议

- 小于 `16 MiB`：默认 whole-file blob
- 大于等于 `16 MiB`：Phase 3 之后默认 chunked

阈值设为 `16 MiB` 而不是更小，是为了让 MVP 阶段的大多数测试和典型模型配置文件直接走 blob，减少早期复杂度。

## 6. 索引设计

### 6.1 MVP

MVP 不做 chunk 索引；blob 查找只依赖对象 ID 到对象文件路径的确定性映射。

这意味着对象查找不需要任何 repo 外的数据库、注册表或路径映射。

### 6.2 Phase 3 设计

chunk 索引采用文件版 LSM：

- 每次事务生成不可变索引段
- `MANIFEST` 记录可见段
- 读路径按 `MANIFEST` 查找
- compact 时做多段合并

## 7. 路径规范化与跨平台约束

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

## 8. 缓存设计

缓存始终不是仓库真相，损坏后必须可重建。

建议包含两类缓存：

- `cache/files/<file_id>`：完整文件缓存
- `cache/snapshots/<commit_id>`：只读快照缓存

缓存规则：

- 缓存绝不参与 commit 的真实可达性判断
- quick verify 可忽略缓存
- GC 只把活跃快照缓存作为额外 root，而不是把缓存内容当正式对象
- 缓存必须位于 repo root 内部，确保仓库整体搬迁或归档恢复后不需要重建外部路径约定
