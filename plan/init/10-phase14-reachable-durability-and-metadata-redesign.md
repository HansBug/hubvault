# 10. Phase 14 Reachable-State Durability 与 Metadata 事务化重构

## Goal

在 Phase 13 已完成当前时间路径热点收敛之后，用新的“可达状态安全”和“全局可串行化”定义重新审视 `backend.py` 的断电/崩溃语义、Windows 耐久性边界、同进程/跨进程/跨节点并发边界、metadata fan-out 成本和后续可替换依赖，明确下一轮应先做哪些安全硬化，再做哪些重构与性能收益回收。

## Status

未开始。

## 为什么需要 Phase 14

当前实现已经通过了 Phase 8 的公开 failpoint 基线，但最新复盘表明，下一轮工作的判断标准需要更精确：

- `create_commit.after_publish`
  中断后旧 head 保持可读、旧文件内容保持正确、`quick_verify()` / `full_verify()` 继续通过，但可能留下 `txn/` 残留和不可达孤儿对象。
- `create_commit.after_ref_write` / `create_commit.after_reflog_append`
  当前 ref-changing 路径已经能把可达状态回滚到旧 head，不会把半提交 ref 暴露给后续读取。
- `gc.after_publish`
  中断后 live 主状态保持可读，校验继续通过；留下的只是可回收垃圾和待清理事务目录，而不是可达真相损坏。
- 这意味着 Phase 14 不应再把“有孤儿对象/残留事务目录”视为 correctness 失败，而应把注意力集中到：
  可达数据是否可能损坏；
  Windows / 断电语义是否足够硬；
  同进程线程、同机多进程和跨节点共享路径访问是否都保持可串行化；
  当前自定义 metadata / manifest / small-file durability 协议是否值得继续维护。

## 新的损坏定义

Phase 14 统一采用下面这套判断标准。

### 视为数据损坏

- 任意可达 ref 指向的 commit closure 无法完整读取。
- 任意可达 tree/file/blob/chunk 在公开 API 下出现读失败、校验失败、内容不一致或 hash 不一致。
- 可达文件的 `oid` / `sha256` / size / range read 与实际字节不一致。
- `quick_verify()` / `full_verify()` 在只检查正式可达仓库真相时发现错误，而不是仅发现缓存或垃圾残留。
- 仓库在重开后把 ref 指向一个缺对象、缺 pack、缺 chunk index 的半提交状态。

### 不视为数据损坏

- 不可达孤儿对象。
- `txn/` 残留目录，只要它不让可达主状态失真。
- `cache/files/`、`cache/snapshots/`、detached view 被用户改坏或丢失。
- `gc()` / `squash_history()` 中断后留下的可回收垃圾、待隔离文件或未完成清理痕迹。
- 任何后续可以由 `gc()`、恢复逻辑或显式 maintenance pass 清掉、且不污染可达主状态的残留。

### 对应的公开语义

- 对 ref-changing 写路径：
  如果 API 没有明确成功返回，则对调用方可达的 ref/tree/file 语义必须等效于“旧状态仍然成立”，不能出现第三种半提交可见态。
- 对 storage-only 维护路径：
  允许留下不可达垃圾，但不允许让可达主状态产生读错、缺块、错 hash 或 ref 漂移。
- 对 verify / diagnose 路径：
  应明确区分“reachable corruption”与“reclaimable residue”，不能把两者混成同一类错误。

## 全局可串行化定义

Phase 14 同时把线程安全和进程安全提升为和 reachable-state safety 同级的硬约束。

### 必须覆盖的并发范围

- 同一 Python 进程内的多个线程同时调用同一个或不同的 `HubVaultApi` / backend 实例。
- 同一台机器上的多个 Python 进程或 CLI 进程同时访问同一个 repo root。
- 不同机器上的进程通过共享路径访问同一个 repo root，例如 repo root 位于 NFS、SMB 或其它网络挂载路径上。

### 可串行化要求

- 任意一组公开 API / CLI 操作的执行结果，都必须等价于某个单线程全序串行执行。
- 写操作必须有唯一线性化点；成功返回的写操作必须在该点之后对后续读可见，失败或中断的写操作不能留下可达半提交状态。
- 读操作可以并发，但每次读只能观察到一个完整 committed snapshot，不能混合读到同一写操作前后的部分状态。
- 两个并发写操作必须串行化；不能出现 lost update、双 head、reflog 顺序和 ref 顺序不一致、chunk index 可见顺序错乱等结果。
- 维护操作 `gc()` / `squash_history()` 必须与普通写操作串行化；它们可以留下不可达垃圾，但不能删除任何在其线性化快照中可达或并发写入后会变成可达的对象。
- 可串行化要求不因运行位置变化而放宽：线程内、同机多进程、跨节点共享文件系统访问都必须满足同一语义。
- 仓库可搬迁要求也不因运行位置变化而放宽：repo root 必须始终是完整真相，可以直接 `zip` 打包、搬到任意机器或路径、解压后立刻打开使用，不允许额外恢复、注册、初始化或 sidecar 补全步骤。

### 选型约束

- 不能只依赖进程内 `threading.Lock` 之类机制，因为它无法覆盖多进程和跨节点。
- 不能假定当前 host-local 文件锁、SQLite 默认锁模式或任意第三方库在 NFS/SMB 上天然满足要求；必须查明官方语义并用跨节点实验验证。
- 如果某个 metadata substrate 或锁方案只能保证单机可串行化，不能作为 Phase 14 默认方案，除非实现额外的共享路径可串行化层。
- 若某类网络文件系统无法提供必要的锁和原子 rename / durability 语义，代码必须显式拒绝进入多节点写入模式，不能静默降级到不安全行为。

## 当前代码结论

基于 `backend.py` 当前实现与已跑过的 failpoint / profiling 复盘，Phase 14 之前的状态可以总结为：

- 当前事务状态机已经足够保证“可达 ref 真相不暴露半提交状态”。
- 当前实现尚不能严格证明“Windows 上断电后仍绝不会出现可达损坏”。
- 当前 `fasteners.InterProcessReaderWriterLock` 已覆盖同机多进程读写锁基线，但 Phase 14 尚不能直接假定它覆盖跨节点 NFS/SMB 可串行化。
- 当前最值得重审的不是 merge/tree 算法，而是 metadata 与 durability 协议本身。
- 当前最重的写侧热点主要是 `fsync` fan-out 和 metadata 小文件写入，不是核心算法复杂度。
- 当前最重的读侧基础设施热点主要是 chunk visible-index 构建与 metadata fan-out，不是 warm download 本体。

当前已知的主要风险点如下：

- `_fsync_directory()` 仍是 best-effort，Windows 上目录项耐久性无法被当前实现严格证明。
- 当前并发基线主要面向同机多进程；跨节点共享挂载访问需要重新选型、验证和必要时增加拒绝机制。
- `create_repo()` bootstrap 不是完整事务化流程，初始化边界仍有进一步收紧空间。
- chunk index 仍是自定义 `MANIFEST + JSONL segment`，事务性、读放大和后续优化空间都不够理想。
- commit/tree/file/blob metadata 仍由大量小 JSON 文件组成，既带来 durability 成本，也带来 metadata-heavy 性能开销。

## 设计原则

- repo root 继续保持自包含，所有真相仍位于 repo root 内。
- repo root 的自包含要求进一步收紧为“zip 级可移植”：
  一个仓库目录必须可以直接打包、搬走、解压，然后在新位置立即启用；不允许依赖宿主绝对路径、系统注册状态、仓库外 sidecar 文件、外部数据库或额外一次性迁移步骤。
- 以“可达状态安全”优先，而不是以“绝对没有垃圾残留”优先。
- 不做 roll-forward；未完成写入最多留下不可达垃圾，不能补完成提交。
- 所有公开操作必须可串行化；读并发可以保留，但写和维护操作必须有全局线性化边界。
- 优先引入成熟事务语义，而不是继续扩张自定义多文件提交协议。
- 尽量不为了 Phase 14 MVP 抬 Python 版本下限；如无必要，不因局部优化放弃 Python 3.7/3.8 与 Windows。
- 只有当第三方库在安全、性能或维护成本上带来实质收益时才引入。

## 候选依赖与替代评估

| 目标区域 | 当前实现 | 候选依赖 | 可行性 | 主要收益 | 主要风险/成本 | 当前判断 |
| --- | --- | --- | --- | --- | --- | --- |
| metadata / refs / reflog / txn journal | 多文件 JSON + 文本 ref + reflog JSONL | `sqlite3`（stdlib） | 本地高，跨节点待验证 | 跨平台、无新依赖、事务语义成熟、显著降低 metadata fan-out | 需要做 schema、迁移与 adapter 重构；NFS/SMB 上的锁、journal 和 durability 语义必须单独验证 | Phase 14 MVP 首选候选，但跨节点语义是硬门槛 |
| metadata / refs / reflog / txn journal | 多文件 JSON + 文本 ref + reflog JSONL | `lmdb` | 中 | ACID KV、读性能强、也可覆盖 index metadata | 额外依赖、当前活跃版本与 Python 版本/Windows 打包需要单独验证；网络文件系统语义也不能假定成立 | 可作为备选，不做默认首选 |
| 全局锁 / 串行化层 | `fasteners.InterProcessReaderWriterLock` | 成熟文件锁、数据库事务锁或显式共享 FS lock backend | 待验证 | 统一线程、进程、跨节点线性化边界 | NFS/SMB 锁语义和故障恢复差异大，必须做官方语义核查与实测 | Phase 14 必做选型项 |
| chunk 压缩 | `compression=\"none\"` | `zstandard` / `pyzstd` | 中 | 降低 pack 体积、改善慢盘 I/O | 需要格式升级、读写 CPU 权衡、Windows 打包验证 | 适合作为 14D 可选项 |
| JSON 编解码 | `json` | `orjson` / `msgspec` | 中到低 | 某些 metadata-heavy 路径可降 CPU | 当前收益不如事务基建显著，通常还伴随更高 Python 版本要求 | 明确后置 |
| Git graph/ref 基础设施 | 自定义 commit/tree/ref 语义 | `dulwich` / `pygit2` | 低 | 可复用部分 Git 语义实现 | 不能解决当前 durability / metadata fan-out 主矛盾，兼容与打包成本高 | 不作为 Phase 14 主线 |

## 推荐重构方向

### 推荐主线：SQLite-first metadata 事务化

Phase 14 默认优先考虑把 repo 内“高频 metadata 真相层”收进一个 repo-local SQLite 数据库，而不是继续扩大自定义文件协议。但 SQLite-first 只有在满足全局可串行化要求后才可以成为默认实现；跨节点共享路径上的锁与 journal 语义必须先被验证。

推荐优先纳入 SQLite 的内容：

- branch/tag refs
- reflog records
- txn state / recovery journal
- chunk visible manifest / chunk index metadata
- 如果原型证明收益明显，再继续纳入 commit/tree/file/blob metadata

保留在文件系统中的内容：

- blob payload bytes
- chunk pack payload bytes
- detached view / snapshot cache
- quarantine 与显式可清理垃圾

这样做的理由：

- `sqlite3` 是标准库，跨平台和 Python 版本覆盖最好。
- refs / reflog / txn state / chunk visible metadata 是当前 correctness 与性能的共同交叉点。
- 即使后续仍保留 pack/blob 外置文件，先把 metadata 统一进事务层，也能显著收敛状态机复杂度和小文件 `fsync` 风暴。
- 如果 SQLite 不能在目标共享文件系统组合上证明跨节点可串行化，则必须增加外层全局锁 backend，或拒绝跨节点多写者模式。
- 即便引入新的 metadata store，它也必须严格位于 repo root 内，并且仓库在 zip/unzip 后不需要额外 rebuild、VACUUM、attach 或 re-register 才能重新启用。

### 可接受的渐进式切分

Phase 14 不要求一步把所有 metadata 一次性搬进数据库。建议按收益和风险分层：

- Tier 1：
  `refs + reflog + txn journal + chunk visible manifest/index metadata`
- Tier 2：
  `commit/tree/file/blob metadata`
- Tier 3：
  chunk compression、JSON codec、更多 OS-specific I/O 手段

### 需要明确的现实边界

即便采用 SQLite-first，若 blob/pack payload 仍保留为外部文件，Windows 上“断电后 payload 文件 rename 和目录项已稳定持久化”的证明仍不能完全跳过。

因此 Phase 14 应把问题拆开：

- 先用事务化 metadata 把当前 correctness / 性能 / 维护复杂度最大的部分压下去。
- 同时把全局可串行化锁边界纳入 metadata substrate 选型，不能只看本机单进程 benchmark。
- 再决定是否需要进一步做 payload 激活协议、payload journal，或更激进的 payload 存储重构。

## Phase 14A. Reachable-State 语义收口与实验基线

### Goal

把新的损坏定义、校验语义和异常测试口径先收口，确保后续重构不会继续被“是否留下孤儿对象”这种问题误导。

### Status

未开始。

### Todo

* [ ] 把计划文档、测试命名和异常安全说明统一改成“reachable-state safety”口径。
* [ ] 明确区分 ref-changing 写路径与 storage-only 维护路径的异常判定规则。
* [ ] 为 `quick_verify()` / `full_verify()` / `get_storage_overview()` 补一套预期分类：reachable corruption、reclaimable residue、cache damage。
* [ ] 用公开 API 固化一组新的 failpoint 复盘脚本，至少覆盖 `create_commit.after_publish`、`after_ref_write`、`after_reflog_append`、`merge.after_publish`、`gc.after_publish`。
* [ ] 记录 Linux 与 Windows 两套最低可接受语义，不再把尚未证明的强断电语义直接写成“已成立”。
* [ ] 固化同进程多线程、同机多进程、跨节点共享路径三类可串行化测试矩阵。
* [ ] 固化 zip 打包迁移测试矩阵：关闭状态直接打包、换路径解压、换机器/换挂载点后直接打开，不允许额外初始化步骤。

### Checklist

* [ ] 计划文档不再把“存在不可达孤儿对象”误写成数据损坏。
* [ ] 对 ref-changing 路径，期望仍明确为“可达状态要么旧、要么新”。
* [ ] 对 storage-only 路径，期望明确为“允许留垃圾，但不允许 reachable truth 出错”。
* [ ] `quick_verify()` / `full_verify()` / `get_storage_overview()` 的角色边界在文档中清楚区分。
* [ ] 公开并发测试能证明读看到完整快照，写与写、写与维护操作都有唯一串行化顺序。
* [ ] 公开迁移测试能证明仓库 zip/unzip 后可直接启用，无需仓库外 state 或额外恢复动作。

## Phase 14B. Metadata Substrate 选型与 Windows Durability 复盘

### Goal

在真正改实现前，把最值得替换的模块、第三方依赖、Windows 耐久性风险、跨节点共享路径可串行化风险和迁移边界评估清楚，避免边改边重新选型。

### Status

未开始。

### Todo

* [ ] 对 `sqlite3`、`lmdb` 和“继续维护当前文件协议”三条路线做同口径比较，覆盖安全、性能、迁移、Python 版本、Windows 打包成本和跨节点共享 FS 可串行化成本。
* [ ] 对当前 `fasteners` 锁语义做同进程、同机多进程和跨节点共享路径适用性复盘，不能把同机通过直接外推到 NFS/SMB。
* [ ] 查明候选 metadata substrate 在 NFS/SMB 上对锁、journal、atomic rename 和 crash recovery 的官方限制。
* [ ] 产出 repo-local metadata schema 草案，至少覆盖 refs、reflog、txn state、chunk visible index。
* [ ] 评估 commit/tree/file/blob metadata 是进入同一个 metadata store，还是先保留文件对象格式。
* [ ] 补一轮 Windows / NTFS 关注点清单，明确当前 `_fsync_directory()` 和多文件发布协议哪里缺证明。
* [ ] 为 `create_repo()` bootstrap 定义更严格的事务边界，不再把初始化视作“写几个文件再补一个 commit”的松散组合。
* [ ] 审查所有候选 substrate 是否都满足“repo root 内自包含 + zip/unzip 后直接可用”，不能引入仓库外 sidecar 或首次打开补写步骤。

### Checklist

* [ ] 已明确 Phase 14 MVP 的默认 metadata substrate。
* [ ] 已明确 Phase 14 MVP 是否需要抬 Python 最低版本；如不需要，应维持现有兼容目标。
* [ ] 已明确哪些自定义协议继续保留，哪些由成熟事务层替换。
* [ ] 已明确 Windows 上目前“已证明”和“未证明”的 durability 语义边界。
* [ ] 已明确同进程线程、同机多进程、跨节点共享路径各自的 serializability 保障机制。
* [ ] 已明确所有候选方案在 zip 级可移植性上的成立条件，不允许“需要额外修复后才能启用”的默认方案。

## Phase 14C. Metadata 事务化 MVP

### Goal

落地最小但真实有收益的一轮 metadata 重构，优先同时改善 reachable-state 安全边界、恢复复杂度和 metadata-heavy 性能。

### Status

未开始。

### Todo

* [ ] 在 repo root 内引入统一 metadata store，并保留自包含/可搬迁约束。
* [ ] 将 refs、reflog 和 txn state 接入新的 metadata 事务层。
* [ ] 将 chunk visible manifest / visible index metadata 接入新的 metadata 事务层。
* [ ] 为当前读路径提供新的 metadata adapter，避免每次读取都全量 materialize visible index。
* [ ] 为当前写路径提供新的 metadata commit barrier，减少小文件元数据写入与 `fsync` fan-out。
* [ ] 为所有写 API 和维护 API 定义并实现统一线性化点，确保并发结果可串行化。
* [ ] 为同进程多线程和同机多进程补公开 API 压测，覆盖 lost update、并发 branch update、concurrent gc 与读写交错。
* [ ] 为跨节点共享路径建立可选集成测试或手动验收脚本，至少覆盖两个节点同时写、一个节点写一个节点读、一个节点 gc 另一个节点读写。
* [ ] 重新定义恢复流程：未完成事务最多留下不可达 payload 或待清理 residue，不再依赖大量文件散布的状态痕迹。
* [ ] 在公开 API 下保留现有 detached view、HF-style path suffix 和公开模型语义不变。
* [ ] 为 zip/unzip 后直接启用建立公开回归，覆盖普通路径、含事务残留路径和 shared mount 路径切换后的重新打开。

### Checklist

* [ ] 公开 API 行为、公开模型和 detached view 语义不回退。
* [ ] ref-changing 路径的恢复逻辑比当前更简单，而不是更复杂。
* [ ] `read_range()` / `hf_hub_download()` / `snapshot_download()` 不再依赖昂贵的可见索引全量构建。
* [ ] 小文件 commit / merge / metadata-heavy listing 的主要热点不再是 metadata fan-out。
* [ ] 新实现仍只依赖 repo root 内状态，不依赖外部数据库服务。
* [ ] 同进程、同机多进程和跨节点共享路径都满足同一个可串行化公开语义，或在无法保证的共享 FS 上显式拒绝危险写入模式。
* [ ] 仓库目录在 zip/unzip、换路径、换机器后仍可直接启用，不需要额外 rebuild、attach、迁移或 sidecar 补全。

## Phase 14D. Payload Durability 收口与后续性能项

### Goal

在 metadata 事务化之后，再决定是否需要继续处理 payload 文件激活语义、压缩和更高阶性能项。

### Status

未开始。

### Todo

* [ ] 评估 blob/packs 继续作为外部文件时，Windows 上还剩多少未解决的断电证明缺口。
* [ ] 如有必要，为 payload 文件补显式 activation barrier、payload journal 或更严格的 staged publish 协议。
* [ ] 在 metadata 新基线稳定后，重新测 small-batch commit、merge-heavy、full-verify、large-upload、range-read。
* [ ] 视收益决定是否引入 `zstandard` / `pyzstd` 做 chunk compression。
* [ ] 视 Python 版本策略决定是否引入 `orjson` / `msgspec` 作为局部 codec 优化。

### Checklist

* [ ] 已明确 metadata 事务化之后剩余的 reachable-state 风险是否主要来自 payload durability。
* [ ] 已明确 chunk compression 是真实收益项，而不是格式复杂度先行。
* [ ] 已明确 JSON codec 优化是否值得为之抬 Python 版本下限。
* [ ] 所有后续性能项都建立在新的安全口径之上，而不是为了 benchmark 牺牲恢复语义。

## Phase 14 MVP Cut

Phase 14 的最低可接受交付为：

- Phase 14A 完成，新的 reachable-state 安全定义正式生效。
- Phase 14B 完成，metadata substrate 和 Windows durability 边界有清晰结论。
- 至少完成 Phase 14C 的设计闭环：
  metadata schema、迁移策略、读写 adapter 边界、恢复状态机和全局串行化策略都已定稿。
- 已明确并验证 Phase 14 默认方案继续满足“zip 打包搬走，解压后直接启用”的严格自包含约束。

如果实现资源允许，MVP 进一步希望直接落下：

- refs / reflog / txn state / chunk visible metadata 的事务化落地。

## Deferred Items

下面这些内容明确不属于 Phase 14 MVP：

- 全量把所有 payload bytes 直接搬入数据库。
- 用 `dulwich` / `pygit2` 替掉当前主仓库逻辑。
- 因局部 JSON 或 codec 收益而直接抬 Python 版本到 3.9+。
- 异步/并发写入重构。
- 放宽同进程、同机多进程或跨节点共享路径的可串行化语义。
- 为了追 benchmark 结果而改动 detached view、HF-style path suffix 或 rollback-only 公开语义。
