# 06. 分阶段执行计划

## 总体策略

执行顺序遵循一个原则：先交付最小可用、可验证、可回归的本地仓库核心，再逐步扩充大文件、维护和性能能力。

优先级排序如下：

1. 公开 API、对象模型、事务协议
2. whole-file blob MVP
3. refs / 历史 / 快照增强
4. chunk / pack / range read
5. merge / full verify / GC / compact
6. 性能优化与发布

## Phase 0. 规范冻结与脚手架

### Goal

冻结格式、API 名称、异常模型和测试制度，确保后续实现不会频繁推翻协议。

### Todo

* [ ] 冻结 `plan/init` 中的对象模型、目录布局、事务状态机和 API 命名。
* [ ] 明确 `HubVaultApi`、`CommitOperation*`、`RepoInfo`、`CommitInfo`、`PathInfo`、`VerifyReport` 的公开字段。
* [ ] 固化 `AGENTS.md` 中的测试制度、公开表面约束和回归要求。
* [ ] 为 `plan/init` 与 `AGENTS.md` 增加结构性单元测试，防止后续回退到非执行式计划。

### Checklist

* [ ] `plan/init` 文档与当前仓库骨架状态一致，没有假设已存在的实现。
* [ ] 所有 Phase 都包含可执行范围、Todo 和 Checklist。
* [ ] 新增测试只依赖公开文件和公开表面，不使用 private / protected 细节。
* [ ] `make unittest` 通过。

## Phase 1. MVP 仓库核心

### Goal

做出第一个真正可用的本地版本仓库 MVP，先只支持 whole-file blob。

### Todo

* [ ] 新增 `hubvault/errors.py`，定义公开异常类型。
* [ ] 新增 `hubvault/models.py` 与 `hubvault/operations.py`，定义公开 dataclass 和 `CommitOperation*`。
* [ ] 新增 `hubvault/api.py` 与 `hubvault/repo.py`，提供 `HubVaultApi` 公开入口。
* [ ] 实现 repo 初始化、打开、`repo_info()` 与默认分支解析。
* [ ] 实现 whole-file blob 存储、commit/tree/file/blob 对象写入和读取。
* [ ] 实现 `create_commit()`、`list_repo_tree()`、`list_repo_files()`、`open_file()`、`read_bytes()`、`hf_hub_download()`。
* [ ] 实现 `reset_ref()` 与最小 `quick_verify()`。
* [ ] 为上述能力补齐只经由公开 API 的单元测试和必要的临时目录集成测试。

### Checklist

* [ ] 可以在空目录中初始化仓库并生成 `FORMAT`、`repo.json`、`refs/`、`objects/`、`txn/`、`locks/`。
* [ ] 可以提交新增文件并通过公开 API 读回内容。
* [ ] 可以列出目录树和文件清单。
* [ ] 可以将分支回退到历史 commit。
* [ ] `quick_verify()` 能在正常仓库上返回成功报告。
* [ ] `make unittest` 通过。

## Phase 2. 可用性增强

### Goal

在不引入 chunk/pack 的前提下，把仓库从“能用”推进到“日常可用”。

### Todo

* [ ] 实现 `create_branch()`、`delete_branch()`、`create_tag()`、`delete_tag()`、`list_repo_refs()`。
* [ ] 实现 `list_repo_commits()` 与公开 reflog 查询模型。
* [ ] 实现 `upload_file()`、`upload_folder()`、`delete_file()`、`delete_folder()`。
* [ ] 实现 `snapshot_download()`，返回只读快照缓存目录。
* [ ] 增强 `quick_verify()` 输出，增加 refs、对象和事务残留诊断。
* [ ] 增加公开 API 的用例测试，覆盖 refs、文件删除、快照缓存和回滚。

### Checklist

* [ ] branch/tag 生命周期通过公开 API 可完整操作。
* [ ] 目录上传与删除行为不依赖内部 helper。
* [ ] `snapshot_download()` 产出的目录内容与目标 revision 一致。
* [ ] reflog 至少能支持审计与恢复诊断。
* [ ] `make unittest` 通过。

## Phase 3. 大文件引擎

### Goal

补齐 chunked file、pack 和 range read，使仓库真正适合中大型模型产物。

### Todo

* [ ] 新增 `chunk_store.py`、`pack_store.py`、`index_store.py`。
* [ ] 引入 `storage_kind="chunked"` 和 chunk 元信息模型。
* [ ] 实现 append-only pack 写入与 `MANIFEST` 管理。
* [ ] 实现 `read_range()` 与 `upload_large_folder()`。
* [ ] 增加 chunk/hash、pack 截断、索引查找和范围读取测试。

### Checklist

* [ ] 大文件可以通过 chunk/pack 存储并稳定读回。
* [ ] `read_range()` 在大文件上可工作且不需要重组全量文件。
* [ ] pack/manifest 更新遵守事务发布原则。
* [ ] 旧的 whole-file blob 仓库仍可兼容读取。
* [ ] `make unittest` 通过。

## Phase 4. 一致性与维护能力

### Goal

补齐 merge、full verify、GC、compact 和保留策略，让仓库具备长期运行能力。

### Todo

* [ ] 实现 `merge()` 和结构化冲突结果。
* [ ] 实现 `full_verify()`，覆盖 chunk、pack、manifest 和逻辑 hash。
* [ ] 实现 mark-sweep `gc()` 与 `quarantine/`。
* [ ] 实现 `compact()` 和 pack/索引段合并。
* [ ] 实现 reflog 保留窗口、pin 与历史保留策略。
* [ ] 增加故障注入测试，覆盖崩溃恢复和回收安全边界。

### Checklist

* [ ] merge 冲突通过公开结果对象返回，而不是暴露内部工作区。
* [ ] `full_verify()` 能定位损坏对象和范围。
* [ ] GC 不会删除任何可达对象。
* [ ] compact 只在新 pack 和新索引发布后才删除旧数据。
* [ ] `make unittest` 通过。

## Phase 5. 性能、文档与发布

### Goal

在协议正确性稳定后，再做原生加速、构建发布和用户文档完善。

### Todo

* [ ] 评估可选原生加速模块，例如 `blake3`、`zstd`、`fastcdc`。
* [ ] 增加 benchmark 和跨平台性能基线。
* [ ] 完善公开 API 文档、MVP 教程和恢复/诊断文档。
* [ ] 视需要扩展 CLI，但保持其为公开 API 的薄封装。
* [ ] 跑通 `make package`、必要时跑 `make build` 与 `make test_cli`。

### Checklist

* [ ] 性能优化不改变格式与公开语义。
* [ ] 文档示例全部走公开 API。
* [ ] 打包产物和基础安装路径可验证。
* [ ] 对 Python 3.7-3.14 与主要平台的兼容性假设有回归证据。
* [ ] `make unittest` 以及相关发布回归通过。
