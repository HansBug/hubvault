# 03. 事务协议、一致性与恢复

## 1. 一致性目标

系统需要满足以下硬性语义：

- 已提交 commit/tree/file/blob 永不被原地修改
- ref 更新必须是原子的
- 任意读请求只能观察到完整版本
- 崩溃、断电、进程被杀后，仓库仍处于可恢复状态
- 最多只留下不可达对象、残留事务目录或其它后续可清理的中断痕迹，绝不破坏已提交且仍可达的版本
- 后续 GC 不得删除可达对象
- 任何读取句柄、下载路径或快照视图都不能成为已提交对象的可写别名

## 2. 锁协议

当前实现已经收敛到成熟第三方跨进程文件锁，而不是自造锁目录协议。

### 2.1 Repo 读写锁

当前基线：

```text
locks/repo.lock
```

实现约束：

- 使用基于 `portalocker` 的 shared/exclusive 文件锁
- `repo_info()`、`list_repo_tree()`、`read_bytes()`、`hf_hub_download()`、`snapshot_download()` 等读操作持有共享读锁
- `create_commit()`、`reset_ref()`、`create_branch()`、`delete_branch()`、`create_tag()`、`delete_tag()` 等写操作持有独占写锁
- 多个纯读请求允许并发
- writer 持锁期间，其余所有读写请求一律阻塞
- 锁文件本身不保存任何仓库正确性所依赖的业务状态

对齐说明：

- `huggingface_hub` 本地缓存层实际使用的是 `filelock`
- Phase 14 之后，`hubvault` 继续维持 repo-root 内单一 `repo.lock` 协议，但具体实现改为 shared/exclusive 文件锁，从而让同进程线程、同机多进程和共享路径访问都走同一套文件锁边界

### 2.2 GC / squash 维护锁

当前 `gc()` 与 `squash_history()` 都直接复用 `locks/repo.lock` 对应的独占写锁，而不是再引入第二套锁文件协议。

实现约束：

- 维护操作与普通写事务共享同一条串行化边界
- 在 `gc()` 或 `squash_history()` 持锁期间，其他读写请求全部阻塞
- 当前没有单独的 `gc.lock`、`compact.lock` 之类历史遗留锁文件
- 后续如果把维护逻辑拆分到独立模块，也必须继续复用同一套成熟第三方文件锁语义

### 2.3 锁失效恢复

锁恢复依赖操作系统文件锁语义，而不是 repo 内 owner 心跳文件。

仓库搬迁或归档恢复后的要求：

- 关闭状态下搬迁 repo root 不应留下不可恢复的路径依赖
- `locks/` 下只允许当前协议定义的 `repo.lock`；其余锁产物都视为异常垃圾，不保留任何历史兼容处理

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
- `UPDATED_REF -> COMMITTED`：本地完成标记已持久化，事务之后只允许做清理或补记日志，绝不再改变提交结果
- 任意未线性化状态都可以转 `ABORTED`

当前设计原则已经进一步收紧：

- **不做 roll-forward**
- 中断写事务不继续“补完提交”
- 只要事务没有进入 `COMMITTED`，恢复动作就必须把 ref 回滚到操作前安全状态
- 已发布但不可达的新对象允许遗留为孤儿对象，等待后续 GC，不影响主状态

## 4. 提交流程

单次 `create_commit()` 的推荐流程如下：

1. 获取写锁
2. 打开仓库并执行轻量恢复
3. 读取目标 ref 当前 head
4. 若调用方提供 `parent_commit`，校验其与当前 head 一致
5. 创建 `txn/<txid>/`
6. 将新增 blob/tree/file/commit 写入 `txn/<txid>/objects/`
7. 对所有新文件执行 `flush` 与必要的 `fsync`
8. 将状态写为 `STAGED`
9. 原子发布对象到正式目录
10. 将状态写为 `PUBLISHED_OBJECTS`
11. 写入 `REF_UPDATE.json`，记录旧 ref、新 ref 与回滚所需信息
12. 使用 `os.replace()` 原子更新 ref
13. 将状态写为 `UPDATED_REF`
14. 将状态写为 `COMMITTED`
15. 追加 reflog
16. 删除事务目录
17. 释放写锁

当前实现语义：

- 第 12 步之前中断：旧 ref 仍然有效；对可达 ref 状态而言等效于“什么都没发生”，但允许留下后续可清理的不可达对象
- 第 12 步到第 14 步之间中断：恢复流程必须按 `REF_UPDATE.json` 把 ref 回滚到旧值
- 第 14 步之后：事务已经被视为完成，后续至多只做清理，不再做结果回滚或继续推进其它业务步骤

## 5. 代表性提交代码片段

```python
def create_commit(self, revision, operations, parent_commit=None):
    with self._txn_manager.begin_write() as txn:
        current_head = self._refs.resolve(revision)
        if parent_commit is not None and parent_commit != current_head:
            raise ConflictError("expected head does not match current branch head")

        staged = self._commit_service.stage_commit(
            txn=txn,
            revision=revision,
            operations=operations,
            parent_commit=current_head,
        )
        txn.mark_staged()
        txn.publish_objects(staged.object_paths)
        txn.record_ref_rollback_info(revision, old_head=current_head, new_head=staged.commit_id)
        txn.update_ref_atomically(revision, staged.commit_id)
        txn.mark_committed()
        txn.append_reflog(revision, old_head=current_head, new_head=staged.commit_id)
        return staged.commit_info
```

这个骨架在 MVP 阶段已经足够稳定；后续只是在 `stage_commit()` 内把 blob 改成 chunk/pack。

## 6. 崩溃恢复语义

### 6.1 崩溃发生在 ref 更新之前

结果：

- 旧 ref 仍然有效
- 新对象即使部分已发布，也仍然不可见
- 恢复时可把它们视为孤儿对象，等待后续 GC
- 这里的要求是“可达主状态不变”，而不是“磁盘上绝对没有残留痕迹”

### 6.2 崩溃发生在 ref 更新之后

结果：

- 如果事务尚未进入 `COMMITTED`，恢复流程必须把 ref 回滚到旧值
- 不做“继续提交”“补写主状态”“继续推进剩余步骤”这类 roll-forward 行为
- 若对象已发布但回滚后不可达，只留下孤儿对象，不影响主状态
- reflog 只在已完成事务上视为补充审计信息，不参与主状态恢复判定

### 6.3 仓库打开时的恢复动作

仓库打开时建议执行轻量恢复，但只允许做安全回滚和清理：

- 扫描 `txn/` 下未完成事务
- 对已经进入 `COMMITTED` 但尚未清理的事务做善后删除
- 对带有 `REF_UPDATE.json` 且尚未 `COMMITTED` 的事务执行 ref 回滚
- 对其余状态的事务直接清理暂存目录
- 不允许把未完成事务继续推进成“已完成”

这一恢复过程不应依赖旧路径上下文；只要 repo root 本身完整存在，就应能在新位置完成恢复。

对于用户视图目录：

- 丢失、损坏或被用户改写的 `cache/files/`、`cache/snapshots/` 内容只做重建，不视为仓库损坏
- `objects/`、`refs/`、`logs/refs/` 的校验结论必须独立于这些视图目录

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

当前 Phase 2 已通过公开 API 暴露 `list_repo_reflog()`，并同时覆盖 branch 与 tag 的 append-only 日志查询。

## 8. 校验与体检

### 8.1 quick verify

MVP 的 `quick_verify()` 重点检查：

- refs 是否指向存在的 commit
- commit/tree/file/blob 对象封装和 checksum 是否正常
- `File -> Blob` 引用闭包是否完整
- 残留事务是否需要回滚或可安全清理
- 仓库内没有要求访问 repo root 外持久化状态的格式残留
- 文件 `oid` / `sha256` / `etag` 与持久化文件对象记录一致
- 用户视图目录如果存在，对应视图元数据与正式对象的一致性可被校验并可被修复
- `cache/views/snapshots/` 中记录的 detached snapshot 也会被体检并在污染后允许重建

### 8.2 full verify

Phase 4 已实现 `full_verify()`，当前校验范围包括：

- 遍历所有可见 branch/tag ref 可达对象
- 校验 commit/tree/file/blob 容器与 checksum
- 重算 chunk hash，并通过 pack/index/manifest 真实读取 chunk 载荷
- 验证 tree 与 commit DAG 引用闭包
- 扫描 file/snapshot 视图元数据，在用户污染缓存视图时给出 warning
- 输出损坏对象与范围，供后续 `gc()` 与空间治理使用

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

首版 merge 已经按“三方 tree merge + 结构化冲突返回”落地，并继续复用与普通提交相同的事务发布和 rollback-only 恢复红线。

当前后续执行顺序已经进一步拆细为：

- Phase 6：补基于公开 API 的 Git-like 本地 CLI
- Phase 7：与真实 `git` / `git-lfs` / `huggingface_hub` 做行为对拍
- Phase 8：补 merge 与通用写路径的异常/故障注入验证

这样做的原因是先把用户真正会直接触达的 CLI 公开面做出来，再用外部真实基线和极端场景把语义压实，而不是把“实现、交付、验证、异常安全”混成同一个模糊阶段。

## 10. 一致性红线

以下行为必须避免：

- 原地修改已提交对象
- 在 ref 指向新 commit 之前暴露半写状态
- 把缓存文件误认为正式仓库数据
- 让下载路径或快照视图与正式对象文件形成可写 hardlink 别名
- 把回滚和物理删除绑在同一步
- 在未验证对象可达性前直接删除对象或 pack
