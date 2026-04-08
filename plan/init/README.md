# init 计划说明

`plan/init/` 保存的是 `hubvault` 从当前“轻量 CLI + 元信息骨架”状态走向“可运行的本地嵌入式版本仓库”的初始化设计基线。

这一组文档不再只是抽象蓝图，而是同时承担两类职责：

- 固定第一版协议、对象模型和兼容边界
- 给出按阶段可执行的落地路径，优先把 MVP 尽快做出来
- 固定“repo root 本身就是完整仓库”的自包含与可搬迁约束
- 固定面向 `huggingface_hub` 风格下载路径与文件元数据的兼容语义

## 1. 当前仓库状态

截至当前仓库现状，已经存在的内容主要是：

- Python 包结构、打包脚本和测试基础设施
- `hubvault.config.meta` 中的公开包元信息
- `hubvault.entry` 下的 CLI 壳层与版本输出
- `pytest` / `make unittest` / `make package` 等基础工程能力
- 已落地的公开仓库 API 与包结构：`hubvault.api`、`hubvault.errors`、`hubvault.models`、`hubvault.operations`、`hubvault.repo/`
- 已落地的 Phase 3 大文件存储包：`hubvault.storage/`（`chunk.py`、`pack.py`、`index.py`）
- 已落地的本地仓库目录布局、whole-file blob 提交/读取、`hf_hub_download()` 路径保真与只读/可重建视图语义
- 已落地的 public-only 单元测试，按 `hubvault/` 模块树拆分到对应的 `test/**/test_<module>.py` 文件，并覆盖新仓库 API 的核心行为与回归要求
- 已落地的 Phase 2 refs / reflog / 便捷 upload-delete / `snapshot_download()` 能力，以及对应的 `test/test_phase2.py` 全周期集成回归
- 已落地的 Phase 3 chunked file / pack / index / `read_range()` / `upload_large_folder()` 能力，以及对应的 `test/test_phase3.py` 全周期集成回归
- 已落地的 Phase 3 阈值边界回归，明确验证只有满足 `large_file_threshold` 条件的文件才进入 chunked storage
- 已落地的 Phase 4 `full_verify()` / `get_storage_overview()` / `gc()` / `squash_history()` 能力，以及对应的 `test/test_phase4.py` 全周期维护回归

尚未落地的核心能力包括：

- merge 本体与冲突模型
- 基于真实 `git` / `git-lfs` / `huggingface_hub` 的行为对拍
- 面向极端场景的异常测试与故障注入验证
- 更进一步的性能基线与可选优化
- 文档、README、教程与最终交付收尾

因此，这组初始化方案既要记录已经实现的 MVP 基线，也要继续约束后续 Phase 5-9，避免把已经落地的格式和公开语义重新漂移回“抽象设想”，也避免把 correctness 验证、性能和文档收尾混成一个模糊的大阶段。

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
  仓库目录布局、内部组织结构、对象编码、路径规范化和分阶段存储格式。
- `03-transaction-consistency.md`
  锁协议、事务状态机、崩溃恢复和一致性红线。
- `04-api-compat.md`
  公开 Python API、数据模型、错误模型和与 `huggingface_hub` 的兼容边界，包含 Phase 2 refs / snapshot / upload-delete 对齐结论。
- `05-gc-roadmap.md`
  verify / GC / 历史压缩 / 空间治理路线图、保留策略和回收阶段拆分。
- `06-phase-execution.md`
  可执行 phase 计划，包含每个阶段的 Todo 与 Checklist。

## 4. MVP 策略

为尽快产出首个可用版本，本目录将 MVP 定义为：

- 单仓库、单写者、多读者
- 纯本地、纯 Python、无外部服务依赖
- 仓库根目录自包含全部持久化状态，关闭仓库后可以直接 `mv`、打包、解压并继续使用
- 只实现 whole-file blob 存储，不在 MVP 阶段引入 chunk pack
- 先打通 `create_repo -> create_commit -> list -> read -> reset -> quick_verify`
- 在 Phase 2 补齐 `list_repo_refs -> create/delete branch/tag -> upload/delete helpers -> snapshot_download -> list_repo_reflog`
- `hf_hub_download()` 与 `snapshot_download()` 返回的文件路径必须保留 repo 内相对路径后缀
- 文件元数据要同时维护 HF 兼容的 `oid` / `blob_id` 与 `sha256`，其中公开 `sha256` 使用和 HF 一样的裸 64 位 hex
- 所有单元测试走公开 API 或公开 CLI，不依赖 private / protected 实现细节，也不把规划文档本身当成单测对象

更重的能力放到后续 phase：

- merge
- `git` / `git-lfs` / `huggingface_hub` 对拍
- 异常测试与故障注入
- 原生加速与性能基线
- 文档、README 与教程收尾

## 5. 执行原则

- 设计先冻结协议，再推进实现，避免边写边改磁盘格式。
- 公开 API 优先于 CLI；CLI 在前期只保留最薄壳层。
- 所有持久化仓库状态必须位于 repo root 内，且不得依赖绝对路径或仓库外 sidecar 数据。
- 任何新增能力都必须配套公开表面的单元测试。
- 每次改动完成后都要跑与改动面匹配的回归；结束前必须通过要求的完整回归集。
- 当前 MVP 的最小验收基线是：`make unittest` 通过，且公开 API 文档生成 `make rst_auto` 可跑通。
