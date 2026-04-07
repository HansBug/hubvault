# 00. 目标、边界与约束

## 1. 当前仓库基线

当前仓库还没有真正的 repo/storage 内核，现状更接近“工程骨架”：

| 领域 | 当前状态 | 备注 |
| --- | --- | --- |
| 包元信息 | 已有 | `hubvault.config.meta` 可用 |
| CLI 壳层 | 已有 | `hubvault.entry` 能输出版本与帮助 |
| 打包/测试基础设施 | 已有 | `Makefile`、`pytest.ini`、`setup.py` 已就位 |
| 公开仓库 API | 缺失 | `HubVaultApi` 及相关模型尚未实现 |
| 存储引擎 | 缺失 | commit/tree/blob/chunk 均未落地 |
| 事务协议 | 缺失 | 锁、恢复、回滚、校验尚未实现 |
| GC/verify/merge | 缺失 | 仍停留在设计阶段 |

因此，本项目的初始化规划必须优先解决“如何从 0 到 1 做出可运行 MVP”，而不是一开始就把 pack、GC、merge、原生加速全部做完。

## 2. 项目目标

目标是设计并实现一个“本地版、嵌入式、API-first”的版本化仓库系统，重点服务如下场景：

- 本地保存模型权重、数据集、训练产物、索引文件等中大体积文件
- 需要版本管理、历史回滚、分支与标签能力
- 需要强一致性、崩溃恢复和校验能力
- 需要纯 Python 即可运行，不依赖外部服务
- 需要跨平台支持 Linux、macOS、Windows
- API 使用手感尽量接近 `huggingface_hub.HfApi`

## 3. 核心约束

- 不依赖 SQLite、Redis、PostgreSQL 或其他外部数据库
- 不依赖守护进程、后台服务或额外安装的服务端
- 不要求兼容 git workspace、git index 或 git CLI
- 首版只要求单写者、多读者，不做多写者事务并发
- 必须兼容 Python 3.7-3.14 与三平台常见文件系统
- 仓库必须是自包含的，所有持久化状态都位于 repo root 下，不依赖仓库外部路径上的元数据、缓存或 sidecar 文件
- 允许后续引入可选 C/Rust 加速，但正确性不能依赖原生扩展

## 4. 第一优先级

第一优先级不是“完整复刻 git 或 Hugging Face Hub”，而是：

- 已提交对象绝不被原地破坏
- 崩溃恢复后仓库仍处于合法、可诊断状态
- 历史版本可读取、可校验、可回滚
- 后续 GC/compact 不会误删仍可达的数据
- 关闭仓库后整体移动目录、打包再解压，仍然不影响仓库正确性

## 5. MVP 切分

### 5.1 MVP 必须实现

MVP 只要求打通以下最短路径：

- `create_repo()` 初始化本地仓库
- `repo_info()` 返回格式版本、默认分支和 head 信息
- `create_commit()` 支持公开 `CommitOperationAdd` / `CommitOperationDelete`
- `list_repo_tree()` / `list_repo_files()` 能列目录与文件
- `open_file()` / `read_bytes()` / `hf_hub_download()` 能读取内容
- `reset_ref()` 能把分支回退到历史 commit
- `quick_verify()` 能做最小一致性体检
- 已关闭的仓库目录可以直接 `mv` 到新路径后重新打开，行为不变
- 通过公开文件信息接口拿到 `oid` / `sha256`
- 公开 `sha256` 的格式要与 HF 一致，使用裸 64 位 hex，而不是 `sha256:<hex>`
- `hf_hub_download()` 返回的文件路径以 repo 内原始相对路径结尾，而不是内部 blob 名

### 5.2 MVP 明确不做

为了尽快产出可用版本，以下内容从 MVP 延后：

- chunked file、pack、LSM 索引
- merge 与冲突求解
- full verify
- GC / compact
- 文本内容级自动 merge
- 面向远端平台的 token、权限、PR、discussion、webhook、space 等能力

### 5.3 MVP 代表性使用方式

```python
from hubvault import HubVaultApi, CommitOperationAdd

api = HubVaultApi("/data/repos/demo")
api.create_repo()
api.create_commit(
    revision="main",
    operations=[
        CommitOperationAdd.from_bytes(
            path_in_repo="weights/config.json",
            data=b'{"dtype":"float16"}',
        ),
    ],
    commit_message="add config",
)

content = api.read_bytes("weights/config.json", revision="main")
```

## 6. 非目标

以下内容不作为首版目标：

- 兼容 git hooks、git index 与 git 子模块
- 多写者高并发事务系统
- 网络文件系统上的强一致保证
- 对二进制大文件做内容级自动 merge
- 把 CLI 做成主入口；前期仍坚持 API-first

## 7. 成功标准

### 7.1 MVP 成功标准

- 在空目录中初始化仓库成功
- 通过公开 Python API 完成提交、读取、列树、回滚
- 发生异常中断后不会破坏已提交版本
- 仓库关闭后整体搬迁路径或打包迁移后仍可正常打开、读取、校验
- 对单个文件可以稳定拿到 HF 风格 `oid` / `sha256`，其中 `sha256` 为裸 hex
- `hf_hub_download()` 与快照导出路径保持 repo 相对路径层级与文件名保真
- 单元测试能通过公开 API 覆盖新增能力
- `make unittest` 通过

### 7.2 完整版本成功标准

- 支持 branch、tag、merge、verify、GC、compact
- 支持大文件 chunked / pack 存储和 range read
- 可以列出历史、refs、文件信息并执行回收策略

## 8. 术语约定

- `Repo`：一个逻辑仓库，对应一个本地根路径
- `Ref`：分支或标签，指向某个 commit
- `Commit`：一次不可变版本快照
- `Tree`：目录树对象
- `Blob`：whole-file 存储对象
- `File`：文件版本对象，引用 blob 或 chunk 列表
- `Chunk`：大文件切分后的数据块
- `Pack`：多个 chunk 的顺序存储文件
- `Txn`：一次写事务的暂存目录与提交流程
- `GC`：不可达对象清理与 pack 重写

## 9. 设计原则

- 不可变优先：所有核心对象一经提交即不可变
- 协议先行：先冻结对象格式和事务协议，再推进实现
- MVP 优先：先 whole-file，后 chunk/pack
- 全息优先：repo root 本身就是完整仓库，任何持久化元数据都不得把真相散落到仓库外
- 公开表面优先：测试和示例优先走公开 API，而不是内部 helper
- 显式回收：逻辑回滚与物理删除必须分离
- 跨平台保守：仅依赖三平台都稳定可用的文件系统语义
