# 09. Phase 13 Hotspot Profiling 与时间路径收敛

## Goal

在 Phase 12 已补齐 benchmark 数据集、指标口径与长期回归产物之后，只围绕真实可测的热点推进时间路径优化，优先解决当前仍有回退、波动或明显 metadata 成本的公开用户路径。

## Status

进行中（13A 已完成首轮 benchmark -> profiling -> optimize -> benchmark 闭环；13B / 13C 未开始）。

## 当前最新进展

- benchmark anchor commit：
  `9b5e14010608c31b271459262dcaf1c540b5d1ee`（`9b5e140`）
- compare baseline commit：
  `26a198711dc41e1bf2ec091361f4b64543a69210`（`26a1987`）
- full benchmark artifact：
  `build/benchmark/phase13/summary/phase13-standard-full-9b5e140.json`
- manifest artifact：
  `build/benchmark/phase13/manifests/phase13-standard-full-9b5e140-manifest.json`
- current profiling artifacts：
  `build/profiling/phase13/read_range_standard.prof`
  `build/profiling/phase13/hf_hub_download_warm_standard.prof`
  `build/profiling/phase13/hf_hub_download_cold_standard.prof`
  `build/profiling/phase13/snapshot_download_mixed_standard.prof`
  `build/profiling/phase13/history_deep_listing_standard.prof`
  `build/profiling/phase13/merge_heavy_non_fast_forward_standard.prof`
- this repo keeps `build/` ignored, so the reproducibility anchor must be recorded here by commit ID + local artifact path, rather than by checking benchmark JSON into git.

13A 当前已经落地并回归通过的实现项包括：

- direct path resolver：
  `read_bytes()`、`read_range()`、`hf_hub_download()` 不再为了单文件读取先 flatten 整棵 snapshot。
- `read_range()` 首轮低风险优化：
  一次性 `visible_entries()`、batched overlap resolve、pack file handle reuse、`bytearray` 输出缓冲。
- warm managed-view fast path：
  managed cache 命中 metadata 时直接复用现有 detached view，不再 repo re-read / detached re-hash / unchanged metadata rewrite。
- `snapshot_download()` quick return + selective repair：
  commit/pattern 完全匹配时直接返回，已有 snapshot 只修复缺失或失配文件。
- repo-managed cache 写入减重：
  repo 自管 `cache/` 路径不再做不必要的 durable `fsync`，并且 download/snapshot 热路径已移除 `_materialize_content_pool()` 的额外写放大。

## 最新 benchmark 快照

| scenario | Phase 12 baseline | Phase 13 (`9b5e140`) | delta vs baseline | current judgment |
| --- | --- | --- | --- | --- |
| `large_upload` | `208.70 MiB/s`, `p50 0.138884s` | `198.18 MiB/s`, `60.91%` of host write baseline, `p50 0.144452s` | throughput `-5.04%`, p50 `+4.01%` | 写路径不是本阶段主瓶颈，但也没有继续上升 |
| `large_read_range` | `223.96 MiB/s`, `p50 0.126996s` | `204.54 MiB/s`, `3.15%` of host read baseline, `p50 0.129064s` | throughput `-8.67%`, p50 `+1.63%` | 仍是 Phase 13 当前第一瓶颈 |
| `hf_hub_download_cold` | `281.80 MiB/s`, `p50 0.206108s` | `534.09 MiB/s`, `8.24%` of host read baseline, `p50 0.188860s` | throughput `+89.53%`, p50 `-8.37%` | 已明显逼近 hard target，但还没过线 |
| `hf_hub_download_warm` | `437.56 MiB/s`, `p50 0.232882s` | `15768.73 MiB/s`, `243.13%` of host read baseline, `p50 0.191718s` | throughput `+3503.81%`, p50 `-17.68%` | warm path 已不再构成当前主风险 |
| `cache_heavy_warm_download` | `450.89 MiB/s`, `p50 0.813272s` | `21828.10 MiB/s`, `336.56%` of host read baseline, `p50 0.562698s` | throughput `+4741.06%`, p50 `-30.81%` | cache-heavy warm 也已完成数量级提升 |
| `snapshot_download_small` | `1.06 MiB/s`, `p50 1.338577s` | `15.49 MiB/s`, `cache_amplification 1.053375`, `p50 0.927746s` | throughput `+1360.72%`, p50 `-30.69%` | quick return / selective repair 的收益稳定成立 |
| `mixed_model_snapshot` | `228.24 MiB/s`, `p50 0.527436s` | `465.62 MiB/s`, `cache_amplification 1.000066`, `p50 0.474930s` | throughput `+104.01%`, p50 `-9.95%` | mixed-model snapshot 已达到 `> 2x` |
| `history_deep_listing` | `8157.42 ops/s`, `wall 4.942012s` | `7204.14 ops/s`, `wall 4.662651s` | ops/s `-11.69%`, wall `-5.65%` | wall-clock 略有改善，但 13B metadata cache 还没开始 |
| `merge_heavy_non_fast_forward` | `48.56 MiB/s`, `p50 0.441694s` | `82.61 MiB/s`, `p50 0.407254s` | throughput `+70.12%`, p50 `-7.80%` | merge-heavy 吃到了读侧优化的间接收益 |
| `verify_heavy_full_verify` | `43.52 MiB/s`, `p50 1.409059s` | `28.69 MiB/s`, `p50 1.705525s` | throughput `-34.07%`, p50 `+21.04%` | 当前唯一触发 compare alert 的路径，需要单独排查 |

当前 full benchmark 的 host I/O reference 也需要一起看：

- `large_upload_vs_write_baseline_ratio = 0.609055`
- `large_read_range_vs_read_baseline_ratio = 0.031538`
- `hf_hub_download_cold_vs_read_baseline_ratio = 0.082350`
- `hf_hub_download_warm_vs_read_baseline_ratio = 2.431340`
- `cache_heavy_warm_download_vs_read_baseline_ratio = 3.365621`

这里最需要强调的一点是：`read_range()` 的“相对主机基线比例”虽然比 Phase 12 看起来更高，但这主要来自本轮 host read baseline 本身更低；绝对吞吐从 `223.96 MiB/s` 回落到 `204.54 MiB/s`，所以它仍然是未解决项，而不是已经改善的路径。

## 输入前提

Phase 13 不单独创造“新热点”，而是依赖下面这些前提：

- Phase 12 已产出带 bandwidth / metadata / amplification / stability 分榜的 benchmark 结果
- 每个候选热点都已经有同机同配置的 baseline / candidate 对比
- 至少一轮 `cProfile`、`py-spy` 或 opt-in `tracemalloc` 画像已经落地
- 当前公开语义、磁盘协议、rollback-only 恢复语义和 detached view 语义不再允许为追性能而漂移

如果这些输入不成立，Phase 13 默认不开始真正的实现优化。

## 当前已知候选热点

根据当前最新的 `standard/full` 结果与 host I/O reference，当前最值得继续盯的路径包括：

- `read_range()`
  当前 `large_read_range` 绝对吞吐仍只有 `204.54 MiB/s`，相对 host 顺序读基线约 `3.15%`，说明单文件路径解析的旧浪费虽然已经拿掉，但 per-chunk checksum + pack read 仍是主成本。
- cold `hf_hub_download()` 与冷 `snapshot_download()`
  warm path 已经基本解决，但 cold `hf_hub_download()` 仍只有约 `534.09 MiB/s`，mixed-model cold snapshot 也仍被 chunk read、checksum 和 detached materialization 拖住。
- `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`
  `history_deep_listing` 当前 `wall_clock_seconds = 4.662651`、`operations_per_sec = 7204.135504`，说明操作本体仍不算差，但 end-to-end wall-clock 仍远未达到 `<= 3.2s` 目标。
- `merge_non_fast_forward`
  `merge_heavy_non_fast_forward` 已经提升到 `82.61 MiB/s`、`latency_p50_seconds = 0.407254`，当前 profile 更偏向 durability 成本，因此应在 metadata cache 之后再评估是否继续挖。
- amplification follow-up
  exact duplicate 与 historical duplicate 已经稳定在 `~1.00x` 唯一数据体积，pressure 下 aligned / shifted overlap 也已接近 `1.00x`，因此空间面先保持趋势观察，不再作为 Phase 13 第一优先级实现面。

## 为什么 Phase 13 必须把读路径当成主战场

当前 full benchmark 仍然证明：写路径并不是当前第一矛盾，真正明显落后于同机 I/O reference 的仍是 `read_range()` 与 metadata-heavy 路径；warm download 已经基本退出主战场。

| scenario | standard throughput | pressure throughput | same-machine ratio | interpretation |
| --- | ---: | ---: | ---: | --- |
| `large_upload` | `198.183320 MiB/s` | `-` | `60.91%` of host write baseline | 写路径没有继续升高，但仍不是当前第一优先级 |
| `large_read_range` | `204.540806 MiB/s` | `-` | `3.15%` of host read baseline | 当前最核心、最未解决的读路径热点 |
| `hf_hub_download_cold` | `534.092932 MiB/s` | `-` | `8.24%` of host read baseline | cold download 已大幅改善，但还没过 hard target |
| `hf_hub_download_warm` | `15768.725361 MiB/s` | `-` | `243.13%` of host read baseline | warm path 已经基本解决 |
| `cache_heavy_warm_download` | `21828.103683 MiB/s` | `-` | `336.56%` of host read baseline | cache-heavy warm 也已经基本解决 |
| `mixed_model_snapshot` | `465.618638 MiB/s` | `-` | `7.18%` of host read baseline | mixed-model snapshot 已达 `> 2x`，但冷路径仍有进一步压缩空间 |
| `history_deep_listing` | `7204.135504 ops/s` | `-` | `wall 4.662651s` | metadata-heavy 路径还缺专门的 cache pass |

这意味着 Phase 13 的优化原则必须很明确：

1. 先把 `read_range()` 与 cold materialization path 做成真正的 fast path。
2. 再压 metadata-heavy 的重复 JSON / tree / commit 读取。
3. warm path 和空间侧都转入“保持不回退”的回归监控，而不是继续当作第一优先级实现面。

## 当前实现状态与仍未解决的问题

在 `9b5e140` 上，Phase 13 已经不再是“什么都没做”的状态；当前更准确的描述是“13A 首轮低风险收敛已经完成，但 read-range / metadata-heavy / verify-heavy 仍未收尾”。

| area | current state on `9b5e140` | remaining waste / bottleneck |
| --- | --- | --- |
| 单文件读取路径 | `read_bytes()`、`read_range()`、`hf_hub_download()` 已经改成 direct path resolver，不再先 flatten 全 snapshot | 单文件路径放大问题已解决，剩余瓶颈转移到真实 chunk read / checksum |
| chunked range read | `_read_chunked_file_range()` 已改成一次性 `visible_entries()`、batched overlap resolve、pack handle reuse、`bytearray` 输出缓冲 | 当前主成本仍是 per-chunk `sha256` 校验和 pack 读取；这也是 `read_range()` 还没起来的根因 |
| warm `hf_hub_download()` | managed-view metadata 命中时已经直接返回现有 detached view，不再 repo re-read / detached re-hash / unchanged metadata rewrite | warm path 当前基本收敛，剩余工作不应再优先堆在这里 |
| cold `hf_hub_download()` | 已移除额外的 content-pool 写放大，并保留 direct resolver + lightweight view metadata | 当前主要成本已经收敛到真实 repo truth 读取、chunk 校验和 detached file 物化 |
| `snapshot_download()` | 已有 snapshot-level quick return 和 file-level selective repair；命中 metadata 时不再无脑全量重建 | 冷 snapshot 仍要承担真实文件读取和逐文件 detached write 成本 |
| 深历史枚举 | 还没有做 object payload / public oid / reflog parse cache | `history_deep_listing` 继续被重复 payload 读取、public oid 计算和时间解析拖慢 |
| merge-heavy | 当前 profile 已经更偏向 transaction durability（`fsync`、原子写）而不是 snapshot flatten | 如果还要继续优化，必须非常谨慎，不能牺牲事务语义 |
| verify-heavy | 本轮 benchmark 明确出现 `verify_heavy_full_verify` 回退告警 | 还没有 dedicated profiling，当前只能把它列为 Phase 13 的明确 follow-up 风险 |

## 当前已有的函数级证据

为了避免继续停留在“看 benchmark 猜哪里慢”，当前已经在 `9b5e140` 上刷新了一轮 `cProfile` 证据，产物统一保存在 `build/profiling/phase13/`。

### `read_range()` quick profile

artifact:
`build/profiling/phase13/read_range_standard.prof`

当前最显著的累计热点是：

- `_read_chunked_file_range()`
- `_sha256_hex()` / OpenSSL `sha256`
- `_read_pack_range_cached()`

这说明 direct path resolver 和 batched visible-index resolve 已经把“先 flatten 全 snapshot”“每个 chunk 都单独 lookup / reopen pack”的明显浪费基本扫掉了，当前真正还没解决的是：

- overlapping chunk 的整块校验
- 每个 chunk 的 pack 读取
- Python 层对 chunk 数据的重复处理

### warm `hf_hub_download()` quick profile

artifact:
`build/profiling/phase13/hf_hub_download_warm_standard.prof`

当前最显著的累计热点是：

- `hf_hub_download()`
- `_read_object_payload()`
- `_file_object_id_for_commit()`

这里最关键的结论不是“还有哪里慢”，而是“旧的慢点已经基本消失”：

- repo 真相不再被重新读取
- detached view 不再被重新做全文件哈希
- unchanged metadata 不再被重复重写并 `fsync`

换句话说，warm path 现在已经基本达到了 13A 预期，不应继续把工程精力优先砸在这里。

### cold `hf_hub_download()` quick profile

artifact:
`build/profiling/phase13/hf_hub_download_cold_standard.prof`

当前最显著的累计热点是：

- `_read_file_bytes_by_object_id()`
- `_read_chunked_file_bytes()`
- `_sha256_hex()`
- `_read_chunked_file_range()`
- `_ensure_detached_view()`

这说明 cold download 现在的主要成本已经更接近“真实工作量”本身：

- chunked repo truth 读取
- chunk 级完整性校验
- detached file 物化

接下来的收益如果还要继续抠，就需要从 lower-copy / lower-overhead streaming 和 read-path 校验成本下手，而不是再做 warm-path 风格的 metadata short-circuit。

### `snapshot_download()` mixed-model quick profile

artifact:
`build/profiling/phase13/snapshot_download_mixed_standard.prof`

当前最显著的累计热点是：

- `_read_file_bytes_by_object_id()`
- `_sha256_hex()`
- `_read_chunked_file_range()`
- `_ensure_detached_view()`

这说明 quick return / selective repair 已经把“不必要的 rebuild”和“额外 content-pool 写放大”拿掉了；当前 mixed-model cold snapshot 仍然主要被真实文件读取、逐文件校验和 detached write 主导。

### `history_deep_listing` quick profile

artifact:
`build/profiling/phase13/history_deep_listing_standard.prof`

当前最显著的累计热点是：

- `_read_object_payload()`
- `_public_commit_oid()`
- `_read_staged_or_published_object_payload()`
- `_git_commit_info()`
- `datetime.strptime()`

这说明深历史枚举的问题依然非常明确：metadata cache pass 还没做，所以 payload 读取、public oid 计算和时间解析仍在重复付费。

### `merge_heavy_non_fast_forward` quick profile

artifact:
`build/profiling/phase13/merge_heavy_non_fast_forward_standard.prof`

当前最显著的累计热点是：

- `posix.fsync`
- `_write_bytes_atomic()`
- `_fsync_directory()`
- `_write_json_atomic()`

这说明 merge-heavy 在当前实现上已经不是“读路径 flatten 太多”式的问题，主成本更多落在事务落盘与 durability 语义上。后续如果继续优化，必须先确认收益足够大，再决定是否值得在不破坏恢复语义的前提下收敛写侧成本。

## 当前剩余瓶颈与后续优化方向

| priority | area | current state on `9b5e140` | next direction | expected payoff | risk |
| --- | --- | --- | --- | --- | --- |
| P0 | `read_range()` | 首轮 direct resolver / visible index / pack reuse 已落地，但 absolute throughput 仍只有 `204.54 MiB/s`，并且相对 Phase 12 还有回落 | 先补 read-session verified chunk cache 设计，再评估 `pread` / `mmap` / 更低 copy 的 pack read path | 这是最可能继续拉开差距的路径 | 中 |
| P0 | cold `hf_hub_download()` / cold `snapshot_download()` | warm path 已解决，cold path 主要剩 chunk 读取、校验和 detached materialization | 共享 lower-copy streaming、减少重复 `sha256` / detached write bookkeeping | cold download 有望补齐到 `>= 600 MiB/s`，snapshot 还能继续稳步抬升 | 低到中 |
| P1 | metadata-heavy | `history_deep_listing` wall-clock 仍在 `4.66s`，13B 的 cache 还没开始 | object payload cache、public oid cache、reflog parse cache | 最直接对应 `<= 3.2s` 目标 | 低 |
| P1 | `verify_heavy_full_verify` | 当前唯一触发 compare alert 的回退项，尚无 dedicated profiling | 先补单独画像，确认是 object read、checksum 还是 detached warning/metadata 侧拖慢 | 这是当前最大的残余风险项 | 低 |
| P1 | merge-heavy | 已从 `48.56 -> 82.61 MiB/s`，但 profile 说明主要成本在 durability | 只有在 metadata cache 做完后仍不够，再考虑 merge-base / ancestry cache 与写侧收敛 | 收益可能存在，但不应抢在 `read_range()` 之前 | 中 |
| P2 | OS-specific I/O experiments | 仍未进入实现；当前只允许把它们放到 13C | `pread` / `mmap` 必须保留 Windows / Python 3.7 fallback，不能进入默认正确性语义 | 可能是最终逼近 host read baseline 的必要手段 | 中到高 |

## 具体优化分解

下面保留 Phase 13 的原始优化分解作为 backlog 说明。其中 direct path resolver、warm managed-view fast path、`snapshot_download()` quick return / selective repair，以及 `read_range()` 的 batched visible-index / pack reuse / buffer 收敛已经完成；剩余文字主要代表后续未完成部分。

### 1. 单文件路径解析去 snapshot 化

在 13A 之前，`read_bytes()`、`read_range()`、`hf_hub_download()` 都是：

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

13A 已经按下面这条路线把 warm path 收敛掉了；保留本节是为了说明已经拿到的收益来自什么改动，以及后续冷路径仍可复用哪些思路。

在改造前，warm path 的核心问题不是“有没有复用 view path”，而是：

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

在 13A 之前，`snapshot_download()` 仍然偏保守：

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
| `large_read_range` standard | `204.540806 MiB/s` | `>= 800 MiB/s` | `>= 1500 MiB/s` | 当前仍是最核心、也最未解决的读路径验收项 |
| `large_read_range` pressure | `本轮未复跑；最近一次 pressure artifact 仍明显低于目标` | `>= 1800 MiB/s` | `>= 2500 MiB/s` | 在 standard 先没打通前，不适合过早乐观评估 pressure |
| `hf_hub_download_warm` standard | `15768.725361 MiB/s` | `>= 900 MiB/s` | `>= 1500 MiB/s` | 已远超 hard / stretch target，当前已不再是主问题 |
| `hf_hub_download_cold` standard | `534.092932 MiB/s` | `>= 600 MiB/s` | `>= 1000 MiB/s` | 已逼近 hard target，但还没有真正过线 |
| `cache_heavy_warm_download` standard | `21828.103683 MiB/s` | `>= 900 MiB/s` | `>= 1400 MiB/s` | 已远超 hard / stretch target |
| `history_deep_listing` wall-clock | `4.662651 s` | `<= 3.2 s` | `<= 2.5 s` | 13B metadata cache 还没开始，因此当前仍远未达标 |

本轮只重跑了 `standard/full` 全量 benchmark，所以 checklist 勾选只以这个档位的当前结果为依据；`pressure` 仍作为后续补跑项保留。

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

* [x] 把 `read_bytes()`、`read_range()`、`hf_hub_download()` 从 `_snapshot_for_revision()` 单文件读路径上拆下来，改成 direct path resolver。
* [x] 为 warm `hf_hub_download()` 增加 managed-view metadata fast path，命中时禁止 repo re-read、detached re-hash 和 unchanged metadata rewrite。
* [x] 为 `_read_chunked_file_range()` 增加调用级 manifest/segment cache、batched chunk resolve、pack reader reuse 和输出 buffer 收敛。
* [x] 为 `snapshot_download()` 增加 `commit_id + pattern set` 级 quick return 和 selective repair。
* [ ] 为 `list_repo_commits()`、`list_repo_refs()`、`list_repo_reflog()` 增加调用级 object payload / public oid / reflog parse cache。
* [ ] 为 `read_range()`、warm/cold `hf_hub_download()`、`history_deep_listing`、`merge_heavy_non_fast_forward` 固定 profiling 命令、输入 shape 与产物保存位置，当前基线产物先保存在 `build/profiling/phase13/`。
* [x] 每轮优化后重跑同一批 Phase 12 benchmark，并把收益、无收益和伴随回退统一追记到计划文档，尤其记录相对 host I/O reference 的比值变化。
* [ ] 在 13A/13B 收益不足时，再评估 `pread` / `mmap` / verified chunk cache，并明确 fallback 与兼容性边界。
* [ ] 为已证明高噪声的场景补“只看趋势不设门禁”的说明，避免误报。

## Checklist

* [x] 每项优化都能追溯到一个具体的 benchmark 场景和 profiling 证据。
* [x] 所有优化都保持公开语义、磁盘协议和恢复语义不变。
* [x] 至少两条当前热点路径完成 benchmark -> profiling -> optimize -> benchmark 的闭环。
* [ ] `read_range()` 与 warm/cold `hf_hub_download()` 至少有两条路径获得 `2x` 级别的稳定收益，且没有把写路径和空间放大重新打坏。
* [x] 回归结果不只写“变快了”，而是明确写出收益比例、相对 host I/O reference 的变化、残余风险和未解决点。
* [ ] 如果某个优化方向收益不足，就明确停止，不继续堆复杂度。
