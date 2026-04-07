# 02. 磁盘格式与对象模型

## 1. 仓库目录布局

建议一个 repo 的根目录如下：

```text
repo_root/
  FORMAT
  config.json

  refs/
    heads/
      main
    tags/
      v1.0.0

  logs/
    refs/
      heads/
        main.log
      tags/
        v1.0.0.log

  objects/
    commits/
    trees/
    files/

  chunks/
    packs/
    index/
      MANIFEST
      L0/
      L1/
      L2/

  txn/
  locks/
  cache/
    files/
    snapshots/
```

说明：

- `FORMAT`：仓库格式版本
- `config.json`：仓库参数，例如 chunk 策略、压缩策略、大小阈值
- `refs/`：当前分支和标签
- `logs/refs/`：ref 的 append-only 变更日志
- `objects/`：小型不可变元数据对象
- `chunks/packs/`：大对象数据
- `chunks/index/`：chunk 索引段与 manifest
- `txn/`：进行中的事务暂存区
- `locks/`：锁目录
- `cache/`：可丢弃缓存

## 2. 对象 ID 与哈希

建议统一采用内容寻址：

- 主哈希：`blake3`
- 可选兼容校验：`sha256`

对象 ID 形如：

```text
blake3:<hex_digest>
```

优点：

- 去重天然成立
- 历史共享天然成立
- rollback 不需要复制文件

## 3. 核心对象

### 3.1 Commit 对象

字段建议：

- `version`
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

目录项按规范化名称排序，保证可重现序列化。

### 3.3 File 对象

字段建议：

- `version`
- `storage_mode`
- `logical_size`
- `logical_hash`
- `content_type_hint`
- `chunker`
- `compression`
- `chunks`

其中 `storage_mode` 有三种：

- `inline`
- `whole_blob`
- `chunked`

### 3.4 Chunk 记录

chunk 真正数据放在 pack 文件中，chunk 元信息可在索引中维护：

- `chunk_id`
- `pack_id`
- `offset`
- `stored_size`
- `logical_size`
- `compression`
- `checksum`

## 4. 对象编码格式

建议所有对象都采用统一外层容器，保证自描述和自校验：

```text
magic
format_version
object_type
header_len
payload_len
header_checksum
payload_checksum
payload
footer_checksum
```

建议：

- 头部采用固定长度字段
- payload 采用稳定编码，可选 JSON 或 msgpack
- 对象落盘前先完整编码，再计算对象 ID

首版为可读性和实现速度，可优先选择“稳定 JSON 编码 + 二进制外层校验封装”。

## 5. 大文件存储策略

### 5.1 大小阈值

建议：

- 小于 `8 MiB`：优先 whole-file
- 大于等于 `8 MiB`：默认 chunked

### 5.2 chunk 策略

建议支持：

- `fixed-size`
- `fastcdc`

默认优先 `fastcdc`，没有加速模块时可回退 `fixed-size`。

### 5.3 pack 文件

pack 文件采用 append-only 模式，每个事务只写新 pack 或新 pack segment，不修改已发布 pack。

pack 内部条目建议记录：

- `chunk_id`
- `compression`
- `logical_size`
- `stored_size`
- `payload_checksum`
- `payload`

pack 文件头和尾部都要带摘要，防止截断和误写。

## 6. 索引设计

不依赖外部 DB，因此 chunk 索引建议采用基于文件的 LSM 结构。

### 6.1 索引段

每次事务生成一个新的不可变索引段文件，段文件中包含：

- fanout table
- bloom filter
- 排序后的 `chunk_id -> location`
- segment checksum

### 6.2 MANIFEST

索引层维护一个 `MANIFEST`，描述当前可见的所有段：

- level
- segment id
- min key
- max key
- file size
- checksum

读路径按 `MANIFEST` 查找，写路径只追加新段，GC 或 compact 时再做多段合并。

## 7. 路径规范化与跨平台约束

仓库逻辑路径统一使用 POSIX 风格 `/`。

必须拒绝以下非法路径：

- 空路径
- 绝对路径
- 包含 `.` 或 `..` 的路径段
- 包含平台保留名的路径

为兼容 Windows/macOS 默认大小写不敏感文件系统，建议增加“规范化名称冲突检测”：

- 同一目录下如果两个逻辑名称在 casefold 后相同，则拒绝提交

例如：

- `Model.bin`
- `model.bin`

这两者不能同时写入同一目录。

## 8. 缓存设计

缓存不是仓库真相，始终可重建。

建议包含两类缓存：

- `cache/files/<file_id>`：重组后的完整文件缓存
- `cache/snapshots/<commit_id>`：按 commit 物化的只读快照缓存

缓存损坏时，不应影响正式仓库数据。
