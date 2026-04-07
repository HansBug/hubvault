# hubvault

这是一个面向本地超大文件场景的嵌入式版本化仓库方案仓库。`hubvault` 的目标是设计一个纯 API 驱动、无 workspace、无外部数据库依赖、强调数据一致性和跨平台支持的本地 repo 系统，并提供与 `huggingface_hub` 相似的 Python 使用手感。

当前仓库主要用于沉淀设计方案，核心约束如下：

- 只通过 Python API 访问和操作仓库
- 不依赖 SQLite、Redis、守护进程或外部服务
- 重点支持超大数据集、模型权重等大文件场景
- 保证已提交版本不可变，支持随时回滚
- 支持 branch、merge、tag、history、GC、verify
- 支持 Linux、macOS、Windows

文档目录：

- `plan/README.md`：计划文档总览与目录约定
- `plan/init/README.md`：初始化阶段方案文档说明
- `plan/init/00-scope.md`：目标、边界、约束与术语
- `plan/init/01-architecture.md`：总体架构与模块划分
- `plan/init/02-storage-format.md`：磁盘布局、对象模型与索引设计
- `plan/init/03-transaction-consistency.md`：事务协议、一致性、恢复与校验
- `plan/init/04-api-compat.md`：Python API 设计与 `huggingface_hub` 兼容面
- `plan/init/05-gc-roadmap.md`：GC、空间回收、测试与分阶段路线图

建议阅读顺序：

1. `plan/init/00-scope.md`
2. `plan/init/01-architecture.md`
3. `plan/init/03-transaction-consistency.md`
4. `plan/init/02-storage-format.md`
5. `plan/init/04-api-compat.md`
6. `plan/init/05-gc-roadmap.md`
