# 09. Phase 13 Hotspot Profiling 与时间路径收敛

## Goal

在 Phase 12 已补齐 benchmark 数据集、指标口径与长期回归产物之后，只围绕真实可测的热点推进时间路径优化，优先解决当前仍有回退、波动或明显 metadata 成本的公开用户路径。

## Status

进行中（13A 第二轮 read-path 收敛、verify-heavy 修复与 memory benchmark 接入已完成；13B metadata-heavy cache 仍未开始；13C 仅在 pressure 目标仍未达标时再考虑）。

## 当前最新进展

- benchmark anchor commit：
  `cb030e0748d31a1ef79377b4484b6e2b766546d0`（`cb030e0`）
- compare baseline commit：
  `26a198711dc41e1bf2ec091361f4b64543a69210`（`26a1987`）
- previous Phase 13 checkpoint：
  `9b5e14010608c31b271459262dcaf1c540b5d1ee`（`9b5e140`）
- standard/full benchmark artifact：
  `build/benchmark/phase13/summary/phase13-standard-full-cb030e0.json`
- standard/full manifest artifact：
  `build/benchmark/phase13/manifests/phase13-standard-full-cb030e0-manifest.json`
- pressure/pressure benchmark artifact：
  `build/benchmark/phase13/summary/phase13-pressure-pressure-cb030e0.json`
- pressure/pressure manifest artifact：
  `build/benchmark/phase13/manifests/phase13-pressure-pressure-cb030e0-manifest.json`
- compare artifacts：
  `build/benchmark/phase13/compare/phase12-vs-cb030e0.json`
  `build/benchmark/phase13/compare/phase13-9b5e140-vs-cb030e0.json`
- current profiling artifacts：
  `build/profiling/phase13/read_range_standard.prof`
  `build/profiling/phase13/hf_hub_download_warm_standard.prof`
  `build/profiling/phase13/hf_hub_download_cold_standard.prof`
  `build/profiling/phase13/snapshot_download_mixed_standard.prof`
  `build/profiling/phase13/history_deep_listing_standard.prof`
  `build/profiling/phase13/merge_heavy_non_fast_forward_standard.prof`
- this repo keeps `build/` ignored, so reproducibility must continue to rely on commit ID + local artifact path rather than committing benchmark JSON itself.

这轮 `cb030e0` 上已经完成并回归通过的实现项包括：

- direct path resolver：
  `read_bytes()`、`read_range()`、`hf_hub_download()` 不再为了单文件读取先 flatten 整棵 snapshot。
- `read_range()` 第二轮 bounded fast path：
  继续保留调用级 `visible_entries()` / batched overlap resolve / pack handle reuse / `bytearray` 输出缓冲，并额外引入：
  bounded recent chunk cache；
  staged-first recent chunk seeding；
  pack / index signature 校验，确保 cache 命中不会掩盖 pack/index 损坏；
  降低重复 `mkdir/stat` 的 layout ensure 路径。
- first-read object path cache：
  commit/tree/file JSON payload 新增 bounded recent payload cache，显著降低“刚写完立刻首读”的 path resolver 成本，并仍然通过 object file `size + mtime` 防止掩盖对象篡改。
- verify-heavy 修复：
  `full_verify()` 现已复用共享 chunk context、verified chunk state、commit/tree/file 去重与 chunked file 增量哈希，上一轮 compare alert 已被清除。
- warm managed-view fast path：
  managed cache 命中 metadata 时直接复用现有 detached view，不再 repo re-read / detached re-hash / unchanged metadata rewrite。
- `snapshot_download()` quick return + selective repair：
  `commit_id + pattern set` 命中时直接返回，已有 snapshot 只修复缺失或失配文件。
- benchmark memory observation：
  benchmark runner 现在会为关键读/校验路径启动独立 memory probe 子进程，记录 `peak_rss_bytes`、`peak_rss_over_baseline_bytes`、`retained_rss_delta_bytes`、`peak_traced_bytes`、`retained_traced_bytes`，同时不污染正式 timing。

## 最新 benchmark 快照

| scenario | Phase 12 baseline | Phase 13 (`9b5e140`) | Phase 13 (`cb030e0`) | delta vs `9b5e140` | current judgment |
| --- | --- | --- | --- | --- | --- |
| `large_upload` | `208.70 MiB/s`, `p50 0.138884s` | `198.18 MiB/s`, `60.91%` of host write baseline, `p50 0.144452s` | `212.21 MiB/s`, `59.28%` of host write baseline, `p50 0.139349s` | throughput `+7.08%`, p50 `-3.53%` | 写路径回到 Phase 12 之上，但仍不是当前主战场 |
| `large_read_range` | `223.96 MiB/s`, `p50 0.126996s` | `204.54 MiB/s`, `3.15%` of host read baseline, `p50 0.129064s` | `1628.66 MiB/s`, `16.22%` of host read baseline, `p50 0.116559s` | throughput `+696.25%`, p50 `-9.69%` | `standard` 已超过 hard `800 MiB/s` 与 stretch `1500 MiB/s` |
| `hf_hub_download_cold` | `281.80 MiB/s`, `p50 0.206108s` | `534.09 MiB/s`, `8.24%` of host read baseline, `p50 0.188860s` | `712.84 MiB/s`, `7.10%` of host read baseline, `p50 0.176921s` | throughput `+33.47%`, p50 `-6.32%` | `standard` 已越过 `>= 600 MiB/s` hard target |
| `hf_hub_download_warm` | `437.56 MiB/s`, `p50 0.232882s` | `15768.73 MiB/s`, `243.13%` of host read baseline, `p50 0.191718s` | `30075.19 MiB/s`, `299.44%` of host read baseline, `p50 0.178630s` | throughput `+90.73%`, p50 `-6.83%` | warm path 继续远高于目标，不再是主风险 |
| `cache_heavy_warm_download` | `450.89 MiB/s`, `p50 0.813272s` | `21828.10 MiB/s`, `336.56%` of host read baseline, `p50 0.562698s` | `37558.69 MiB/s`, `373.94%` of host read baseline, `p50 0.473485s` | throughput `+72.07%`, p50 `-15.85%` | cache-heavy warm 继续放大优势 |
| `snapshot_download_small` | `1.06 MiB/s`, `p50 1.338577s` | `15.49 MiB/s`, `cache_amplification 1.053375`, `p50 0.927746s` | `18.24 MiB/s`, `cache_amplification 1.053375`, `p50 0.881316s` | throughput `+17.71%`, p50 `-5.00%` | quick return / selective repair 收益继续成立 |
| `mixed_model_snapshot` | `228.24 MiB/s`, `p50 0.527436s` | `465.62 MiB/s`, `cache_amplification 1.000066`, `p50 0.474930s` | `778.70 MiB/s`, `cache_amplification 1.000066`, `p50 0.436494s` | throughput `+67.24%`, p50 `-8.09%` | mixed-model cold snapshot 继续抬升 |
| `history_deep_listing` | `8157.42 ops/s`, `wall 4.942012s` | `7204.14 ops/s`, `wall 4.662651s` | `14714.14 ops/s`, `wall 4.317284s` | ops/s `+104.25%`, wall `-7.41%` | metadata-heavy 明显改善，但仍未达 `<= 3.2s` |
| `merge_heavy_non_fast_forward` | `48.56 MiB/s`, `p50 0.441694s` | `82.61 MiB/s`, `p50 0.407254s` | `71.37 MiB/s`, `p50 0.391287s` | throughput `-13.61%`, p50 `-3.92%` | 吞吐低于上一轮，但 wall/p50 继续改善 |
| `verify_heavy_full_verify` | `43.52 MiB/s`, `p50 1.409059s` | `28.69 MiB/s`, `p50 1.705525s` | `739.34 MiB/s`, `p50 0.526066s` | throughput `+2477.02%`, p50 `-69.16%` | 上一轮 compare alert 已被完全清除 |

当前 `standard/full` 的 host I/O reference 也要一起看：

- `large_upload_vs_write_baseline_ratio = 0.592764`
- `large_read_range_vs_read_baseline_ratio = 0.162154`
- `hf_hub_download_cold_vs_read_baseline_ratio = 0.070972`
- `hf_hub_download_warm_vs_read_baseline_ratio = 2.994361`
- `cache_heavy_warm_download_vs_read_baseline_ratio = 3.739437`

这里最需要强调的变化已经不是“absolute throughput 没起来”，而是相反：`read_range()` 的 absolute throughput 已经从 `204.54 MiB/s` 直接跃升到 `1628.66 MiB/s`。当前最主要的未完成项不再是 standard read-range 本身，而是：

- `pressure` 档 `large_read_range()` 仍只有 `1041.87 MiB/s`
- `history_deep_listing` 的 wall-clock 仍是 `4.317284s`
- pressure / 大对象冷 materialization 的 resident footprint 仍然偏大

### 最新 pressure 快照

| scenario | Phase 13 (`cb030e0`) | same-machine ratio | current judgment |
| --- | --- | --- | --- |
| `large_upload` | `349.26 MiB/s`, `p50 3.864512s` | `92.77%` of host write baseline | 压力档写路径已经很接近本机顺序写参考 |
| `large_read_range` | `1041.87 MiB/s`, `p50 2.877622s` | `10.00%` of host read baseline | 仍未达到 `>= 1800 MiB/s` hard target |
| `hf_hub_download_cold` | `449.78 MiB/s`, `p50 5.910967s` | `4.32%` of host read baseline | 512 MiB 冷下载仍是压力档热点 |
| `hf_hub_download_warm` | `1127753.30 MiB/s`, `p50 6.048054s` | `108.29x` of host read baseline | warm path 只需继续看“不回退” |
| `cache_heavy_warm_download` | `72234.76 MiB/s`, `p50 0.737435s` | `6.94x` of host read baseline | pressure warm 路径也已完成收敛 |

## 当前 memory 快照

目前 memory 观察不是独立类别得分，而是对关键场景的横切观察层。当前 `standard/full` 关键场景的 memory snapshot 如下：

| scenario | peak RSS | peak RSS over baseline | peak traced heap | retained RSS delta | retained traced heap | note |
| --- | --- | --- | --- | --- | --- | --- |
| `host_io_read_baseline` | `54.25 MiB` | `16.94 MiB` | `16.01 MiB` | `1.07 MiB` | `0.01 MiB` | host 顺序读本身就会拉起一部分 working set |
| `large_read_range` | `74.94 MiB` | `37.52 MiB` | `36.54 MiB` | `15.40 MiB` | `0.19 MiB` | 首读 fast path 会拉起 bounded cache，但 Python retained 很低 |
| `hf_hub_download_cold` | `85.96 MiB` | `48.57 MiB` | `48.25 MiB` | `36.63 MiB` | `0.21 MiB` | 冷下载的 retained RSS 更像 detached view / allocator / page cache 保留 |
| `hf_hub_download_warm` | `86.97 MiB` | `49.54 MiB` | `48.22 MiB` | `1.70 MiB` | `0.21 MiB` | warm 路径不再留下明显额外 resident footprint |
| `cache_heavy_warm_download` | `118.03 MiB` | `80.87 MiB` | `80.27 MiB` | `66.00 MiB` | `0.22 MiB` | process RSS 保留明显，但 traced heap 仍接近常数级 |
| `history_deep_listing` | `41.46 MiB` | `4.03 MiB` | `3.53 MiB` | `3.72 MiB` | `2.70 MiB` | metadata-heavy 当前 retained traced heap 最高，但仍停留在 MiB 级 |
| `verify_heavy_full_verify` | `118.76 MiB` | `81.45 MiB` | `80.32 MiB` | `33.75 MiB` | `0.23 MiB` | verify-heavy 已不再留下显著 Python heap 残留 |

`pressure` memory 也要单独看，因为大对象 detached materialization 会把 resident footprint 拉得更高：

| scenario | peak RSS | peak RSS over baseline | peak traced heap | retained RSS delta | retained traced heap |
| --- | --- | --- | --- | --- | --- |
| `large_read_range` | `1574.44 MiB` | `1537.14 MiB` | `1599.99 MiB` | `1.68 MiB` | `0.19 MiB` |
| `hf_hub_download_cold` | `1651.92 MiB` | `1613.61 MiB` | `1599.99 MiB` | `77.88 MiB` | `0.22 MiB` |
| `hf_hub_download_warm` | `1651.92 MiB` | `1613.75 MiB` | `1600.00 MiB` | `78.16 MiB` | `0.22 MiB` |
| `cache_heavy_warm_download` | `210.04 MiB` | `172.81 MiB` | `160.28 MiB` | `34.40 MiB` | `0.23 MiB` |

这说明当前 memory 风险更像“压力档大对象路径会显著拉起峰值 resident / working set”，而不是“Python heap 或对象缓存在每轮后持续线性增长”。

### repeated memory stability spot-check

为了避免只看单次 peak 就误判成泄漏，当前又补了一轮同一进程 repeated spot-check：

| scenario | repeat count | RSS first -> last | traced current first -> last | current judgment |
| --- | --- | --- | --- | --- |
| `large_read_range()` | `8` | `63.33 -> 63.46 MiB` | `1.0101 -> 1.0136 MiB` | 只有 `~0.12 MiB` RSS 与 `~0.0035 MiB` traced 漂移，没有持续线性上升 |
| warm `hf_hub_download()` | `8` | `87.74 -> 87.74 MiB` | `0.0024 -> 0.0039 MiB` | RSS 完全持平，traced current 只增加 `~0.0015 MiB` |
| `verify_heavy_full_verify()` | `5` | `98.68 -> 98.78 MiB` | `0.0125 -> 0.0148 MiB` | verify 重复执行同样没有出现明显膨胀 |

## 输入前提

Phase 13 不单独创造“新热点”，而是依赖下面这些前提：

- Phase 12 已产出带 bandwidth / metadata / amplification / stability 分榜的 benchmark 结果
- 每个候选热点都已经有同机同配置的 baseline / candidate 对比
- 至少一轮 `cProfile`、`py-spy` 或 opt-in `tracemalloc` 画像已经落地
- 当前公开语义、磁盘协议、rollback-only 恢复语义和 detached view 语义不再允许为追性能而漂移

如果这些输入不成立，Phase 13 默认不开始真正的实现优化。

## 当前已知候选热点

根据当前最新的 `standard/full` 与 `pressure/pressure` 结果，当前最值得继续盯的路径已经改成：

- `history_deep_listing` / `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`
  `history_deep_listing` 当前虽然已经提升到 `14714.14 ops/s`，但 `wall_clock_seconds` 仍是 `4.317284s`，13B 的 object payload / public oid / reflog parse cache 仍然必须做。
- `pressure` 档 `read_range()`
  `large_read_range` 在 `standard` 已过线，但 `pressure` 仍只有 `1041.87 MiB/s`，说明 32 MiB 范围读和大 chunk working set 仍有进一步压缩空间。
- pressure 冷 `hf_hub_download()`
  `standard` cold download 已达 `712.84 MiB/s`，但 `pressure` 512 MiB 冷下载仍只有 `449.78 MiB/s`，当前仍被大对象 truth read + detached materialization 拖住。
- memory / resident footprint follow-up
  bounded cache 已经防住“无限膨胀”方向的明显信号，但 pressure 大对象路径会拉起 `1.5-1.6 GiB` 级 peak RSS / traced heap，后续如果继续冲 pressure 指标，就必须把 resident footprint 一起看。
- merge-heavy second-order follow-up
  `merge_heavy_non_fast_forward` 当前 p50 继续改善，但 throughput 低于 `9b5e140`；在 metadata cache 做完前，它仍不应抢占 `history_deep_listing` 或 pressure read-path 的优先级。

## 为什么 Phase 13 必须把读路径当成主战场

当前结论已经更细分：

- `standard` 档读路径第一矛盾基本已经解除，`read_range()` 与 cold `hf_hub_download()` 都已跨过 hard target。
- 当前真正最落后的，是 `pressure` 档大对象读路径和 metadata-heavy wall-clock。
- warm download 继续退出主战场，更多转入“监控不回退”的长期回归项。

| scenario | standard throughput | pressure throughput | same-machine ratio | interpretation |
| --- | ---: | ---: | ---: | --- |
| `large_upload` | `212.212849 MiB/s` | `349.255377 MiB/s` | `59.28%` / `92.77%` of host write baseline | 写路径不是当前第一优先级，pressure 下甚至已逼近本机顺序写 |
| `large_read_range` | `1628.664495 MiB/s` | `1041.870157 MiB/s` | `16.22%` / `10.00%` of host read baseline | standard 已打通，pressure 仍是当前核心未解项 |
| `hf_hub_download_cold` | `712.843056 MiB/s` | `449.779722 MiB/s` | `7.10%` / `4.32%` of host read baseline | standard 已达标，但 pressure 大对象冷物化仍重 |
| `hf_hub_download_warm` | `30075.187970 MiB/s` | `1127753.303965 MiB/s` | `299.44%` / `108.29x` of host read baseline | warm path 已完全退出主战场 |
| `cache_heavy_warm_download` | `37558.685446 MiB/s` | `72234.762980 MiB/s` | `373.94%` / `6.94x` of host read baseline | cache-heavy warm 也只需做“不回退”监控 |
| `mixed_model_snapshot` | `778.699808 MiB/s` | `-` | `7.75%` of host read baseline | mixed-model cold snapshot 已明显提升，但仍可继续吃 metadata / materialization 收敛收益 |
| `history_deep_listing` | `14714.141301 ops/s` | `-` | `wall 4.317284s` | 当前最应该进入 13B 的 metadata-heavy 路径 |

这意味着 Phase 13 的优化原则必须很明确：

1. 先补 metadata-heavy 的 object payload / public oid / reflog parse cache，把 `history_deep_listing` 往 `<= 3.2s` 压。
2. 再继续收敛 `pressure` 档 `read_range()` 与大对象冷 materialization path，并同步观察 resident footprint。
3. warm path、verify-heavy 和空间侧都转入“保持不回退”的回归监控，而不是继续当第一优先级实现面。

## 当前实现状态与仍未解决的问题

在 `cb030e0` 上，Phase 13 当前更准确的描述已经变成：

- standard read-range / cold download / verify-heavy 的主要回退已经被处理掉
- metadata-heavy 还没有进入真正的 cache pass
- pressure 大对象读路径仍然明显落后于目标
- memory 结果已经可观测，但 resident footprint 优化还没有进入实现

| area | current state on `cb030e0` | remaining waste / bottleneck |
| --- | --- | --- |
| 单文件读取路径 | direct path resolver 仍然成立，并且刚写完立刻首读已经新增 recent object payload cache | snapshot flatten 型浪费已被清掉，剩余成本转移到 metadata-heavy 与 pressure object path |
| chunked range read | bounded recent chunk cache + staged seeding + signature validation 已经让 `standard` read-range 过线 | pressure 32 MiB 范围读仍然要承担大 chunk resident footprint 与 copy 成本 |
| warm `hf_hub_download()` | managed-view metadata 命中时继续直接返回现有 detached view | 已基本收敛，只需监控不回退 |
| cold `hf_hub_download()` | standard 已达到 `712.84 MiB/s`，cache amplification 维持在 `~1.00x` | pressure 512 MiB 冷下载仍被大对象 truth read + detached write 拖慢 |
| `snapshot_download()` | quick return / selective repair 已稳固，mixed-model snapshot 继续抬升 | 冷 snapshot 仍然会吃到 metadata / materialization 成本，但优先级已落后于 history-heavy |
| 深历史枚举 | object payload / public oid / reflog parse cache 仍未做 | `history_deep_listing` 继续被重复 payload 读取、public oid 计算和时间解析拖慢 |
| merge-heavy | latency 继续改善，但吞吐低于上一轮 | 如果还要继续优化，必须先确认 metadata cache 后是否还值得挖 |
| verify-heavy | `full_verify()` 共享 chunk context 与对象去重已经落地，吞吐大幅高于上一轮和 Phase 12 | 当前已退出风险列表，只保留不回退监控 |

## 当前已有的函数级证据

为了避免继续停留在“看 benchmark 猜哪里慢”，当前仍然沿用 `build/profiling/phase13/` 下的 `cProfile` 证据，并结合这轮新的 targeted timing 结论来做判断：

### `read_range()` quick profile

artifact:
`build/profiling/phase13/read_range_standard.prof`

当前最显著的累计热点是：

- `_read_chunked_file_range()`
- `_sha256_hex()` / OpenSSL `sha256`
- `_read_pack_range_cached()`

这批证据配合这轮 targeted timing 已经说明：

- “先 flatten 全 snapshot”“每个 chunk 都单独 lookup / reopen pack” 这类明显浪费已经被扫掉
- 新一轮收益主要来自 first-read recent chunk/object cache，而不是继续压 pack checksum 本身
- 当前更需要继续看的，是 pressure 范围读上的大对象 resident / copy 成本，而不是 standard 1 MiB 范围读

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

这说明深历史枚举的问题仍然非常明确：metadata cache pass 还没做，所以 payload 读取、public oid 计算和时间解析仍在重复付费。

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

| priority | area | current state on `cb030e0` | next direction | expected payoff | risk |
| --- | --- | --- | --- | --- | --- |
| P0 | metadata-heavy | `history_deep_listing` 已从 `7204.14 -> 14714.14 ops/s`，但 wall-clock 仍有 `4.317284s` | object payload cache、public oid cache、reflog parse cache | 最直接对应 `<= 3.2s` 目标 | 低 |
| P0 | `pressure` `read_range()` | `standard` 已过 stretch target，但 `pressure` 仍只有 `1041.87 MiB/s` | 优先压 32 MiB 范围读的 copy / resident footprint；收益不足时再看 `pread` / `mmap` | 这是当前最明确的“离目标还远”的读路径项 | 中 |
| P0 | pressure cold `hf_hub_download()` | `standard` cold 已过线，但 `pressure` 512 MiB 冷下载仍只有 `449.78 MiB/s` | lower-copy truth read、detached materialization bookkeeping、resident footprint 收敛 | 这是当前 pressure 下载面主要缺口 | 中 |
| P1 | memory / resident footprint | bounded cache 与 repeated spot-check 已经说明没有明显线性泄漏，但 pressure 大对象路径峰值 working set 很高 | 继续把 memory 结果和 throughput 一起看，必要时优先优化 pressure 大对象 path 的 resident footprint | 能减少“吞吐换内存”的疑虑 | 低到中 |
| P1 | merge-heavy | p50 已继续改善，但 throughput 比 `9b5e140` 低 | metadata cache 做完后再决定是否值得补 ancestry / file identity cache | 收益可能存在，但不应抢在 metadata-heavy 和 pressure 之前 | 中 |
| P2 | OS-specific I/O experiments | 仍未进入实现；当前只在 pressure 目标继续卡住时考虑 | `pread` / `mmap` 必须保留 Windows / Python 3.7 fallback，不能进入默认正确性语义 | 可能是 pressure 读路径最终进一步逼近 host baseline 的必要手段 | 中到高 |

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

### Phase 13A: 已完成的 standard 读路径与 verify-heavy 收敛

这一批已经完成的目标包括：

- `read_range()`
- warm `hf_hub_download()`
- cold `hf_hub_download()`
- `snapshot_download()`
- `verify_heavy_full_verify`
- benchmark memory observation

这轮已经落地并验证收益的优化包括：

- direct path resolver，去掉单文件读前的 full snapshot flatten
- `read_range()` bounded recent chunk cache、staged-first seeding 与 pack/index signature validation
- recent object payload cache，降低“刚写完立刻首读”的 commit/tree/file 路径成本
- warm managed-view metadata fast path
- `_materialize_content_pool()` unchanged no-op fast path
- 调用级 manifest/segment/pack reader cache
- `snapshot_download()` quick return + selective repair
- `full_verify()` 共享 chunk context、对象去重与 chunked file 增量哈希
- 独立 memory probe 子进程与 repeated stability spot-check

当前仍留在 13A 尾部、但还没有完成的只有一个明确项：

- `_ensure_detached_view()` sidecar/metadata-first fast path；它不会影响当前 standard hard target 是否达成，但会影响 pressure 冷 materialization 和 repair path 的额外全文件重哈希成本

### Phase 13B: metadata-heavy cache pass

下一批优先解决：

- `history_deep_listing`
- `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`
- `merge_heavy_non_fast_forward`

首批必须落地的优化：

- object payload cache
- public oid cache
- reflog parse cache
- 非富文本路径下减少不必要的时间解析和对象重读
- merge-base / ancestry cache 只在 metadata-heavy 收敛后再补第二轮

### Phase 13C: pressure 大对象读路径与 resident footprint 收敛

这一批只在 13B 做完后继续推进，重点关注：

- `pressure` `large_read_range()`
- `pressure` cold `hf_hub_download()`
- `_ensure_detached_view()` repair path
- resident footprint / retained RSS 观察

低风险方向优先是：

- 降低 32 MiB 范围读的额外 copy 与重复 layout ensure 成本
- 压缩大对象 detached materialization 的 bookkeeping / 重哈希开销
- 把 throughput、peak RSS、retained RSS 一起看，而不是只追吞吐

只有在这些低风险方向收益不足时，才继续评估：

- `pread`
- `mmap`
- 更低 copy 的 pack read path

这些实验都必须保留跨平台 fallback，不能把 Windows / Python 3.7 兼容性当作可牺牲项，也不能破坏当前 rollback / detached view 语义。

## 性能与内存验收目标

Phase 13 需要的是“很大的提速”，不能只接受几个百分点的微调。因此验收要按 hard target 和 stretch target 双层来写。

### 吞吐 / wall-clock 目标

| scenario | current (`cb030e0`) | Phase 13 hard target | stretch target | status | note |
| --- | --- | --- | --- | --- | --- |
| `large_read_range` standard | `1628.664495 MiB/s` | `>= 800 MiB/s` | `>= 1500 MiB/s` | 已达成 stretch | standard 读路径主矛盾已解除 |
| `large_read_range` pressure | `1041.870157 MiB/s` | `>= 1800 MiB/s` | `>= 2500 MiB/s` | 未达成 | 当前最明确的压力档吞吐缺口 |
| `hf_hub_download_warm` standard | `30075.187970 MiB/s` | `>= 900 MiB/s` | `>= 1500 MiB/s` | 已达成 stretch | 只需继续监控不回退 |
| `hf_hub_download_cold` standard | `712.843056 MiB/s` | `>= 600 MiB/s` | `>= 1000 MiB/s` | 已达成 hard | standard 冷下载已过线，但仍未到 stretch |
| `hf_hub_download_cold` pressure | `449.779722 MiB/s` | `>= 600 MiB/s` | `>= 900 MiB/s` | 未达成 | 512 MiB 冷下载仍是 pressure 热点 |
| `cache_heavy_warm_download` standard | `37558.685446 MiB/s` | `>= 900 MiB/s` | `>= 1400 MiB/s` | 已达成 stretch | 当前不再是风险路径 |
| `history_deep_listing` wall-clock | `4.317284 s` | `<= 3.2 s` | `<= 2.5 s` | 未达成 | 13B metadata cache 仍必须做 |
| `verify_heavy_full_verify` | `739.340365 MiB/s`, `p50 0.526066s` | 清除 compare alert 且显著高于 Phase 12 | 持续稳定不回退 | 已达成 | verify-heavy 已退出当前风险列表 |

### 内存 / 安全护栏

Memory 这里先定义 guardrail，而不是拍脑袋给跨机器绝对 RSS 排名。

| guardrail | current (`cb030e0`) | status | note |
| --- | --- | --- | --- |
| benchmark summary 记录 `peak_rss_bytes` / `peak_rss_over_baseline_bytes` / `retained_rss_delta_bytes` / `peak_traced_bytes` / `retained_traced_bytes` | 已记录到关键读/校验场景 | 已达成 | timing 与 memory probe 已隔离执行 |
| repeated memory spot-check 没有明显持续单调增长 | `large_read_range()`、warm `hf_hub_download()`、`verify_heavy_full_verify()` 都只见极小漂移 | 已达成 | 当前更像 bounded cache / allocator 保留，不像线性泄漏 |
| 新增 cache 有显式上界 | recent chunk cache `64 MiB`；recent object payload cache `256` entries | 已达成 | 防止缓存无限膨胀 |
| pressure 大对象路径的 peak / retained resident footprint 继续收敛 | `large_read_range` / cold download 仍会拉起 `1.5-1.6 GiB` 级 peak RSS / traced heap | 未达成 | 这是 13C 需要继续压的内存侧问题 |

这些目标故意写得偏激进，因为当前读侧与写侧的差距已经足够大，Phase 13 不应该再满足于“局部微调但用户几乎无感”的收益。

## 优化顺序

Phase 13 的优化顺序固定如下：

1. 先完成 metadata-heavy cache pass，优先验证 `history_deep_listing`、`list_repo_commits()`、`list_repo_refs()`、`list_repo_reflog()` 的 wall-clock 收敛空间。
2. 再用 profiling 确认函数级成本，不凭代码直觉改。
3. 然后继续收敛 `pressure` 档 `read_range()`、cold `hf_hub_download()` 与 `_ensure_detached_view()` repair path，并同步看 resident footprint。
4. 每轮改动后重跑同一批 standard/full + pressure/pressure benchmark，记录收益、回退和 memory 观察。
5. 如果热点无法在零协议风险优化内显著改善，再决定是否进入 `pread` / `mmap` 这类更重的实现调整。

## 零协议风险优化优先级

Phase 13 默认优先考虑下面这些不改变公开行为和磁盘协议的优化：

- `_ensure_detached_view()` 的 sidecar/metadata-first fast path，优先避免 repair path 下的全文件重哈希
- pressure 大对象读路径里的 lower-copy chunk 拼装、重复 layout ensure 收敛与大对象 working-set 压缩
- 深历史遍历里的 object payload / public oid / reflog parse 调用级缓存
- `merge()` 路径的 merge-base、commit/tree 解析缓存，避免一次公开调用内重复反序列化
- `full_verify()` / `quick_verify()` / `gc()` 的目录扫描与 pack/index manifest 复用

这些优化都应限定在单次公开调用或有明确文件版本保护的短时 cache 范围内，不引入进程级全局真相状态。

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

- `standard` 档 `read_range()`、warm/cold `hf_hub_download()`、`snapshot_download()` 已完成 benchmark + profiling + 优化闭环，并把收益写回 compare 与计划文档
- `verify_heavy_full_verify` 的 compare alert 已被清除，且 memory 观察已进入 benchmark 摘要
- metadata-heavy 路径至少完成一轮 benchmark + profiling + cache 收敛闭环，并把 `history_deep_listing` 的 wall-clock 明确压低或明确写出停止理由
- `pressure` 档 `large_read_range()` 与 cold `hf_hub_download()` 至少再完成一轮 benchmark + profiling + optimize + benchmark 闭环
- 所有收益、回退和 memory 代价都能回写到 benchmark compare 报告和计划文档里，而不是只体现在 commit message 里

## Deferred Items

下面这些内容明确不属于 Phase 13 MVP：

- 新的默认存储格式或新的公开兼容层
- 以压缩或新协议替代当前主线实现
- 大规模重写 benchmark harness 本身
- 为所有热点一口气做并行复杂优化而缺少逐项归因

## Todo

* [x] 记录 `cb030e0` 的 benchmark anchor commit、standard/full + pressure/pressure artifacts，以及与 `26a1987` / `9b5e140` 的 compare 产物，保证结果可复现。
* [x] 把 `read_bytes()`、`read_range()`、`hf_hub_download()` 从 `_snapshot_for_revision()` 单文件读路径上拆下来，改成 direct path resolver。
* [x] 为 `_read_chunked_file_range()` 增加调用级 manifest/segment cache、batched chunk resolve、pack reader reuse、输出 buffer 收敛，以及 bounded recent chunk cache。
* [x] 为 commit/tree/file JSON 读取增加 recent object payload cache，降低“刚写完立刻首读”的 path resolver 成本。
* [x] 为 warm `hf_hub_download()` 增加 managed-view metadata fast path，命中时禁止 repo re-read、detached re-hash 和 unchanged metadata rewrite。
* [x] 为 `snapshot_download()` 增加 `commit_id + pattern set` 级 quick return 和 selective repair。
* [x] 为 `full_verify()` 增加共享 chunk context、对象去重与 chunked file 增量哈希，清除 verify-heavy compare alert。
* [x] 为关键读/校验路径固定 profiling 命令、输入 shape 与产物保存位置，统一放在 `build/profiling/phase13/`。
* [x] 为 benchmark runner 增加独立 memory probe 子进程，并补 repeated memory stability spot-check。
* [ ] 为 `_ensure_detached_view()` 增加 sidecar/metadata-first fast path，减少 cold/warm repair path 的全文件重哈希。
* [ ] 为 `list_repo_commits()`、`list_repo_refs()`、`list_repo_reflog()` 增加调用级 object payload cache。
* [ ] 为 `list_repo_commits()`、`list_repo_refs()`、`list_repo_reflog()` 增加调用级 public commit/tree oid cache。
* [ ] 为 `list_repo_reflog()` 增加调用级或短时受保护的 reflog parse cache。
* [ ] 为 `merge_heavy_non_fast_forward` 增加 merge-base / ancestor distance cache，并在 metadata pass 后再判断是否继续扩展 file identity cache。
* [ ] 在 `pressure` 档继续收敛 `large_read_range()` 的 copy / resident footprint 成本，并复跑 standard/full + pressure/pressure benchmark。
* [ ] 在 `pressure` 档继续收敛 cold `hf_hub_download()` 的 truth read / detached materialization 成本，并复跑 standard/full + pressure/pressure benchmark。
* [ ] 如果 13B / 13C 的低风险优化收益仍不足，再评估 `pread` / `mmap` / 更低 copy pack read path，并明确 fallback 与兼容性边界。
* [ ] 如果某个方向收益不足或代价过高，就在文档里明确停止，而不是继续堆复杂度。

## Checklist

* [x] 每项优化都能追溯到一个具体的 benchmark 场景和 profiling 证据。
* [x] 所有优化都保持公开语义、磁盘协议和恢复语义不变。
* [x] `cb030e0` 的 benchmark 结果已经把 Phase 12 baseline、上一轮 Phase 13 checkpoint 和当前结果放在同一组对比表里。
* [x] `large_read_range` 在 `standard` 档达到 `>= 800 MiB/s`。
* [x] `large_read_range` 在 `standard` 档达到 `>= 1500 MiB/s` stretch target。
* [ ] `large_read_range` 在 `pressure` 档达到 `>= 1800 MiB/s`。
* [x] `hf_hub_download_warm` 在 `standard` 档达到 `>= 900 MiB/s`。
* [x] `hf_hub_download_cold` 在 `standard` 档达到 `>= 600 MiB/s`。
* [ ] `hf_hub_download_cold` 在 `standard` 档达到 `>= 1000 MiB/s` stretch target。
* [ ] `hf_hub_download_cold` 在 `pressure` 档达到 `>= 600 MiB/s`。
* [x] `cache_heavy_warm_download` 在 `standard` 档达到 `>= 900 MiB/s`。
* [ ] `history_deep_listing` 的 `wall_clock_seconds` 降到 `<= 3.2s`。
* [x] `verify_heavy_full_verify` 已清除 compare alert，并回到显著高于 Phase 12 基线的吞吐区间。
* [x] `read_range()` 与 warm/cold `hf_hub_download()` 至少已有两条路径获得 `2x` 级别以上的稳定收益，且没有把写路径和空间放大重新打坏。
* [x] 回归结果不只写“变快了”，而是明确写出收益比例、相对 host I/O reference 的变化、残余风险和未解决点。
* [x] `peak_rss_bytes` / `peak_rss_over_baseline_bytes` / `retained_rss_delta_bytes` / `peak_traced_bytes` / `retained_traced_bytes` 已进入 benchmark 摘要。
* [x] repeated memory stability spot-check 没有出现明显持续单调增长。
* [x] 新增 cache 具备显式上界：recent chunk cache `64 MiB`，recent object payload cache `256` entries。
* [ ] pressure 大对象路径的 peak / retained resident footprint 已经过下一轮优化重新测量并出现明确收敛。
* [ ] 如果某个优化方向收益不足，就明确停止，不继续堆复杂度。
