# 05. GC、空间回收、测试与路线图

## 1. 为什么 GC 必须单独设计

本项目要求：

- 随时回滚
- 必要时释放历史空间

因此必须把“逻辑版本切换”和“物理空间释放”彻底分离：

- rollback 负责变更 ref
- gc/compact 负责回收不可达对象与 pack 空洞

如果把这两步混在一起，会直接威胁一致性。

## 2. GC Root 定义

GC 只能从明确的 root 集合出发做可达性分析。

建议 root 包括：

- 所有 branch head
- 所有 tag
- 用户显式 pin 的 commit
- 活跃事务引用
- 活跃快照缓存引用
- reflog 保留窗口内涉及的 commit

## 3. GC 流程

推荐采用 mark-sweep + pack compaction 的组合：

1. 获取 GC 锁
2. 读取全部 roots
3. 遍历 `commit -> tree -> file -> chunk`
4. 计算 live set
5. 将不可达对象加入 quarantine 列表
6. 等待 grace period
7. 重写仍有存活 chunk 的 pack
8. 发布新的索引和 MANIFEST
9. 删除旧 pack 与垃圾对象

## 4. 历史保留策略

建议支持多种保留策略组合：

- 保留所有 tag 指向的历史
- 每个 branch 保留最近 `N` 个 commit
- 保留最近 `X` 天内被 reflog 引用的 commit
- 用户可显式 pin 关键版本

这样可以在“可回滚”和“控制空间”之间取得平衡。

## 5. compact 的必要性

仅删除不可达对象并不足够，因为 chunk 实际位于 pack 中，旧 pack 往往只部分可回收。

compact 负责：

- 重写含少量 live chunk 的旧 pack
- 合并小 pack，减少句柄与碎片
- 合并索引段，降低查询开销

compact 必须遵循与普通提交相同的发布原则：

- 先写新 pack 和新索引
- 校验完整性
- 原子切换 manifest
- 最后删除旧 pack

## 6. 测试策略

如果要把一致性和跨平台作为核心卖点，测试不能只做单元测试。

建议测试分层如下：

### 6.1 单元测试

- 对象编码与解码
- 路径规范化
- merge 判定
- ref 解析
- 索引查找

### 6.2 集成测试

- create/upload/delete/list/download
- branch/tag/reset/merge
- snapshot/cache 行为
- gc/compact/verify 联动

### 6.3 故障注入测试

- 写 pack 中途崩溃
- 写 commit 中途崩溃
- 更新 ref 前崩溃
- 更新 ref 后日志未写完崩溃
- 事务目录残留

### 6.4 跨平台测试

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

## 7. 实施路线图

### Phase 0：规范冻结

目标：

- 冻结对象模型
- 冻结目录布局
- 冻结事务协议
- 冻结错误语义

产出：

- 设计文档
- 格式版本约定

### Phase 1：纯 Python 最小可用版本

目标：

- 基础 repo 初始化
- refs/commit/tree/file 存储
- whole-file 存储
- `create_commit` / `list` / `download` / `reset`
- quick verify

### Phase 2：大文件能力

目标：

- chunked file
- pack 存储
- 文件版 LSM 索引
- range read
- 基础 GC

### Phase 3：工程增强

目标：

- merge
- full verify
- compact
- reflog 与保留策略
- 更完整的 API 兼容层

### Phase 4：性能与发布

目标：

- 原生加速模块
- wheel 打包
- benchmark
- 文档与示例

## 8. 首版建议取舍

为了尽快进入可验证状态，首版建议：

- 先不实现 rename 检测
- 先不实现文本内容级自动 merge
- 先用稳定 JSON 对象编码
- 先以单写者模型保证正确性
- 先让功能正确，再逐步引入原生加速
