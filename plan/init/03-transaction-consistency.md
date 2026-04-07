# 03. 事务协议、一致性与恢复

## 1. 一致性目标

系统需要满足以下硬性语义：

- 已提交 commit 永不被原地修改
- ref 更新必须是原子的
- 任意读请求只能观察到完整版本
- 崩溃、断电、进程被杀后，仓库仍处于可恢复状态
- 最多丢失未完成事务，绝不破坏已提交版本
- GC 不得删除可达对象

## 2. 锁协议

为保持跨平台与实现简洁，首版建议使用“锁目录”而非平台专属文件锁。

### 2.1 写锁

写事务尝试创建：

```text
locks/write.lock/
```

创建成功则获得写锁，目录内记录：

- `owner.json`
- `pid`
- `hostname`
- `started_at`
- `heartbeat_at`

若锁已存在，则新写事务失败或等待超时。

### 2.2 GC 锁

GC 与 compact 使用独立锁：

```text
locks/gc.lock/
```

GC 启动前必须确认没有活跃写事务。

### 2.3 锁失效恢复

如果进程崩溃导致锁残留，可通过以下方式处理：

- 检查 `heartbeat_at`
- 检查 owner 进程是否仍存活
- 经过超时阈值后允许管理员或恢复流程接管

## 3. 提交状态机

建议将事务状态写入 `txn/<txid>/STATE`，状态如下：

- `PREPARING`
- `STAGED`
- `PUBLISHED_OBJECTS`
- `COMMITTED`
- `ABORTED`

## 4. 提交流程

单次 `create_commit` 或等价写操作的推荐流程如下：

1. 获取写锁
2. 读取目标 ref 当前 head
3. 校验 `expected_head` 或 `parent_commit`
4. 创建 `txn/<txid>/`
5. 将新增对象、pack、索引段写入 `txn/<txid>/`
6. 对所有新文件执行 `flush` 与必要的 `fsync`
7. 将事务状态写为 `STAGED`
8. 原子发布对象与 pack 到正式目录
9. 写入新 commit 对象
10. 再次刷盘关键对象
11. 用 `os.replace()` 原子更新 ref
12. 追加 ref log
13. 将事务状态写为 `COMMITTED`
14. 删除事务目录
15. 释放写锁

其中第 11 步是整个提交协议的线性化点。

## 5. 崩溃恢复语义

### 5.1 崩溃发生在 ref 更新之前

结果：

- 旧 ref 仍然有效
- 新对象即使部分已发布，也仍然不可见
- 后续恢复时可把这些对象视为孤儿对象，等待 GC 处理

### 5.2 崩溃发生在 ref 更新之后

结果：

- 新 commit 已生效
- 即使 ref log 未完整追加，也不影响仓库主状态
- 恢复流程应补全日志或标记日志不完整

### 5.3 恢复启动时的动作

仓库打开时建议执行轻量恢复检查：

- 扫描 `txn/` 下未完成事务
- 读取其 `STATE`
- 对 `COMMITTED` 但未清理的事务做善后
- 对未到 `COMMITTED` 的事务执行回收

## 6. ref 日志

每次 branch/tag 变更都应记录 append-only ref log。

建议字段：

- `timestamp`
- `ref_name`
- `old_head`
- `new_head`
- `txid`
- `actor`
- `message`
- `checksum`

用途：

- 审计
- rollback
- 恢复诊断
- 历史保留窗口管理

## 7. 校验与体检

### 7.1 quick verify

快速校验重点检查：

- refs 是否指向存在的 commit
- commit/tree/file 对象封装和 checksum 是否正常
- `MANIFEST` 与索引段摘要是否匹配
- pack 文件头尾摘要是否正常

### 7.2 full verify

完全校验需要：

- 遍历所有 GC roots 可达对象
- 重算 chunk hash
- 重新组合 file 逻辑 hash
- 验证 tree 和 commit DAG
- 输出损坏对象和损坏范围

## 8. rollback 语义

建议支持两类 rollback：

### 8.1 ref reset

直接将某个 ref 指回历史 commit。

特点：

- O(1)
- 不会立刻释放旧数据
- 适合快速恢复版本

### 8.2 revert commit

在当前 head 上生成一个“反向提交”。

特点：

- 历史线性可追踪
- 更适合共享分支

## 9. merge 语义

merge 首版建议采用“三方 tree merge + 显式冲突返回”。

规则建议：

- 只有一侧修改：自动通过
- 两侧都修改但结果对象 ID 一致：自动通过
- 两侧都修改且对象 ID 不同：冲突
- 二进制大文件默认不做内容级自动 merge

冲突通过结构化结果返回，不落地工作区。

## 10. 一致性红线

以下行为在设计上必须避免：

- 原地修改已提交对象
- 在 ref 指向新 commit 之前暴露半写对象
- 将缓存文件误认为正式数据
- 将回滚与物理删除绑在同一步
- 在未验证对象可达性前直接删除 pack
