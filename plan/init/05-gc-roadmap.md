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

为了尽快产出 MVP，GC 不应成为第一阶段的阻塞项。当前这部分已经按分阶段路线落地：

- Phase 1：落地“残留事务清理 + `quick_verify()`”，先保证不会破坏数据
- Phase 3：引入 chunk/pack，使大文件空间治理有真实对象基础
- Phase 4：落地 `full_verify()`、`get_storage_overview()`、`gc()` 与 `squash_history()`

这意味着 MVP 先做到“不会破坏数据”，再逐步做到“能解释空间去哪了”和“能安全回收空间”。

## 3. GC Root 定义

GC 只能从明确的 root 集合出发做可达性分析。当前实现已经冻结为：

- 所有可见 branch head
- 所有可见 tag

当前不作为 GC root 的内容：

- reflog 记录
- 用户下载/快照缓存视图
- 未完成事务目录中的暂存文件
- 仓库外部任何状态

原因：

- 维护 pass 在进入 `gc()` / `squash_history()` 前会先做恢复或回滚，未完成事务不应继续 pin 住主仓库空间
- `cache/` 里的用户视图是可重建的 detached 视图，不代表仓库真相
- 当前没有额外的 pin/retention 元数据协议，因此不能凭空假设这些 root 存在

这组 root 全部只依赖 repo root 内部可见 refs 推导，不查询仓库外状态源。

## 4. 回收流程

当前实现采用 `verify -> mark -> rewrite-live-pack -> quarantine -> delete` 的组合流程。

### 4.1 mark

1. 获取 repo 独占写锁
2. 读取全部 roots
3. 遍历 `commit -> tree -> file -> blob/chunk`
4. 计算 live set

### 4.2 rewrite-live-pack

当仓库存在 chunked storage 时，`gc()` 会先根据当前 live chunk 集合重写出新的紧凑 pack/index 视图，再原子发布它。

这样做的原因：

- 避免边删旧 pack 边依赖旧 pack 读取 live chunk
- 保证“要么新 live pack 完整发布，要么什么都没发生”
- 为后续删除旧 pack/index 留出明确隔离边界

### 4.3 quarantine

将不可达对象先移入 `quarantine/` 或登记到隔离清单，而不是立刻删除。

好处：

- 降低误删风险
- 允许管理员做人工检查
- 崩溃恢复更简单

### 4.4 delete

当前实现不会保留历史遗留的 quarantine 队列，而是在同一次维护 pass 内把新隔离出的旧对象和旧 pack/index 清掉；对 `txn/` 则保持人工检查策略，不自动删除。

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

当前实现同时复用这套遍历逻辑来做 `get_storage_overview()` 的 live/tip/historical 空间分析。

## 6. 历史保留策略

当前实现的历史保留策略是显式的，而不是后台自动的：

- 所有可见 branch/tag 默认都继续保留其可达历史
- 需要释放旧历史时，由用户显式调用 `squash_history(...)`
- `squash_history(...)` 只重写一个 branch，并把其他仍阻塞旧历史回收的 refs 以 `blocking_refs` 明确报告出来

因此，当前版本在“可回滚”和“控制空间”之间采用的是“默认保守保留，显式重写后再回收”的策略。

## 7. compact 的必要性

仅删除不可达对象并不足够，因为 chunk 实际位于 pack 中，旧 pack 往往只部分可回收。

当前实现里，compact 逻辑已经内嵌在 `gc()` 里，负责：

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

Phase 4 当前已补齐：

- 遍历所有可见 ref 可达对象
- 重算 chunk/hash
- 校验 pack、索引段和 manifest
- 校验公开 detached 视图是否陈旧，并以 warning 形式返回

## 9. 测试路线图

如果要把一致性和跨平台作为核心卖点，测试不能只做 happy-path 单元测试。当前已落地回归重点如下。

### 9.1 单元测试

- 公开 API 的参数行为
- 路径规范化
- 对象编码与解码
- refs 解析
- verify 报告结构
- 文件 `oid` / `sha256` 计算与 HF 兼容语义

### 9.2 集成测试

- `create_repo -> create_commit -> list -> read -> reset`
- branch/tag/reflog
- snapshot/cache 行为
- full verify / storage overview / gc / squash_history 联动
- 仓库关闭后整体移动目录、重新打开与继续读取/校验
- 仓库归档后解压恢复并重新打开
- `hf_hub_download()` / `snapshot_download()` 返回路径保留 repo 相对路径层级
- 用户删除或改写下载视图后，repo 真相不变且视图可以重建

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

## 10. 当前明确取舍

当前维护能力已经落地，但仍保留以下明确取舍：

- 仍未实现 rename 检测
- 仍未实现文本内容级自动 merge
- 仍以单写者模型保证正确性
- `squash_history()` 只重写单个 branch，不自动改写其他 refs
- `txn/` 残留在空间画像中标记为 `manual-review`，不由 `gc()` 自动清理
