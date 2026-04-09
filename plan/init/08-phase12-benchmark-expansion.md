# 08. Phase 12 Benchmark 扩容与指标固化

## Goal

在 Phase 9 已建立 baseline、Phase 10 已完成首轮 A/B 对比的前提下，把 `hubvault` 的 benchmark 体系从“能回答当前瓶颈”扩成“可长期决策、可解释、可比较、可回归”的完整性能基线。

## Status

已完成。

## 为什么还需要 Phase 12

Phase 9 和 Phase 10 已经回答了两个最重要的问题：

- 当前本地仓库路径的大文件吞吐和空间行为大体可接受
- `fastcdc + blake3 + 写时 reuse` 确实解决了写后立刻膨胀与 shifted overlap 复用失效这两个核心问题

但当前 benchmark 仍然主要是“围绕已知问题打点”的定向体系，还没有完全升级成长期回归用的通用性能合同。当前缺口主要包括：

- metadata-heavy 场景仍缺统一的 `operations/s` 与 tail latency 口径
- mixed-model / nested-small / deep-history 这类更接近日常仓库形状的数据集还不够完整
- amplification 指标目前已经有原型，但还没有全部统一到稳定命名与固定定义
- benchmark 结果还没有明确拆成 bandwidth、metadata、maintenance、amplification、stability 几类长期分榜
- cache / memory footprint 还缺统一的 peak / retained 口径，难以直接回答“有没有无限膨胀风险”
- 环境元数据、产物命名和 compare 规则还可以更标准化

因此，Phase 12 的目标不是“继续做性能优化”，而是先把“如何衡量性能”这件事补完整。

## 外部参考口径

Phase 12 的指标定义不会只根据仓库当前已有字段拍脑袋命名，而是明确参考下列常见、公开且相对稳定的 benchmark 口径：

- [`pytest-benchmark`](https://pytest-benchmark.readthedocs.io/)
  作为 Python 层 benchmark harness 的主计时框架。其 calibration、pedantic、autosave / compare 和 machine info 机制适合本仓库这种公开 API 驱动、兼顾 micro 与 workflow 场景的 benchmark 体系。
- [Python `tracemalloc` documentation](https://docs.python.org/3/library/tracemalloc.html)
  提供 `get_traced_memory()` 的 current / peak traced Python heap 口径，适合观察“操作期间峰值 Python heap”和“显式 `gc.collect()` 之后仍保留的 Python 分配”。
- [Linux `/proc/<pid>/status` (`VmRSS` / `VmHWM`)](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
  公开定义了当前 resident set 与 peak resident set high-water mark 的含义。Phase 12 的 memory 观察会借用这一类 OS resident / working-set 口径，而不是只看 Python heap。
- [`fio`](https://fio.readthedocs.io/en/master/fio_doc.html)
  作为存储 benchmark 的常见基线，强调 bandwidth、IOPS、latency percentiles 与带宽/IOPS 波动统计。Phase 12 会借用这些指标族，但只在适合 `hubvault` 这一应用层仓库语义的路径上落地。
- [`IOR` / `mdtest`](https://ior.readthedocs.io/en/latest/intro.html)
  IOR 面向 bulk IO 吞吐，mdtest 面向 metadata peak rates。它们共同说明“带宽型工作负载”和“metadata 型工作负载”不应混成一个总分。
- [`IO500`](https://io500.org/the-lists)
  IO500 公开维护 `overall`、`bandwidth only` 与 `metadata only` 等分榜，这进一步支持本仓库 benchmark 不应压缩成单一总分，而应至少区分 bandwidth 与 metadata 两条主轴。
- [RocksDB amplification definitions](https://github.com/facebook/rocksdb/wiki/RocksDB-Tuning-Guide)
  RocksDB 把 read / write / space amplification 当作独立性能维度来讨论。`hubvault` 不是 LSM，但对“物理读写量 / 逻辑用户量”的放大关系同样成立，因此会借用 amplification 这一维度的定义方式。

这些参考只提供 metric family 与 interpretation 的通用框架，不会改变 `hubvault` 自身的公开 API 语义、磁盘协议或仓库模型。

## Scope Principles

Phase 12 的 benchmark 扩容必须遵守下面这些边界：

- benchmark 仍只通过公开 API / 公开 CLI 驱动，不借助 private / protected 入口测“内部函数体感速度”
- 指标定义优先服务于 `hubvault` 的真实用户路径，而不是追求和低层 block benchmark 一字不差
- 正式结论优先看同机同配置下的相对对比，不用跨机器的绝对毫秒数直接下结论
- 不把高噪声场景强行设为 PR 门禁，先记录趋势，等数据稳定后再考虑阈值
- 区分 wall-clock 与 operation-seconds，避免把初始化、fixture、预热、目录搭建和真实操作本体混在一起
- 区分 logical bytes、live logical bytes、unique logical bytes 与 physical bytes，避免 amplification 分母被混用
- 区分 peak RSS / retained RSS / peak traced heap / retained traced heap，避免把“瞬时峰值”和“疑似泄漏残留”混成一个 memory 数字
- cold / warm、bandwidth / metadata、bulk / workflow、benchmark / correctness 这些边界必须全部写清楚

## Metric Families

Phase 12 计划固化的指标至少包括下面五大类。

### 1. Latency

延迟指标主要用于用户可感知的单次 API / CLI 调用。

| 指标 | 定义 | 适用场景 |
| --- | --- | --- |
| `latency_p50_seconds` | 单场景样本延迟的 median | 所有公开 API / CLI benchmark |
| `latency_p95_seconds` | 单场景样本延迟的 p95 | 有足够 rounds 的 standard / nightly benchmark |
| `latency_p99_seconds` | 单场景样本延迟的 p99 | 样本数足够且波动确实重要的场景 |
| `latency_iqr_seconds` | 单场景样本延迟的四分位距 | 观察稳定性与波动 |
| `wall_clock_seconds` | 包含 fixture、repo init、预热与完整 workflow 的总时长 | workflow / end-to-end 场景 |
| `operation_seconds` | 只统计核心公开操作本体的时长 | throughput、ops/s 的分母 |

约束如下：

- 日常结果展示默认以 `p50` 为主，不用 `min` 当结论
- `p95/p99` 只在样本数足够时展示，不为了“有 tail”而造假尾延迟
- 大 workflow 场景同时展示 `wall_clock_seconds` 和 `operation_seconds`，避免把 setup 污染成纯操作延迟

### 2. Throughput / Bandwidth

带宽指标主要用于 bulk data path。

| 指标 | 定义 | 适用场景 |
| --- | --- | --- |
| `throughput_mib_per_sec` | `logical_bytes_processed / operation_seconds` | `upload_file()`、`read_range()`、`hf_hub_download()`、`snapshot_download()` |
| `files_per_sec` | `file_count_processed / operation_seconds` | 批量小文件导出、tree materialization |
| `history_entries_per_sec` | `commit/ref/reflog entries returned / operation_seconds` | 深历史遍历 |

约束如下：

- throughput 的分子默认使用对用户可见的 logical bytes，而不是物理 pack/chunk bytes
- detached view / snapshot 这类场景仍保留额外 physical/cache 指标，但不直接和 logical throughput 混成一个数字
- 对文件树导出这类 mixed path，可以同时展示 `throughput_mib_per_sec` 和 `files_per_sec`

### 3. Metadata Rate

参考 mdtest 与 IO500 的 metadata 口径，Phase 12 会把 metadata-heavy 工作负载作为独立分榜，而不是塞进 bulk throughput。

| 指标 | 定义 | 适用场景 |
| --- | --- | --- |
| `operations_per_sec` | `metadata_operation_count / operation_seconds` | `list_repo_tree()`、`list_repo_files()`、`list_repo_refs()`、`list_repo_commits()`、CLI `status/log/ls-tree` |
| `files_materialized_per_sec` | `files_created_in_detached_view / operation_seconds` | `snapshot_download()`、冷 `hf_hub_download()` |
| `merge_nodes_per_sec` | `merge comparison units / operation_seconds` | `merge()` 的 tree merge / history walk |

这里的重点不是追求“和 mdtest 完全同构”，而是明确分出 `hubvault` 里的 metadata 主工作负载：

- refs / reflog / history 解析
- tree / file info 枚举
- detached view 目录和文件物化
- merge-base / tree merge / commit graph 遍历

### 4. Amplification

Amplification 不再作为“解释性旁注”，而是进入 Phase 12 的正式指标族。

| 指标 | 定义 | 说明 |
| --- | --- | --- |
| `write_amplification` | `physical_repo_bytes_written / logical_user_bytes_committed` | 反映一次提交在仓库内真正新增了多少物理写入 |
| `space_amplification_live` | `live_physical_bytes / live_logical_bytes` | 反映当前 live repo 视角下的物理空间放大 |
| `space_amplification_unique` | `physical_bytes / unique_logical_bytes` | duplicate / overlap 数据集的核心指标 |
| `cache_amplification` | `cache_delta_bytes / logical_bytes_delivered` | detached view / cache 路径的膨胀比例 |
| `read_amplification_repo` | `repo_bytes_loaded_by_hubvault / logical_bytes_returned` | 可选的 repo-layer 读放大，不尝试直接测 OS/device 层真实磁盘读放大 |

额外约束：

- `write_amplification` 的分子只统计 repo root 内真实新增或改写的持久化字节，不把临时 fixture 目录算进去
- `space_amplification_live` 与 `space_amplification_unique` 不能混用；duplicate / overlap 场景优先看 unique 口径
- `read_amplification_repo` 默认不是第一阶段硬要求，因为它需要更细的 IO instrumentation；Phase 12 先把定义写清楚并允许 opt-in 实验

### 5. Memory / Resident Footprint

Memory 不进入单一总分，但必须进入长期 benchmark 结果，否则缓存和短时对象优化很难回答“有没有把吞吐换成潜在内存膨胀”。

| 指标 | 定义 | 用途 |
| --- | --- | --- |
| `peak_rss_bytes` | 独立 memory probe 子进程在场景执行期间观察到的 peak resident set / working set | 观察整个进程的峰值常驻内存 |
| `peak_rss_over_baseline_bytes` | `peak_rss_bytes - probe_start_rss_bytes` | 看该场景相对空闲基线额外拉起了多少 resident memory |
| `retained_rss_delta_bytes` | `probe_end_rss_bytes - probe_start_rss_bytes` | 粗看场景结束后进程是否留下明显 resident footprint |
| `peak_traced_bytes` | `tracemalloc` 在场景执行期间观测到的 peak traced Python heap | 观察 Python-managed heap 峰值 |
| `retained_traced_bytes` | 显式 `gc.collect()` 后 `tracemalloc` current traced bytes | 观察 Python heap 是否留下持续残留 |

约束如下：

- memory probe 必须与正式 timing 隔离，在独立子进程里执行，不能把 `tracemalloc` 或 RSS 采样直接混进正常 latency / throughput 计时
- `peak_rss_bytes` / `retained_rss_delta_bytes` 反映的是整个进程 resident footprint，不能直接等同于 Python 对象量
- `peak_traced_bytes` / `retained_traced_bytes` 只覆盖 Python-managed heap，不覆盖内核 page cache、mmap working set 或解释器外部分配
- memory 结果默认按场景单独展示，不与 bandwidth / metadata 压成一个合成分数

### 6. Stability / Reproducibility

长期回归除了“快还是慢”，还要看结果是否稳定、可解释。

| 指标 | 定义 | 用途 |
| --- | --- | --- |
| `latency_iqr_seconds` | 延迟 IQR | 看分布收敛程度 |
| `latency_stddev_seconds` | 延迟标准差 | 辅助观察噪声 |
| `throughput_stddev_mib_per_sec` | 吞吐标准差 | 观察吞吐波动 |
| `sample_count` | 样本数 | 判断 percentiles 是否可信 |
| `machine_signature` | Python / OS / arch / runner / filesystem / CPU 基本信息 | 判断比较是否同口径 |

Phase 12 不会为了追求“像系统 benchmark 一样严苛”而在 CI 里尝试清空 page cache 或控制 CPU governor；它只要求同一 runner、同一配置、同一数据集下的结果可比较。Memory probe 也遵守同样原则：保留同机相对观察意义，但不把跨机器绝对 RSS 数字当作排行榜。

## Host IO Reference

Phase 12 额外引入一组 host local sequential I/O reference，用来回答“当前 `hubvault` 的应用层路径距离本机顺序读写上限还有多远”，但它只作为同机相对坐标，不作为跨机器绝对评分。

- `host_io_write_baseline`
  在同一文件系统、同一 Python 进程与同一 benchmark runner 下顺序写入固定大小临时文件，输出 `throughput_mib_per_sec`。
- `host_io_read_baseline`
  对同一类临时文件做顺序读取，输出 `throughput_mib_per_sec`。
- `_vs_write_baseline_ratio` / `_vs_read_baseline_ratio`
  只用于同机、同配置、同批 benchmark 内的相对判断，不做跨机器排名或跨 runner 结论。

额外约束如下：

- 顺序写基线更接近“当前宿主文件系统的持续写带宽参考”，适合对比 `upload_file()`、大文件 commit 等 bulk write path。
- 顺序读基线天然会受到 OS page cache、readahead 与文件系统缓存命中的影响，因此更适合作为“当前实现距本机热读路径还有多远”的参考，不声称代表设备层裸读极限。
- host I/O reference 进入 curated summary、compare 解释和 Phase 13 热点排序，但不直接做 correctness 门禁，也不作为单独的公开 API benchmark 结论。

## Metric Interpretation Rules

为了避免报告里出现“指标看起来很多，但谁都能随口解释”的问题，Phase 12 额外固定下面这些解释规则：

### 不压成单一总分

`hubvault` 的 benchmark 结果至少分成下面几类结果页：

- `bandwidth`
- `metadata`
- `maintenance`
- `amplification`
- `stability`

可以提供简洁摘要，但不生成一个“总性能分”。原因是：

- 大文件吞吐和 metadata 延迟并不是一类瓶颈
- amplification 改善可能伴随局部 latency 回退
- 单一总分会掩盖 shifted overlap、warm download、merge 这类局部热点

### Cold / Warm 明确定义

- `cold`：新建 repo、或新进程、或显式清理 managed cache/detached view 后的首次路径
- `warm`：同一 repo、同一 benchmark 轮次内，允许复用既有 managed cache、visible index、detached view 与 OS 元数据缓存

不额外声称“绝对冷启动”。Phase 12 只定义 benchmark harness 可控制的冷暖语义。

### Wall-clock 与 Operation Time 明确定义

- `wall_clock_seconds` 用于回答“真实用户完整跑完流程用了多久”
- `operation_seconds` 用于回答“核心操作本体的吞吐、ops/s 和 amplification”

两者都要保留，但不能混为同一列。

## Dataset Families

Phase 12 会在当前数据集的基础上，补出下面这组长期可维护的数据集族：

### 已有且继续保留

- `small-tree`
- `large-single`
- `exact-duplicate-live`
- `aligned-overlap-live`
- `shifted-overlap-live`
- `historical-duplicate`
- `maintenance-heavy`
- `pressure-large`
- `pressure-space-live`

### 新增的数据集族

`nested-small`
    多层目录、多文件数的小文件树；主要用于 metadata rate、snapshot tree materialization 和深层目录扫描。

`mixed-model`
    README / config / tokenizer / JSON / TXT 小文件与 1-2 个 32-128 MiB 大文件混合；用于更接近日常模型仓库的工作流 benchmark。

`history-deep`
    固定 128 / 512 / 1024 commit 深度，持续修改有限路径；用于 history walk、reflog、merge-base 与 squash path。

`merge-heavy`
    多分支并行修改、带 shared ancestor 与有限冲突面的仓库；用于 benchmark `merge()` 的非冲突热路径与结构化冲突路径。

`cache-heavy`
    带既有 detached views、managed cache 和多轮下载记录的仓库；用于 warm download、cache amplification 与 view reuse 路径。

`verify-heavy`
    大量 chunk / packs / index segments / refs / logs 并存的仓库；用于 `quick_verify()` / `full_verify()` / `gc()` 的维护成本测量。

## Execution Tiers

Phase 12 固化四档执行层次：

`smoke`
    三平台快速可运行子集，只验证 harness 和结果量级。

`standard`
    本地开发与 PR 后手动 benchmark 的默认档位，覆盖主要 bandwidth / metadata / maintenance 场景。

`nightly`
    Linux 权威 runner 上的完整档位，保留更多 rounds、tail latency、compare 产物与曲线摘要。

`pressure`
    GiB 级别的大文件与空间行为压测，不作为高频 PR 门禁，但保留趋势跟踪。

## Artifact Structure

Phase 12 计划把 benchmark 产物结构统一到下面的层级：

- 原始 `pytest-benchmark` JSON
- curated summary JSON
- compare JSON / Markdown
- 带环境元数据的 run manifest
- 可读性摘要报告，至少分 bandwidth、metadata、maintenance、amplification、stability 五个 section

建议的目录结构：

```text
build/benchmark/
  phase12/
    raw/
    summary/
    compare/
    manifests/
```

## CI Policy

Phase 12 的 CI 策略固定如下：

- Linux x86_64 继续作为权威 benchmark 数值环境
- Windows / macOS 保留 smoke benchmark 与少量 metadata / download sanity benchmark
- `pressure` 默认只在 Linux nightly 或手动 workflow 跑
- compare 结果必须带 machine signature；machine signature 明显不一致时，不自动给出回退结论
- 初期只对少量稳定指标加相对阈值告警，例如 metadata p50 或 bulk throughput 的 15%-20% 回退

## Phase 12 MVP Cut

Phase 12 的 MVP 交付不要求“一步到位把所有 benchmark 理想形态全部落完”。最低可接受交付为：

- 新增 `nested-small`、`mixed-model`、`history-deep` 三组数据集
- benchmark 结果明确拆成 bandwidth / metadata / amplification 三大类
- 指标命名和分母口径写清楚并落到 JSON summary
- Linux nightly 可以产出 machine-tagged compare 报告
- Windows / macOS smoke 仍可运行核心子集

## Deferred Items

下面这些内容明确延后，不作为 Phase 12 MVP：

- 设备级真实磁盘读放大与写放大 tracing
- `perf` / eBPF / ETW 等 OS-specific 低层剖析默认集成
- 把 benchmark 结果做成单一总分排行
- 为所有场景都维护 tail latency 门禁
- 为跨机器比较做绝对值打分

## Execution Record

Phase 12 的实现、完整 benchmark 与计划回写已经完成。为避免“文档提交污染 benchmark 复现点”，本阶段明确把实际 benchmark 的代码锚点固定在提交 `26a198711dc41e1bf2ec091361f4b64543a69210`（短 SHA `26a1987`）；后续文档补记 commit 只负责记录，不改变被测实现。

### Environment

- branch: `main`
- benchmarked commit: `26a198711dc41e1bf2ec091361f4b64543a69210`
- platform: `Linux-6.14.0-33-generic-x86_64-with-glibc2.39`
- python: `CPython 3.10.10`
- executable: `./venv/bin/python`

### Commands Run

- `./venv/bin/python -m compileall tools/benchmark test/benchmark`
- `./venv/bin/python -m tools.benchmark.run_phase9 --scale smoke --rounds 1 --warmup-rounds 0 --scenario-set full --output build/benchmark/phase12/summary/phase12-smoke-full.json --manifest-output build/benchmark/phase12/manifests/phase12-smoke-full-manifest.json`
- `HUBVAULT_BENCHMARK_SCALE=smoke ./venv/bin/python -m pytest test/benchmark -sv -m benchmark --benchmark-only -k "mixed_model_snapshot_download or history_deep_listing_on_branchy_repo or merge_heavy_non_fast_forward_workflow or cache_heavy_warm_download or verify_heavy_full_verify"`
- `make benchmark_phase12_smoke`
- `make benchmark_phase12_standard`
- `make benchmark_phase12_pressure`
- `make benchmark_phase12_compare BENCHMARK_BASELINE=build/benchmark/phase12/raw/autosave/Linux-CPython-3.10-64bit/0002_phase12-standard-full.json BENCHMARK_CANDIDATE=build/benchmark/phase12/raw/autosave/Linux-CPython-3.10-64bit/0003_phase12-standard-full.json BENCHMARK_PHASE12_COMPARE_JSON=build/benchmark/phase12/compare/phase12-standard-0002-vs-0003.json`

### Artifact Paths

- raw standard JSON: `build/benchmark/phase12/raw/pytest-benchmark-standard.json`
- raw autosave baseline: `build/benchmark/phase12/raw/autosave/Linux-CPython-3.10-64bit/0002_phase12-standard-full.json`
- raw autosave candidate: `build/benchmark/phase12/raw/autosave/Linux-CPython-3.10-64bit/0003_phase12-standard-full.json`
- standard summary: `build/benchmark/phase12/summary/phase12-standard-full.json`
- pressure summary: `build/benchmark/phase12/summary/phase12-pressure-pressure.json`
- standard manifest: `build/benchmark/phase12/manifests/phase12-standard-full-manifest.json`
- pressure manifest: `build/benchmark/phase12/manifests/phase12-pressure-pressure-manifest.json`
- compare result: `build/benchmark/phase12/compare/phase12-standard-0002-vs-0003.json`

### Representative Standard Results

| scenario | category | latency_p50_seconds | throughput_mib_per_sec | operations_per_sec | amplification |
| --- | --- | ---: | ---: | ---: | --- |
| `large_upload` | bandwidth | `0.138884` | `208.699282` | `17.391607` | `write_amplification = 1.000414` |
| `large_read_range` | bandwidth | `0.126996` | `223.964166` | `223.964166` | `-` |
| `hf_hub_download_cold` | bandwidth | `0.206108` | `281.802597` | `23.48355` | `cache_amplification = 2.000053` |
| `hf_hub_download_warm` | bandwidth | `0.232882` | `437.556974` | `36.463081` | `cache_amplification = 0.0` |
| `cache_heavy_warm_download` | bandwidth | `0.813272` | `450.894744` | `28.180922` | `cache_amplification = 0.0` |
| `mixed_model_snapshot` | bandwidth | `0.527436` | `228.235579` | `64.15557` | `cache_amplification = 2.000125` |
| `history_deep_listing` | metadata | `4.942012` | `-` | `8157.419516` | `-` |
| `merge_heavy_non_fast_forward` | metadata | `0.441694` | `48.562719` | `476.315225` | `-` |
| `verify_heavy_full_verify` | maintenance | `1.409059` | `43.518142` | `17.660812` | `-` |

`space_amplification_unique_after_gc` 的代表值如下：

| scenario | dataset_family | space_amplification_unique_after_gc |
| --- | --- | ---: |
| `exact_duplicate_live_space` | `exact-duplicate-live` | `1.000001` |
| `aligned_overlap_live_space` | `aligned-overlap-live` | `1.59523` |
| `shifted_overlap_live_space` | `shifted-overlap-live` | `2.984699` |
| `historical_duplicate_space` | `historical-duplicate` | `1.000001` |

host I/O reference 如下：

| metric | value |
| --- | ---: |
| `write_baseline_throughput_mib_per_sec` | `360.815443` |
| `read_baseline_throughput_mib_per_sec` | `10471.204188` |
| `large_upload_vs_write_baseline_ratio` | `0.57841` |
| `large_read_range_vs_read_baseline_ratio` | `0.021389` |
| `hf_hub_download_cold_vs_read_baseline_ratio` | `0.026912` |
| `hf_hub_download_warm_vs_read_baseline_ratio` | `0.041787` |
| `cache_heavy_warm_download_vs_read_baseline_ratio` | `0.04306` |

### Representative Pressure Results

| scenario | category | latency_p50_seconds | throughput_mib_per_sec | operations_per_sec | amplification |
| --- | --- | ---: | ---: | ---: | --- |
| `large_upload` | bandwidth | `3.982752` | `342.373006` | `0.668697` | `write_amplification = 1.000151` |
| `large_read_range` | bandwidth | `2.952265` | `1030.396703` | `32.199897` | `-` |
| `hf_hub_download_cold` | bandwidth | `7.018945` | `271.450559` | `0.530177` | `cache_amplification = 2.000001` |
| `hf_hub_download_warm` | bandwidth | `8.540273` | `349.13463` | `0.681904` | `cache_amplification = 0.0` |
| `cache_heavy_warm_download` | bandwidth | `1.396751` | `377.955732` | `11.811117` | `cache_amplification = 0.0` |

pressure 档的 host I/O reference 如下：

| metric | value |
| --- | ---: |
| `write_baseline_throughput_mib_per_sec` | `366.491509` |
| `read_baseline_throughput_mib_per_sec` | `9954.698345` |
| `large_upload_vs_write_baseline_ratio` | `0.934191` |
| `large_read_range_vs_read_baseline_ratio` | `0.103509` |

pressure 档 `space_amplification_unique_after_gc` 的代表值如下：

| scenario | dataset_family | space_amplification_unique_after_gc |
| --- | --- | ---: |
| `exact_duplicate_live_space` | `exact-duplicate-live` | `1.0` |
| `aligned_overlap_live_space` | `aligned-overlap-live` | `1.006715` |
| `shifted_overlap_live_space` | `shifted-overlap-live` | `1.020428` |
| `historical_duplicate_space` | `historical-duplicate` | `1.0` |

### Compare Conclusion

- `build/benchmark/phase12/compare/phase12-standard-0002-vs-0003.json` 当前 `alerts = 0`
- `same_machine = true`
- `same_config = false`

这里的 `same_config = false` 是当前 raw `pytest-benchmark` autosave JSON 不携带 curated config block 导致的 compare 现象，不代表 benchmark 输入形状真的不一致；Phase 12 的正式回归判断仍应优先使用 curated summary 的 config、dataset shape 与 threshold policy。

### Immediate Phase 13 Priorities

根据当前 Phase 12 结果，下一阶段应按下面顺序推进：

1. `read_range()`、cold/warm `hf_hub_download()`、`snapshot_download()` 的时间路径收敛优先级最高。
   当前它们相对 host 顺序读基线仍只有约 `2%` 到 `4%`，说明主要瓶颈已经不在纯写入，而在 repo-visible index、detached view、目录物化与 metadata 解析链路。
2. `history_deep_listing` 与 `merge_heavy_non_fast_forward` 作为第二优先级。
   它们已经纳入 metadata 分榜，适合直接进入 `cProfile` / `py-spy` 的热点归因，而不是继续靠体感猜测。
3. amplification 路径先保持趋势跟踪，不再作为第一优先级实现面。
   exact duplicate、historical duplicate 已经稳定在 `~1.00x`，pressure 下 aligned / shifted overlap 也已接近唯一数据体积，说明空间主矛盾已经明显弱于时间主矛盾。

## Todo

* [x] 为 `nested-small`、`mixed-model`、`history-deep`、`merge-heavy`、`cache-heavy`、`verify-heavy` 实现确定性数据集生成器。
* [x] 扩展 benchmark harness，让 metadata-heavy 场景输出 `operations_per_sec` 与 tail latency，而不是只有吞吐。
* [x] 扩展 summary schema，加入 `latency_p50/p95/p99`、`latency_iqr`、`operations_per_sec`、`write_amplification`、`space_amplification_live`、`space_amplification_unique`、`cache_amplification` 等字段。
* [x] 为运行结果补 machine signature 与 dataset shape 信息，并确保 compare 工具优先比较同机同配置结果。
* [x] 调整 benchmark workflow，区分 `smoke`、`standard`、`nightly`、`pressure` 四档执行口径。
* [x] 为 bandwidth / metadata / maintenance / amplification / stability 五类结果补独立摘要模板，不再输出单一总分。
* [x] 为 memory / resident footprint 补 `peak_rss_bytes`、`peak_rss_over_baseline_bytes`、`retained_rss_delta_bytes`、`peak_traced_bytes`、`retained_traced_bytes` 五项正式指标，并固定独立 memory probe 执行口径。
* [x] 明确哪些指标进入告警阈值，哪些指标只记录趋势。
* [x] 把 Phase 12 扩容后的 benchmark 入口写回 Makefile、workflow 文档和计划说明。

## Checklist

* [x] 所有新增指标都能明确说明分子、分母和适用场景。
* [x] benchmark summary 不会再把 metadata-heavy 路径塞进 bulk throughput 一列里。
* [x] amplification 指标已经正式进入结果 schema，而不只是人工解读时的辅助描述。
* [x] memory / resident footprint 已进入正式 metric family，并明确和 timing / throughput 隔离执行、单独解释。
* [x] benchmark 结果可以携带足够的环境元数据，支持长期比较和结果复核。
* [x] Linux / Windows / macOS 三平台仍然保持公开 API / 公开 CLI 驱动的 benchmark 入口。
* [x] Phase 12 的产物结构已经能支持后续 Phase 13 做热点排序和回归归因。
