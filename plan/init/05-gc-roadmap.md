# 05. GC、空间回收、校验与测试路线图

## 1. 为什么 GC 必须单独设计

本项目同时要求：

- 随时回滚
- 必要时释放历史空间

因此必须把“逻辑版本切换”和“物理空间释放”彻底分离：

- `reset_ref()` / `revert_commit()` 负责修改逻辑版本
- `gc()` / `compact()` 负责释放不可达对象与 pack 空洞

如果把这两步混在一起，会直接威胁一致性。

## 2. MVP 与 GC 的关系

为了尽快产出 MVP，GC 不应成为第一阶段的阻塞项。

推荐分三步推进：

- Phase 1：只做“残留事务清理 + quick verify”，不做真正删除
- Phase 3：实现 blob/object 级 mark-sweep
- Phase 4：实现 pack compaction 与保留策略

这意味着 MVP 可以先做到“不会破坏数据”，然后再做到“安全回收空间”。

## 3. GC Root 定义

GC 只能从明确的 root 集合出发做可达性分析。

建议 root 包括：

- 所有 branch head
- 所有 tag
- 用户显式 pin 的 commit
- 活跃事务引用
- 活跃快照缓存引用
- reflog 保留窗口内涉及的 commit

这些 root 都必须能仅依赖 repo root 内的数据推导出来，不能要求查询仓库外状态源。

## 4. 回收流程

推荐采用 `mark -> quarantine -> sweep -> compact` 的组合流程。

### 4.1 mark

1. 获取 GC 锁
2. 读取全部 roots
3. 遍历 `commit -> tree -> file -> blob/chunk`
4. 计算 live set

### 4.2 quarantine

将不可达对象先移入 `quarantine/` 或登记到隔离清单，而不是立刻删除。

好处：

- 降低误删风险
- 允许管理员做人工检查
- 崩溃恢复更简单

### 4.3 sweep

经过 grace period 后，再删除确定不可达的对象。

### 4.4 compact

当引入 pack 后，再重写 live chunk 稀疏分布的 pack，并原子切换索引。

## 5. 代表性 GC 代码片段

```python
def collect_live_objects(repo):
    roots = repo.list_gc_roots()
    pending = list(roots)
    live = set()

    while pending:
        object_id = pending.pop()
        if object_id in live:
            continue
        live.add(object_id)
        pending.extend(repo.iter_object_references(object_id))

    return live
```

MVP 阶段即使暂时没有真正 `gc()`，也可以先复用这套遍历逻辑来做 `quick_verify()` 的可达性检查。

## 6. 历史保留策略

建议支持多种保留策略组合：

- 保留所有 tag 指向的历史
- 每个 branch 保留最近 `N` 个 commit
- 保留最近 `X` 天内被 reflog 引用的 commit
- 用户显式 pin 关键版本

这样可以在“可回滚”和“控制空间”之间取得平衡。

## 7. compact 的必要性

仅删除不可达对象并不足够，因为 chunk 实际位于 pack 中，旧 pack 往往只部分可回收。

compact 负责：

- 重写含少量 live chunk 的旧 pack
- 合并小 pack，减少句柄与碎片
- 合并索引段，降低查询开销

compact 必须遵循与普通提交相同的发布原则：

- 先写新 pack 和新索引
- 校验完整性
- 原子切换 `MANIFEST`
- 最后删除旧 pack

## 8. 校验路线图

### 8.1 Phase 1 的 `quick_verify()`

只检查最关键闭包：

- refs 是否存在并指向合法 commit
- commit/tree/file/blob 是否可解码
- `File -> Blob` 引用是否完整
- 事务目录是否处于可恢复状态

### 8.2 Phase 4 的 `full_verify()`

完整校验再补齐：

- 遍历所有 root 可达对象
- 重算 chunk/hash
- 重新组合 logical hash
- 校验 pack、索引段和 manifest

## 9. 测试路线图

如果要把一致性和跨平台作为核心卖点，测试不能只做 happy-path 单元测试。

### 9.1 单元测试

- 公开 API 的参数行为
- 路径规范化
- 对象编码与解码
- refs 解析
- verify 报告结构

### 9.2 集成测试

- `create_repo -> create_commit -> list -> read -> reset`
- branch/tag/reflog
- snapshot/cache 行为
- verify / gc / compact 联动
- 仓库关闭后整体移动目录、重新打开与继续读取/校验
- 仓库归档后解压恢复并重新打开

### 9.3 故障注入测试

- 写 blob 中途崩溃
- 写 commit 中途崩溃
- 更新 ref 前崩溃
- 更新 ref 后 reflog 未写完崩溃
- 事务目录残留

### 9.4 跨平台测试

至少覆盖：

- Linux
- macOS
- Windows

重点验证：

- 路径分隔符处理
- 大小写冲突拒绝
- `os.replace()` 行为
- 锁目录恢复
- 长路径与保留名

## 10. 首版建议取舍

为了尽快进入可验证状态，首版建议：

- 先不实现 rename 检测
- 先不实现文本内容级自动 merge
- 先用稳定 JSON 对象编码
- 先以单写者模型保证正确性
- 先把 blob 存储和 quick verify 做稳，再逐步引入 chunk/pack/GC
