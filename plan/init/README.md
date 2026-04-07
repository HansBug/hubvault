# init 计划说明

`plan/init/` 保存的是 `hubvault` 从当前“轻量 CLI + 元信息骨架”状态走向“可运行的本地嵌入式版本仓库”的初始化设计基线。

这一组文档不再只是抽象蓝图，而是同时承担两类职责：

- 固定第一版协议、对象模型和兼容边界
- 给出按阶段可执行的落地路径，优先把 MVP 尽快做出来

## 1. 当前仓库状态

截至当前仓库现状，已经存在的内容主要是：

- Python 包结构、打包脚本和测试基础设施
- `hubvault.config.meta` 中的公开包元信息
- `hubvault.entry` 下的 CLI 壳层与版本输出
- `pytest` / `make unittest` / `make package` 等基础工程能力

尚未落地的核心能力包括：

- 面向仓库的公开 Python API
- commit/tree/blob/chunk 等对象模型
- 本地磁盘格式与事务协议实现
- verify、gc、compact、merge 等一致性与维护能力

因此，初始化方案必须显式围绕“当前仓库几乎没有存储内核实现”这一现实来规划，而不是假设系统已经具备 Git 或 Hub 级别能力。

## 2. 使用方式

建议按如下顺序阅读和执行：

1. 先看 `00-scope.md`，确认目标、MVP 边界与不做项。
2. 再看 `01-architecture.md` 与 `02-storage-format.md`，确定包结构、对象关系和磁盘协议。
3. 接着看 `03-transaction-consistency.md` 与 `05-gc-roadmap.md`，锁定一致性、恢复、校验和回收红线。
4. 最后以 `04-api-compat.md` 与 `06-phase-execution.md` 作为开发入口，直接按 phase 推进实现。

## 3. 文档清单

- `00-scope.md`
  目标、约束、当前仓库基线、MVP 切分与成功标准。
- `01-architecture.md`
  面向当前仓库的推荐模块结构、分层职责和核心对象关系。
- `02-storage-format.md`
  仓库目录布局、对象编码、路径规范化和分阶段存储格式。
- `03-transaction-consistency.md`
  锁协议、事务状态机、崩溃恢复和一致性红线。
- `04-api-compat.md`
  公开 Python API、数据模型、错误模型和与 `huggingface_hub` 的兼容边界。
- `05-gc-roadmap.md`
  verify / GC / compact 路线图、保留策略和回收阶段拆分。
- `06-phase-execution.md`
  可执行 phase 计划，包含每个阶段的 Todo 与 Checklist。

## 4. MVP 策略

为尽快产出首个可用版本，本目录将 MVP 定义为：

- 单仓库、单写者、多读者
- 纯本地、纯 Python、无外部服务依赖
- 只实现 whole-file blob 存储，不在 MVP 阶段引入 chunk pack
- 先打通 `create_repo -> create_commit -> list -> read -> reset -> quick_verify`
- 所有测试走公开 API、公开 CLI 或受版本控制的规划文档，不依赖 private / protected 实现细节

更重的能力放到后续 phase：

- chunked file、pack、LSM 索引
- merge
- full verify
- GC / compact
- 原生加速模块

## 5. 执行原则

- 设计先冻结协议，再推进实现，避免边写边改磁盘格式。
- 公开 API 优先于 CLI；CLI 在前期只保留最薄壳层。
- 任何新增能力都必须配套公开表面的单元测试。
- 每次改动完成后都要跑与改动面匹配的回归；结束前必须通过要求的完整回归集。
