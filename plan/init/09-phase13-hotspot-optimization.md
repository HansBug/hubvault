# 09. Phase 13 Hotspot Profiling 与时间路径收敛

## Goal

在 Phase 12 已补齐 benchmark 数据集、指标口径与长期回归产物之后，只围绕真实可测的热点推进时间路径优化，优先解决当前仍有回退、波动或明显 metadata 成本的公开用户路径。

## Status

未开始。

## 输入前提

Phase 13 不单独创造“新热点”，而是依赖下面这些前提：

- Phase 12 已产出带 bandwidth / metadata / amplification / stability 分榜的 benchmark 结果
- 每个候选热点都已经有同机同配置的 baseline / candidate 对比
- 至少一轮 `cProfile`、`py-spy` 或 opt-in `tracemalloc` 画像已经落地
- 当前公开语义、磁盘协议、rollback-only 恢复语义和 detached view 语义不再允许为追性能而漂移

如果这些输入不成立，Phase 13 默认不开始真正的实现优化。

## 当前已知候选热点

根据 Phase 12 的 `standard` / `pressure` 完整结果与 host I/O reference，当前最值得继续盯的路径包括：

- `read_range()`
  当前 `large_read_range` 相对 host 顺序读基线仍只有约 `2.14%`（standard）到 `10.35%`（pressure），优先怀疑可见索引加载、逐 chunk lookup、逐 chunk 校验与 Python 层 copy path。
- cold / warm `hf_hub_download()` 与 `snapshot_download()`
  当前 cold/warm download 相对 host 顺序读基线仍大致只有 `2%` 到 `4%`，warm 路径虽然已经做到 `cache_amplification = 0`，但 wall-clock 仍明显偏高，优先怀疑 detached view existence check、目录扫描、materialization bookkeeping 与 metadata 解析链路。
- `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`
  `history_deep_listing` 已经在 metadata 分榜中测到 `latency_p50_seconds = 4.942012`、`operations_per_sec = 8157.419516`，说明操作本体吞吐并不差，但 end-to-end wall-clock 仍值得拆开做热点定位。
- `merge_non_fast_forward`
  `merge_heavy_non_fast_forward` 已经纳入 metadata 分榜，当前 `latency_p50_seconds = 0.441694`、`operations_per_sec = 476.315225`，适合在读路径热点之后进入 `merge-base`、tree parse 与 commit graph 遍历 profiling。
- amplification follow-up
  exact duplicate 与 historical duplicate 已经稳定在 `~1.00x` 唯一数据体积，pressure 下 aligned / shifted overlap 也已接近 `1.00x`，因此空间面先保持趋势观察，不再作为 Phase 13 第一优先级实现面。

## 为什么 Phase 13 必须把读路径当成主战场

Phase 12 已经证明：写路径并不是当前第一矛盾，真正明显落后于同机 I/O reference 的是读路径与 materialization 路径。

| scenario | standard throughput | pressure throughput | same-machine ratio | interpretation |
| --- | ---: | ---: | ---: | --- |
| `large_upload` | `208.699282 MiB/s` | `342.373006 MiB/s` | `57.84%` / `93.42%` of host write baseline | 写路径已经进入“可以继续优化，但不是最急”的区间 |
| `large_read_range` | `223.964166 MiB/s` | `1030.396703 MiB/s` | `2.14%` / `10.35%` of host read baseline | 当前第一热点，离同机热读参考仍很远 |
| `hf_hub_download_cold` | `281.802597 MiB/s` | `271.450559 MiB/s` | `2.69%` / `2.73%` of host read baseline | cold download 仍明显受 repo read + detached view materialization 拖累 |
| `hf_hub_download_warm` | `437.556974 MiB/s` | `349.13463 MiB/s` | `4.18%` / `3.51%` of host read baseline | warm 路径已经没有缓存增量，但仍不是“真正的 warm fast path” |
| `cache_heavy_warm_download` | `450.894744 MiB/s` | `377.955732 MiB/s` | `4.31%` / `3.80%` of host read baseline | cache-heavy 场景也说明 warm 路径的主要问题还在时间链路而不在空间膨胀 |
| `mixed_model_snapshot` | `228.235579 MiB/s` | `-` | `-` | mixed-model 导出仍会被目录物化、路径过滤和逐文件 detached view 拖慢 |
| `history_deep_listing` | `8157.419516 ops/s` | `-` | `-` | metadata 吞吐不算差，但 wall-clock 仍偏高，说明存在大量重复对象读取与解析开销 |

这意味着 Phase 13 的优化原则必须很明确：

1. 先把读路径和 warm path 做成真正的 fast path。
2. 再压 metadata-heavy 的重复 JSON / tree / commit 读取。
3. 空间侧只保留回归监控，不再当作第一优先级实现面。

## 当前实现里的直接问题清单

下面这些问题已经能直接从当前实现读出来，不需要再靠猜：

| area | current behavior | likely waste |
| --- | --- | --- |
| 单文件读取路径 | `read_bytes()`、`read_range()`、`hf_hub_download()` 都先走 `_snapshot_for_revision()`，把整棵 tree flatten 成 path -> file_id 映射后再取一个文件 | 单文件读请求被放大成 `O(tree_size)` 的 snapshot materialization |
| chunked range read | `_read_chunked_file_range()` 每次新建 `IndexStore` / `PackStore`，读取 manifest，并对每个 chunk 调 `lookup()`、读 pack、再对整块做 `sha256` 校验 | 小范围读取仍要承担 manifest/segment 查找、pack reopen 和全 chunk 校验成本 |
| warm `hf_hub_download()` | 即使 view 已存在，仍会先把 repo 文件完整读出并重建逻辑 bytes，再调用 `_ensure_detached_view()` 对已有目标文件 `read_bytes() + sha256` 校验，还会重写 materialized pool metadata 与 view metadata | warm path 仍在做“重新读取 repo 真相 + 重新哈希 detached file + 重新落 metadata”，不是轻量复用 |
| `snapshot_download()` | 当前会解析完整 snapshot、过滤路径、遍历所有文件、逐个 `read_file_bytes -> materialize_content_pool -> ensure_detached_view`，即使目标 snapshot 已经存在且 commit 没变 | 缺少 commit-level 和 file-level 的 quick return / selective repair |
| 深历史枚举 | `list_repo_commits()` 先遍历 reachable commits，再对每个 commit 调 `_git_commit_info()`；public oid 解析又会重复读取 commit/tree payload | metadata-heavy 路径存在明显重复 JSON load、pathlib path 构造、`stat()` 和时间解析 |
| merge-heavy | merge 仍先取 target/source/base 三份 flat snapshot，再做 merge-base / identity 判断 / 结构冲突检查 | 对大树或深历史仓库会被 snapshot flatten 与 object payload 重复读取放大 |

## 当前已有的函数级证据

为了避免 Phase 13 继续停留在“看 benchmark 猜哪里慢”，当前已经补了一轮 `cProfile` 证据，产物保存在 `build/profiling/phase13/`。

### `read_range()` quick profile

artifact:
`build/profiling/phase13/read_range_standard.prof`

当前最显著的累计热点是：

- `_read_chunked_file_range()`
- `_sha256_hex()` / OpenSSL `sha256`
- `PackStore.read_chunk()` / `PackStore.read_range()`
- `IndexStore.lookup()` / `load_segment()`

这说明当前 `read_range()` 的主成本不是 Python 包装层，而是：

- overlapping chunk 的整块校验
- 每个 chunk 的 pack 读取
- manifest / segment / entry 查找

### warm `hf_hub_download()` quick profile

artifact:
`build/profiling/phase13/hf_hub_download_warm_standard.prof`

当前最显著的累计热点是：

- `_read_file_bytes_by_object_id()`
- `_read_chunked_file_bytes()` / `_read_chunked_file_range()`
- `_ensure_detached_view()`
- `_materialize_content_pool()`
- `_write_json_atomic()` / `_write_bytes_atomic()` / `fsync`
- `pathlib.Path.read_bytes()`

这说明 warm path 现在最大的结构性问题不是“没有 cache”，而是“命中了 cache 以后仍重新做了大部分冷路径动作”：

- repo 真相仍被重新读取
- detached view 仍被重新哈希
- metadata 仍被重新写盘并 `fsync`

### `history_deep_listing` quick profile

artifact:
`build/profiling/phase13/history_deep_listing_standard.prof`

当前最显著的累计热点是：

- `_read_object_payload()`
- `_public_commit_oid()`
- `_git_commit_info()`
- `_read_json()`
- `pathlib` 路径拼接 / `stat()` / `open()`
- `datetime.strptime()`

这说明深历史枚举的主要问题也不是单点算法错误，而是 metadata 路径上明显存在：

- 重复 commit/tree payload 读取
- 重复 public oid 计算
- 重复 JSON decode 与时间解析

## 优化方向总表

| priority | hotspot | code touchpoints | main direction | expected payoff | risk |
| --- | --- | --- | --- | --- | --- |
| P0 | 单文件读路径先 flatten 全 snapshot | `read_bytes()` / `read_range()` / `hf_hub_download()` -> `_snapshot_for_revision()` | 新增 direct path resolver，按路径段下钻 tree，避免单文件读先构造整张 snapshot | 直接减少单文件读的 tree 读取与 path 构造成本，对 read/download 都有收益 | 低 |
| P0 | warm download 不是 fast path | `_read_file_bytes_by_object_id()`、`_ensure_detached_view()`、`_materialize_content_pool()` | 基于 `view_key + sha256 + size` 做 metadata-driven early return；命中时直接返回现有 view，不再 repo re-read / detached re-hash / metadata rewrite | warm `hf_hub_download()`、cache-heavy warm download 预计最容易获得 2x-4x 提升 | 低 |
| P0 | range read per-chunk 查找和校验过重 | `_read_chunked_file_range()`、`IndexStore.lookup()`、`PackStore.read_range()` | 引入调用级 manifest/segment cache、批量 chunk entry resolve、pack handle reuse、预分配 buffer | `read_range()` 和 cold download 都会受益 | 低到中 |
| P0 | snapshot_download 每次都全量重建 | `snapshot_download()`、`_ensure_detached_view()` | 加 snapshot-level quick return 和 selective repair，只重建缺失/失配文件 | mixed-model snapshot、small tree snapshot 的 wall-clock 会明显下降 | 低到中 |
| P1 | metadata-heavy 路径重复 JSON load | `list_repo_commits()`、`_reachable_commit_order_unlocked()`、`_git_commit_info()`、`list_repo_reflog()` | 调用级 object payload cache / public oid cache / parsed reflog cache；减少重复 `json.load`、`stat`、`strptime` | `history_deep_listing`、refs/reflog、merge 辅助链路收益明显 | 低 |
| P1 | merge-heavy 的 snapshot 和 ancestry 开销 | `merge()`、`_find_merge_base_unlocked()`、`_merge_snapshots_unlocked()` | merge-base / ancestor distance cache、file identity cache 扩展、能 lazy 的路径不先 flatten 全量 snapshot | `merge_heavy_non_fast_forward` 预计可稳步下降 | 中 |
| P2 | pack 随机读取仍偏保守 | `PackStore.read_range()` | 评估 `os.pread()` / `mmap` / 单 pack 文件描述符复用；保持跨平台 fallback | 大范围 read/download 可能再上一个台阶 | 中 |
| P2 | range read 每次都做整 chunk `sha256` | `_read_chunked_file_range()` | 评估“进程内带 mtime/inode 保护的 verified chunk cache”或更轻的 read-session verified cache | 热读与连续 range read 会有较大收益 | 中到高 |

## 具体优化分解

### 1. 单文件路径解析去 snapshot 化

当前 `read_bytes()`、`read_range()`、`hf_hub_download()` 都是：

1. `_resolve_revision()`
2. `_snapshot_for_revision()`
3. 在整张 snapshot 里找目标路径

这对 `snapshot_download()` 这种“本来就要列出整棵树”的操作没问题，但对单文件读取是明显浪费。

Phase 13 应新增一条只服务于单路径读取的内部链路，例如：

- `_file_object_id_for_revision(revision, path_in_repo)`
- `_file_object_id_for_commit(commit_id, path_in_repo)`

目标行为：

- 只按 path segment 逐层读取所需 tree object
- 找到目标 file object 后立即返回
- 不再为了一个文件把整棵树 flatten 成 dict

这会直接覆盖：

- `read_bytes()`
- `read_range()`
- `hf_hub_download()`

### 2. `read_range()` 先做调用级 cache 和 batched resolve

当前 `_read_chunked_file_range()` 的结构性问题有三类：

- manifest / index segment 读取是调用级重复成本
- per-chunk `lookup()` 仍在 segment 里线性回扫
- per-chunk pack read 是独立 open/seek/read/checksum 流程

第一轮应该优先落下面这些零协议风险优化：

- 调用级 `IndexManifest` cache
- 调用级 segment cache
- 把当前 file payload 的 chunk 列表先批量 resolve 成 `chunk_id -> IndexEntry`
- 同一个 pack 的多个 chunk 复用同一个 pack reader / file descriptor
- 输出缓冲改成 `bytearray` / `memoryview`，减少小片段 `bytes` 拼接

第二轮才考虑更重的实验：

- `os.pread()` 或 `mmap`
- read-session verified chunk cache

### 3. warm `hf_hub_download()` 必须变成真正的 fast path

当前 warm path 的核心问题不是“有没有复用 view path”，而是：

- 虽然复用了同一个 path
- 但没有复用“这个 path 已经是正确内容”这一事实

Phase 13 应明确把 managed cache 文件下载拆成两条路径：

`warm fast path`
    命中 `view_key`、metadata 一致、target path 存在、size/sha metadata 一致时，直接返回，不再读 repo 真相，不再读 target file，不再重写 metadata。

`repair path`
    只有在 target 缺失、size 不一致、metadata 缺失或 metadata 不匹配时，才进入当前的重建逻辑。

这条路径的具体优化项包括：

- `cache/views/files/<view_key>.json` 命中后直接 short-circuit
- `_materialize_content_pool()` 在 pool/meta 已存在且匹配时不再重写
- `_ensure_detached_view()` 不再对现有 target 做 `read_bytes() + sha256` 全文件校验，而是优先读 sidecar metadata / size
- unchanged metadata 不再每次 `_write_json_atomic()` + `fsync`

### 4. `snapshot_download()` 从“全量重建”改成“selective repair”

当前 `snapshot_download()` 仍然偏保守：

- 先构建完整 snapshot
- 再遍历全部文件
- 每个文件都重新读 repo truth 并校验 detached view

Phase 13 对它的优化方向应分两层：

`snapshot quick return`
    当 `commit_id + allow_patterns + ignore_patterns` 与 metadata 完全一致，且所有记录文件都存在时，直接返回整个 snapshot root。

`selective repair`
    只修复缺失、损坏或 metadata 不一致的文件，而不是把所有文件重做一遍。

补充方向：

- stale path 清理优先用 metadata diff，减少目录扫描
- 如果只是内部 managed snapshot，可先验证 metadata，再决定是否需要逐文件进入 detached repair

### 5. metadata-heavy 路径要减少重复对象读取

当前深历史路径的主要浪费来自：

- `_reachable_commit_order_unlocked()` 读取 commit payload 一遍
- `_git_commit_info()` 再读取 commit payload 一遍
- `_public_commit_oid()` / `_public_commit_oid_or_none()` 再读取 commit/tree payload
- `list_repo_reflog()` 全文件 `read_text()` 后逐行 `json.loads()`

因此 Phase 13 应明确引入：

- 调用级 `object_payload_cache`
- 调用级 `public_commit_oid_cache`
- 调用级 `public_tree_oid_cache`
- reflog 解析缓存，至少基于 `(path, size, mtime)` 做一次调用内或短时复用
- 非格式化路径下避免不必要的富文本 / 时间解析开销

注意这里强调的是“调用级”或“有明确文件版本保护的短时 cache”，不是进程级全局真相。

### 6. merge-heavy 是第二梯队，但不要再靠感觉优化

merge 当前还不是读路径那种“压倒性差距”，但它已经在 metadata 分榜里稳定可测，所以不该再靠直觉做改动。

优先方向：

- `merge-base` / ancestor distance 结果在一次 merge 调用内复用
- target/source/base snapshot 能 lazy 的地方尽量 lazy
- file identity cache 继续扩展到 merge 冲突判定和结构冲突检查
- 只有在前两层做完仍不够时，才考虑更大的 merge traversal 重写

## Phase 13 的分批落地顺序

### Phase 13A: 先救读路径

目标：

- `read_range()`
- warm `hf_hub_download()`
- cold `hf_hub_download()`
- `snapshot_download()`

首批必须落地的优化：

- direct path resolver，去掉单文件读前的 full snapshot flatten
- warm managed-view metadata fast path
- `_materialize_content_pool()` unchanged no-op fast path
- `_ensure_detached_view()` sidecar/metadata-first fast path
- 调用级 manifest/segment/pack reader cache

### Phase 13B: 再压 metadata-heavy

目标：

- `history_deep_listing`
- `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`
- `merge_heavy_non_fast_forward`

首批必须落地的优化：

- object payload cache
- public oid cache
- reflog parse cache
- merge-base / ancestry cache

### Phase 13C: 最后才做更重的 I/O 实验

只在 13A/13B 收益不足时再做：

- `pread`
- `mmap`
- verified chunk cache

这些实验都必须保留跨平台 fallback，不能把 Windows / Python 3.7 兼容性当作可牺牲项。

## 性能验收目标

Phase 13 需要的是“很大的提速”，不能只接受几个百分点的微调。因此验收要按 hard target 和 stretch target 双层来写。

| scenario | current | Phase 13 hard target | stretch target | note |
| --- | --- | --- | --- | --- |
| `large_read_range` standard | `223.964166 MiB/s` | `>= 800 MiB/s` | `>= 1500 MiB/s` | 这是当前最核心的读路径验收项 |
| `large_read_range` pressure | `1030.396703 MiB/s` | `>= 1800 MiB/s` | `>= 2500 MiB/s` | 目标是明显向同机 I/O reference 靠拢 |
| `hf_hub_download_warm` standard | `437.556974 MiB/s` | `>= 900 MiB/s` | `>= 1500 MiB/s` | warm path 不允许继续 full repo re-read |
| `hf_hub_download_cold` standard | `281.802597 MiB/s` | `>= 600 MiB/s` | `>= 1000 MiB/s` | 冷路径允许慢于 warm，但不能仍停留在当前档位 |
| `cache_heavy_warm_download` standard | `450.894744 MiB/s` | `>= 900 MiB/s` | `>= 1400 MiB/s` | 用来验证 warm 优化不是只对单一大文件有效 |
| `history_deep_listing` wall-clock | `4.942012 s` | `<= 3.2 s` | `<= 2.5 s` | metadata 路径至少要看到 30% 以上下降 |

这些目标故意写得偏激进，因为当前读侧与写侧的差距已经足够大，Phase 13 不应该再满足于“局部微调但用户几乎无感”的收益。

## 优化顺序

Phase 13 的优化顺序固定如下：

1. 先用扩容 benchmark 排序热点，优先锁定 `read_range()` 与 download/materialization 路径。
2. 再用 profiling 确认函数级成本，不凭代码直觉改。
3. 优先做零协议风险优化，例如调用级缓存、批量读取、重复扫描消除和目录遍历压缩。
4. 每轮改动后重跑同一批 Phase 12 benchmark，记录收益与回退。
5. 如果热点无法在零协议风险优化内显著改善，再决定是否进入更重的实现调整。

## 零协议风险优化优先级

Phase 13 默认优先考虑下面这些不改变公开行为和磁盘协议的优化：

- `read_range()` 的调用级 visible-index cache 或 batched chunk lookup，减少重复 `IndexStore.lookup()` / `visible_entries()` 加载
- detached view 路径的目录存在性检查合并、批量 `stat()` / `glob()` 收敛与 metadata cache
- `merge()` 路径的 merge-base、commit/tree 解析缓存，避免一次公开调用内重复反序列化
- 深历史遍历里的 refs / reflog / commit object 调用级缓存
- `full_verify()` / `quick_verify()` / `gc()` 的目录扫描与 pack/index manifest 复用

这些优化都应限定在单次公开调用或单次 benchmark 场景内，不引入进程级全局真相状态。

## 明确不做的事情

Phase 13 默认不做下面这些事情：

- 为了追 benchmark 数字修改公开 `oid` / `blob_id` / `sha256` 语义
- 为了更快绕开事务、原子发布、锁或 rollback-only 恢复
- 引入必须依赖 OS-specific tracing 或 native profiler 才能正确工作的运行时行为
- 把 benchmark 告警反向变成格式或兼容性上的折中
- 因单一合成数据集上的局部结果而回退已经证明有效的 Phase 10 主线

## Profiling Workflow

Phase 13 的 profiling 流程固定为：

### 第一层：benchmark 证据

- 用 Phase 12 benchmark 确认热点场景、输入规模、回退比例和波动模式
- 先判断问题是 bandwidth、metadata、tail latency 还是 amplification 侧问题

### 第二层：函数级画像

- `cProfile`
  适合先看 Python 层累计热点、调用次数和总时间分布
- `py-spy`
  适合补 wall-clock / sampling 视角，避免只看函数自时间
- opt-in `tracemalloc`
  只在怀疑临时对象膨胀、目录树 materialization 或 chunk 列表构建成本明显时启用

### 第三层：回归闭环

- 每个优化都要绑定一个具体 benchmark 场景
- 每个 benchmark 场景都要记录 baseline commit、candidate commit、输入 shape 和 machine signature
- 如果收益不足或伴随更严重回退，就停止继续沿该方向堆复杂度

## Phase 13 MVP Cut

Phase 13 的最低可接受交付为：

- 对 `read_range()`、warm `hf_hub_download()`、cold `hf_hub_download()` 至少完成一轮 benchmark + profiling + 优化闭环
- `read_range()` 与 warm `hf_hub_download()` 至少有一条达到 hard target，另一条至少获得 `2x` 以上稳定收益
- metadata-heavy 路径至少完成一轮 benchmark + profiling + cache 收敛闭环
- 所有收益都能回写到 benchmark compare 报告和计划文档里，而不是只体现在 commit message 里

## Deferred Items

下面这些内容明确不属于 Phase 13 MVP：

- 新的默认存储格式或新的公开兼容层
- 以压缩或新协议替代当前主线实现
- 大规模重写 benchmark harness 本身
- 为所有热点一口气做并行复杂优化而缺少逐项归因

## Todo

* [ ] 把 `read_bytes()`、`read_range()`、`hf_hub_download()` 从 `_snapshot_for_revision()` 单文件读路径上拆下来，改成 direct path resolver。
* [ ] 为 warm `hf_hub_download()` 增加 managed-view metadata fast path，命中时禁止 repo re-read、detached re-hash 和 unchanged metadata rewrite。
* [ ] 为 `_read_chunked_file_range()` 增加调用级 manifest/segment cache、batched chunk resolve、pack reader reuse 和输出 buffer 收敛。
* [ ] 为 `snapshot_download()` 增加 `commit_id + pattern set` 级 quick return 和 selective repair。
* [ ] 为 `list_repo_commits()`、`list_repo_refs()`、`list_repo_reflog()` 增加调用级 object payload / public oid / reflog parse cache。
* [ ] 为 `read_range()`、warm/cold `hf_hub_download()`、`history_deep_listing`、`merge_heavy_non_fast_forward` 固定 profiling 命令、输入 shape 与产物保存位置，当前基线产物先保存在 `build/profiling/phase13/`。
* [ ] 每轮优化后重跑同一批 Phase 12 benchmark，并把收益、无收益和伴随回退统一追记到计划文档，尤其记录相对 host I/O reference 的比值变化。
* [ ] 在 13A/13B 收益不足时，再评估 `pread` / `mmap` / verified chunk cache，并明确 fallback 与兼容性边界。
* [ ] 为已证明高噪声的场景补“只看趋势不设门禁”的说明，避免误报。

## Checklist

* [ ] 每项优化都能追溯到一个具体的 benchmark 场景和 profiling 证据。
* [ ] 所有优化都保持公开语义、磁盘协议和恢复语义不变。
* [ ] 至少两条当前热点路径完成 benchmark -> profiling -> optimize -> benchmark 的闭环。
* [ ] `read_range()` 与 warm/cold `hf_hub_download()` 至少有两条路径获得 `2x` 级别的稳定收益，且没有把写路径和空间放大重新打坏。
* [ ] 回归结果不只写“变快了”，而是明确写出收益比例、相对 host I/O reference 的变化、残余风险和未解决点。
* [ ] 如果某个优化方向收益不足，就明确停止，不继续堆复杂度。
