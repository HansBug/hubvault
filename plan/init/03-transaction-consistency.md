# 03. 事务协议、一致性与恢复

## 1. 一致性目标

系统需要满足以下硬性语义：

- 已提交 commit/tree/file/blob 永不被原地修改
- ref 更新必须是原子的
- 任意读请求只能观察到完整版本
- 崩溃、断电、进程被杀后，仓库仍处于可恢复状态
- 最多丢失未完成事务，绝不破坏已提交版本
- 后续 GC 不得删除可达对象

## 2. 锁协议

为保持跨平台与实现简洁，首版建议使用“锁目录”而不是平台专属文件锁。

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

这些字段仅用于诊断与恢复，不得成为仓库可用性的前提；其中也不应记录必须参与正确性的绝对路径。

如果锁已存在，则：

- 默认立即失败并抛出 `LockTimeoutError`
- 或按显式超时参数等待

### 2.2 GC 锁

GC 和 compact 使用独立锁：

```text
locks/gc.lock/
```

GC 启动前必须确认没有活跃写事务。

### 2.3 锁失效恢复

如果进程崩溃导致锁残留，可按以下顺序处理：

1. 读取 `owner.json`
2. 判断 `heartbeat_at` 是否过期
3. 如平台支持，再判断进程是否仍存活
4. 只有满足“锁已超时且持有者不存在或不可达”时，才允许接管

仓库搬迁或归档恢复后的要求：

- 关闭状态下搬迁 repo root 不应留下不可恢复的路径依赖
- 如果归档中包含陈旧锁目录，打开仓库时应把它视为可恢复诊断状态，而不是永久阻塞条件

## 3. 事务状态机

建议将事务状态写入 `txn/<txid>/STATE.json`。

状态集合：

- `PREPARING`
- `STAGED`
- `PUBLISHED_OBJECTS`
- `UPDATED_REF`
- `COMMITTED`
- `ABORTED`

状态转移规则：

- `PREPARING -> STAGED`：所有对象都已写入事务目录并刷盘
- `STAGED -> PUBLISHED_OBJECTS`：对象已发布到正式目录
- `PUBLISHED_OBJECTS -> UPDATED_REF`：目标 ref 已用 `os.replace()` 更新
- `UPDATED_REF -> COMMITTED`：reflog 已追加，事务可安全清理
- 任意未线性化状态都可以转 `ABORTED`

## 4. 提交流程

单次 `create_commit()` 的推荐流程如下：

1. 获取写锁
2. 打开仓库并执行轻量恢复
3. 读取目标 ref 当前 head
4. 校验 `expected_head` 或 `parent_commit`
5. 创建 `txn/<txid>/`
6. 将新增 blob/tree/file/commit 写入 `txn/<txid>/objects/`
7. 对所有新文件执行 `flush` 与必要的 `fsync`
8. 将状态写为 `STAGED`
9. 原子发布对象到正式目录
10. 将状态写为 `PUBLISHED_OBJECTS`
11. 使用 `os.replace()` 原子更新 ref
12. 将状态写为 `UPDATED_REF`
13. 追加 reflog
14. 将状态写为 `COMMITTED`
15. 删除事务目录
16. 释放写锁

线性化点是第 11 步的 `os.replace()`。

## 5. 代表性提交代码片段

```python
def create_commit(self, revision, operations, parent_commit=None):
    with self._txn_manager.begin_write() as txn:
        current_head = self._refs.resolve(revision)
        self._refs.check_expected_head(
            revision=revision,
            current_head=current_head,
            expected_head=parent_commit,
        )

        staged = self._commit_service.stage_commit(
            txn=txn,
            revision=revision,
            operations=operations,
            parent_commit=current_head,
        )
        txn.mark_staged()
        txn.publish_objects(staged.object_paths)
        txn.update_ref_atomically(revision, staged.commit_id)
        txn.append_reflog(revision, old_head=current_head, new_head=staged.commit_id)
        txn.mark_committed()
        return staged.commit_info
```

这个骨架在 MVP 阶段已经足够稳定；后续只是在 `stage_commit()` 内把 blob 改成 chunk/pack。

## 6. 崩溃恢复语义

### 6.1 崩溃发生在 ref 更新之前

结果：

- 旧 ref 仍然有效
- 新对象即使部分已发布，也仍然不可见
- 恢复时可把它们视为孤儿对象，等待后续 GC

### 6.2 崩溃发生在 ref 更新之后

结果：

- 新 commit 已生效
- 即使 reflog 尚未完整追加，也不影响主状态
- 恢复流程应补写日志或记录诊断信息

### 6.3 仓库打开时的恢复动作

仓库打开时建议执行轻量恢复：

- 扫描 `txn/` 下未完成事务
- 读取其 `STATE.json`
- 对 `COMMITTED` 但未清理的事务做善后
- 对 `UPDATED_REF` 的事务补写 reflog
- 对其余状态的事务执行回收

这一恢复过程不应依赖旧路径上下文；只要 repo root 本身完整存在，就应能在新位置完成恢复。

## 7. ref 日志

每次 branch/tag 变更都应记录 append-only reflog。

建议字段：

- `timestamp`
- `ref_name`
- `old_head`
- `new_head`
- `txid`
- `actor`
- `message`
- `checksum`

reflog 用途：

- 审计
- rollback 诊断
- 恢复补偿
- GC 保留窗口

## 8. 校验与体检

### 8.1 quick verify

MVP 的 `quick_verify()` 重点检查：

- refs 是否指向存在的 commit
- commit/tree/file/blob 对象封装和 checksum 是否正常
- `File -> Blob` 引用闭包是否完整
- 残留事务是否可恢复或可安全清理
- 仓库内没有要求访问 repo root 外持久化状态的格式残留

### 8.2 full verify

完整校验在后续阶段增加：

- 遍历所有 GC roots 可达对象
- 重算 chunk hash
- 重新组合 file 逻辑 hash
- 验证 tree 和 commit DAG
- 输出损坏对象与范围

## 9. rollback 与 merge 语义

### 9.1 `reset_ref()`

直接将某个 ref 指回历史 commit。

特点：

- O(1)
- 不释放旧数据
- 是 MVP 内的核心恢复手段

### 9.2 `revert_commit()`

在当前 head 上生成一个反向提交，建议放到后续 phase。

### 9.3 `merge()`

首版 merge 建议采用“三方 tree merge + 结构化冲突返回”，但落地时间放到 Phase 4。

## 10. 一致性红线

以下行为必须避免：

- 原地修改已提交对象
- 在 ref 指向新 commit 之前暴露半写状态
- 把缓存文件误认为正式仓库数据
- 把回滚和物理删除绑在同一步
- 在未验证对象可达性前直接删除对象或 pack
