# 07. Phase 9 Benchmark 基线与结论

## 目标

这份文档记录 Phase 9 首轮性能基线的真实执行方式、数据集形状、关键指标和当前已经可以成立的结论。

它不是未来规划，而是当前仓库已经落地并实际跑过的 benchmark 结果说明。后续如果继续补 profiling、优化实验或新增 benchmark 场景，也应继续在这里追记。

## 执行环境

本轮 benchmark 在本地仓库环境下执行，Python 解释器固定为仓库内虚拟环境：

- `./venv/bin/python`
- Python 版本：`3.10.1`

本轮基线的计时与导出工具如下：

- `pytest-benchmark`
- `tools/benchmark/run_phase9.py`
- `tools/benchmark/compare.py`

## 基线锚点提交

当前这套已完成的 Phase 9 benchmark 体系，后续做 Phase 10 技术引入时应以这个提交作为 A/B 对比锚点：

- baseline anchor commit：`edde3cafaaf6f1c99fa4b66912a5b3874132d79d`
- baseline anchor subject：`feat(benchmark): complete phase9 baseline and pressure suite`

后续建议的对比流程固定为：

```bash
git checkout edde3cafaaf6f1c99fa4b66912a5b3874132d79d
make benchmark_phase9_standard
make benchmark_phase9_pressure

git checkout <candidate-commit>
make benchmark_phase9_standard
make benchmark_phase9_pressure

./venv/bin/python -m tools.benchmark.compare \
  build/benchmark/<baseline-json> \
  build/benchmark/<candidate-json>
```

如果后续需要更细的单场景对比，也应沿用同一套 runner / Makefile 入口，不再临时拼脚本。

## 已实际执行的命令

下面这些命令已经实际跑过并产出了结果文件：

```bash
./venv/bin/python -m tools.benchmark.run_phase9 --scale smoke --output build/benchmark/phase9-smoke-summary.json
HUBVAULT_BENCHMARK_SCALE=smoke ./venv/bin/python -m pytest test/benchmark -sv -m benchmark --benchmark-only --benchmark-json=build/benchmark/pytest-benchmark-smoke.json
make benchmark_phase9_standard
make benchmark_phase9_pressure
make unittest
```

## 当前 benchmark 入口

当前 benchmark 代码已经落到以下位置：

- `test/benchmark/test_phase9_small.py`
- `test/benchmark/test_phase9_large.py`
- `test/benchmark/test_phase9_history.py`
- `test/benchmark/test_phase9_maintenance.py`
- `test/benchmark/test_phase9_cli.py`
- `test/benchmark/conftest.py`
- `tools/benchmark/common.py`
- `tools/benchmark/run_phase9.py`
- `tools/benchmark/compare.py`
- `Makefile` 中的 `benchmark` / `benchmark_smoke` / `benchmark_standard` / `benchmark_phase9` / `benchmark_phase9_smoke` / `benchmark_phase9_standard` / `benchmark_phase9_pressure` / `benchmark_compare`
- `.github/workflows/benchmark.yml`

这些 benchmark 当前都只通过公开 API 驱动，不依赖 private / protected 内部实现。

## 数据集形状

当前已落地并实际使用的数据集如下：

### `small-tree`

- 128 个 4 KiB 小文件
- 多目录分组布局
- 用于小文件批量提交、批量读取、冷快照导出

### `large-single`

- 单个 12 MiB chunked 大文件
- 用于大文件上传和 `read_range()` 吞吐测量

### `exact-duplicate-live`

- 6 个完全相同的 12 MiB live 大文件
- 用于衡量“写后立刻”的空间膨胀和 `gc()` 后的物理复用

### `aligned-overlap-live`

- 6 个文件共享 8 MiB 对齐前缀
- 每个文件额外带 1 MiB 独有尾部
- 用于衡量固定大小 chunk 对“边界对齐重叠内容”的复用能力

### `shifted-overlap-live`

- 6 个文件来自同一 base payload
- 每个文件窗口相对前一个按 1 KiB 偏移
- 用于衡量固定大小 chunk 对“错位相似内容”的复用退化

### `historical-duplicate`

- 同一路径连续写入 24 个完全相同的大文件 revision
- 用于衡量历史累积写入时的短期空间膨胀，以及 `gc()` 的最终回收效果

### `maintenance-heavy`

- 多代大文件
- 已包含下载和快照视图痕迹
- 用于测 `full_verify()` 的维护路径成本

### `pressure-large`

- 512 MiB chunked 大文件
- 用于 `benchmark_phase9_pressure` 的大文件读写和 detached view 压测

### `pressure-space-live`

- exact duplicate / aligned overlap / shifted overlap 三组 live set
- 总逻辑体量均在 GiB 级
- 用于压力档位下的空间膨胀与 chunk 复用行为确认

## 样本修正说明

首轮实现中，数据生成器一度会把大文件做成固定 1 MiB 周期重复，这会把“文件内部自重复”误算成“跨文件 chunk 复用”，从而污染 dedup 结论。

当前版本已经修正为：

- 使用全长确定性字节流
- 不再重复拼接同一个 1 MiB 模板块
- 这样 exact duplicate / aligned overlap / shifted overlap 的结论才真正只反映跨文件关系

另外，runner 的吞吐统计也已修正为：

- 保留整场景 wall-clock
- 但 throughput 优先基于真实操作耗时 `operation_seconds`
- 避免把 repo 初始化、预热和环境搭建时间误算进纯读写吞吐

## 标准基线结果

以下数值来自：

```bash
make benchmark_phase9_standard
```

### 时间性能

- 大文件上传：12 MiB `upload_file()` 实测操作耗时约 `0.361s`，吞吐约 `33.20 MiB/s`
- 大文件范围读取：1 MiB `read_range()` 实测操作耗时约 `0.0297s`，吞吐约 `33.66 MiB/s`
- 小文件批量读取：128 个 4 KiB 文件共 512 KiB，实测读取耗时约 `0.703s`，吞吐约 `0.71 MiB/s`
- 冷快照导出：512 KiB 小文件树 `snapshot_download()` 实测操作耗时约 `2.30s`，吞吐约 `0.22 MiB/s`
- 冷 `hf_hub_download()`：12 MiB chunked 文件 detached view 实测操作耗时约 `0.213s`，吞吐约 `56.28 MiB/s`
- warm `hf_hub_download()`：第二次调用缓存增量约 `0`，并复用既有 detached view 路径
- 非快进 `merge()`：实测操作耗时约 `0.0822s`，吞吐约 `24.41 MiB/s`
- `squash_history()`：历史重写 + 跟随 GC 实测操作耗时约 `1.92s`，吞吐约 `6.24 MiB/s`
- `full_verify()`：maintenance-heavy 仓库约 9 MiB live 数据，实测校验耗时约 `4.04s`，吞吐约 `2.23 MiB/s`

### 空间与复用

#### 完全重复 live 大文件

- `chunks.packs` 写后立刻约 `75.50 MiB`
- `gc()` 后约 `12.58 MiB`
- `dedup_gain_after_gc = 6.0x`

这说明：

- 当前没有写时 pack/chunk 物理复用
- 当前 exact duplicate 的长期空间利用率主要依赖 `gc()`

#### 对齐重叠 live 大文件

- `chunks.packs` 从 `56.62 MiB` 降到 `14.68 MiB`
- `dedup_gain_after_gc = 3.86x`
- `physical_over_unique_after_gc ≈ 1.0x`

这说明：

- 只要重叠内容与 chunk 边界对齐
- 当前固定大小 chunk 在 `gc()` 后可以把空间压到接近唯一数据体积

#### 错位重叠 live 大文件

- `chunks.packs` 从 `75.50 MiB` 到 `75.50 MiB` 基本不变
- `dedup_gain_after_gc ≈ 1.0x`
- `physical_over_unique_after_gc ≈ 6.0x`

这说明：

- 固定大小 chunk 对错位相似内容极不友好
- 当前几乎无法复用这种场景下的内容

#### 历史重复写入

- 同一路径连续 24 个相同 revision 时
- `chunks.packs` 从 `301.99 MiB` 降到 `12.58 MiB`
- `dedup_gain_after_gc = 24.0x`

这说明：

- 历史重复写入会在压实前造成非常明显的短期膨胀
- 但最终是可回收的
- 风险主要在“未及时 GC 的中间阶段”，不在最终格式不可回收

## Pressure 压测结果

以下数值来自：

```bash
make benchmark_phase9_pressure
```

这不是日常 baseline，而是专门把总数据量拉到 GiB 级别的压力子集。它只保留最关键的大文件和重复/重叠空间场景，避免把小文件路径也一起放大。

### 时间性能

- 大文件上传：512 MiB `upload_file()` 实测操作耗时约 `6.33s`，吞吐约 `80.93 MiB/s`
- 大文件范围读取：32 MiB `read_range()` 实测操作耗时约 `0.396s`，吞吐约 `80.80 MiB/s`
- 冷 `hf_hub_download()`：512 MiB detached file view 实测操作耗时约 `9.36s`，吞吐约 `54.70 MiB/s`

### 空间与复用

- 完全重复 live 大文件：`chunks.packs` 从约 `1.50 GiB` 降到 `512 MiB`，`dedup_gain_after_gc = 3.0x`
- 对齐重叠 live 大文件：`chunks.packs` 从约 `1.50 GiB` 降到 `768 MiB`，`dedup_gain_after_gc = 2.0x`
- 错位重叠 live 大文件：`chunks.packs` 从约 `1.50 GiB` 降到约 `1.00 GiB`，`dedup_gain_after_gc ≈ 1.49x`
- 冷 `hf_hub_download()` 后缓存增量约 `1.00 GiB`

这说明 pressure 档位已经足以观察真正的 GiB 级行为：

- 大文件读写在 GiB 总量级下仍保持可接受吞吐
- exact duplicate 与 aligned overlap 的长期空间利用率仍健康
- shifted overlap 在 GiB 总量下依然明显差于对齐重叠
- detached view 在大文件下载场景下会带来显著缓存膨胀

## Phase 9 锚点当时可以成立的结论

### 1. 大文件读写速度当前是可接受的

在当前本地路径仓库模型下：

- 大文件上传已经进入几十 MiB/s
- 大文件范围读取也已经进入几十 MiB/s

这说明当前 chunked 大文件路径在单机本地场景下没有明显不可接受的性能问题。

### 2. 小文件和快照路径仍然更慢

和大文件路径相比：

- 小文件批量读取吞吐明显更低
- 冷快照导出也更慢

这说明当前更值得 profiling 的不是单纯大文件 IO，而是：

- 目录遍历
- 元数据解析
- detached view 生成
- 多文件路径下的重复扫描

### 3. 当前没有写时物理复用

exact duplicate live set 在写后立刻几乎线性膨胀，已经明确说明：

- 当前不会在写入当下复用 pack/chunk 实体
- 当前空间优化主要依赖后续 `gc()`

### 4. 对齐重复内容的长期空间利用率是健康的

对 exact duplicate 和 aligned overlap：

- `gc()` 之后都能接近唯一数据体积

这说明当前固定 chunk 方案在“内容相同”或“边界对齐共享”场景里是成立的。

### 5. 错位相似内容是当前最明确的空间短板

shifted overlap 的结果已经说明：

- 一旦重叠内容不与 chunk 边界对齐
- 当前 chunk 方案基本失去复用能力

这也是当前最值得明确记录的结构性短板。

## Phase 9 结束时的优化优先级（历史记录）

基于这轮 benchmark，后续优化优先级已经可以明确：

### 优先级 1：写时复用 / 短期空间膨胀控制

这是最优先的问题，因为它直接决定：

- 大量重复大文件提交时的即时空间占用
- 未及时 `gc()` 时的空间膨胀程度

### 优先级 2：小文件和快照路径的元数据热点

这部分更可能受以下环节影响：

- 重复 ref/commit/tree 解析
- 多文件视图生成
- `stat()` / `glob()` / 目录扫描

### 优先级 3：是否值得引入内容定义分块实验

只有在确认：

- 错位重叠复用确实是高优先级业务问题
- 且写时复用和元数据热点优化后仍然不够

才值得进入 `fastcdc` 一类内容定义分块实验。

## Phase 9 结束时的新技术引入建议（历史记录）

结合当前结果，对前面提到的几类技术建议如下：

### 建议尽快引入

- `blake3`
  最适合先作为内部快速预哈希与重复候选筛查工具进入写路径。它可以服务于写时 chunk/pack reuse，而不需要改变公开 `sha256` / `oid` 语义，收益与风险比最高。
- `cProfile` / `py-spy` / opt-in `tracemalloc`
  这些更适合作为 Phase 10 的分析工具链先落地。当前小文件、快照、历史遍历和 detached view 的热点还需要更细定位，它们能给出下一轮优化的证据。
- 单遍流式 hash+copy 与调用级 metadata cache
  这部分不依赖新的磁盘协议，也不需要改变公开行为，应该和上面的 profiling 一起尽快做掉。

### 建议实验性推进

- `fastcdc`
  它最有希望改善 shifted overlap 的复用退化，但复杂度和格式影响都明显更高。建议只放到实验路径里，等 `blake3` 和写时 reuse 做完后再看是否值得默认化。

### 当前不建议优先引入

- `zstandard`
  当前主要痛点不是最终静态体积，而是写后立刻膨胀与 metadata 热点。现阶段先引入压缩的边际收益不高，还会带来 CPU 与兼容复杂度。

## 后续可继续演进的内容

Phase 9 的核心交付已经完成，但这份文档仍然允许后续继续追记新的长期演进项，例如：

- 更细的 mixed-model / nested-small 数据集
- opt-in `tracemalloc` / Python heap profiling
- 更系统的热点 flamegraph / cProfile 结果
- 更细分的 cache amplification 拆解

## Phase 10 当前候选实现对比

### 候选实现说明

当前候选实现直接默认引入：

- `fastcdc` 内容定义分块
- `blake3` 作为 FastCDC 的快速边界哈希
- 写时 chunk/pack reuse（同事务内 + 跨既有历史）

本轮候选结果仍使用与 Phase 9 相同的命令口径：

```bash
make benchmark_phase9_standard
make benchmark_phase9_pressure
```

对比基线固定为：

- anchor commit：`edde3cafaaf6f1c99fa4b66912a5b3874132d79d`
- anchor subject：`feat(benchmark): complete phase9 baseline and pressure suite`

### Standard 档时间对比

| 场景 | Anchor | Candidate | 变化 | 说明 |
| --- | --- | --- | --- | --- |
| `large_upload` | `33.20 MiB/s` / `0.361s` | `37.16 MiB/s` / `0.323s` | `+11.9%` | 标准档大文件写入更快，说明 FastCDC 规划和写时复用没有拖垮 12 MiB 量级上传。 |
| `large_read_range` | `33.66 MiB/s` / `0.0297s` | `27.36 MiB/s` / `0.0365s` | `-18.7%` | 标准档小范围 range read 出现回退，后续应继续盯 `IndexStore.lookup()` 与逐 chunk 校验。 |
| `small_read_all` | `0.71 MiB/s` / `0.703s` | `0.87 MiB/s` / `0.574s` | `+22.5%` | 小文件全量读取反而更快，说明对象扫描和仓库尺寸收敛对读路径有正反馈。 |
| `snapshot_download_small` | `0.22 MiB/s` / `2.30s` | `0.27 MiB/s` / `1.85s` | `+24.5%` | 小文件快照导出也更快，说明当前改动没有把 detached view 路径变慢。 |
| `hf_hub_download_cold` | `56.28 MiB/s` / `0.213s` | `58.56 MiB/s` / `0.205s` | `+4.1%` | 冷下载小幅变好。 |
| `hf_hub_download_warm` | `77.28 MiB/s` / `0.155s` | `57.56 MiB/s` / `0.208s` | `-25.5%` | warm 路径回退明显，但缓存增量仍保持 `0`；后续要继续盯现有 view 复用链路。 |
| `merge_non_fast_forward` | `24.41 MiB/s` / `0.0822s` | `19.62 MiB/s` / `0.102s` | `-19.7%` | merge 不是本轮主优化面，但已出现可测回退，需要在后续性能 phase 里单独 profiling。 |
| `squash_history` | `6.24 MiB/s` / `1.92s` | `21.33 MiB/s` / `0.563s` | `+241.8%` | 历史重复写入被写时复用消掉后，历史压缩路径显著变轻。 |
| `full_verify` | `2.23 MiB/s` / `4.04s` | `3.08 MiB/s` / `2.93s` | `+38.2%` | 由于重复 pack/索引大幅减少，完整校验路径也直接受益。 |

### Standard 档空间与复用对比

| 场景 | Anchor 写后立刻 pack | Candidate 写后立刻 pack | Anchor `gc()` 后 pack | Candidate `gc()` 后 pack | Anchor 写后立刻 / unique | Candidate 写后立刻 / unique | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `exact_duplicate_live_space` | `72.00 MiB` | `12.00 MiB` | `12.00 MiB` | `12.00 MiB` | `6.00x` | `1.00x` | exact duplicate 的写时膨胀已经完全消失。 |
| `aligned_overlap_live_space` | `54.00 MiB` | `22.33 MiB` | `14.00 MiB` | `22.33 MiB` | `3.86x` | `1.60x` | 写时空间明显更健康，但这个标准档合成数据集在旧固定 chunk 下原本就“完美对齐”，因此 `gc()` 后最终体积反而不如 anchor 极致。 |
| `shifted_overlap_live_space` | `72.00 MiB` | `35.83 MiB` | `72.00 MiB` | `35.83 MiB` | `6.00x` | `2.98x` | 错位重叠场景显著改善，FastCDC 的核心收益在这里开始体现。 |
| `historical_duplicate_space` | `288.00 MiB` | `12.00 MiB` | `12.00 MiB` | `12.00 MiB` | `24.00x` | `1.00x` | 同一路径历史重复写入不再制造短期 pack 膨胀。 |

### Pressure 档时间对比

| 场景 | Anchor | Candidate | 变化 | 说明 |
| --- | --- | --- | --- | --- |
| `large_upload` | `80.93 MiB/s` / `6.33s` | `78.97 MiB/s` / `6.48s` | `-2.4%` | GiB 级上传基本持平，说明默认切换 FastCDC 后吞吐没有数量级恶化。 |
| `large_read_range` | `80.80 MiB/s` / `0.396s` | `167.53 MiB/s` / `0.191s` | `+107.3%` | 压测档大范围 range read 明显提速，说明更少的重复 pack 与更稳定的可见索引布局在重负载下反而更有利。 |
| `hf_hub_download_cold` | `54.70 MiB/s` / `9.36s` | `49.14 MiB/s` / `10.42s` | `-10.2%` | 冷下载仍有回退，但缓存增量保持 `1.00 GiB`，没有额外放大。 |

### Pressure 档空间与复用对比

| 场景 | Anchor 写后立刻 pack | Candidate 写后立刻 pack | Anchor `gc()` 后 pack | Candidate `gc()` 后 pack | Anchor 写后立刻 / unique | Candidate 写后立刻 / unique | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `exact_duplicate_live_space` | `1536.00 MiB` | `512.00 MiB` | `512.00 MiB` | `512.00 MiB` | `3.00x` | `1.00x` | GiB 级 exact duplicate 也已经在写入当下完成物理复用。 |
| `aligned_overlap_live_space` | `1536.00 MiB` | `773.16 MiB` | `768.00 MiB` | `773.16 MiB` | `2.00x` | `1.01x` | 对齐重叠场景在压测档几乎直接压到唯一数据体积，和 anchor 的 `gc()` 后结果非常接近。 |
| `shifted_overlap_live_space` | `1536.00 MiB` | `526.54 MiB` | `1028.00 MiB` | `526.54 MiB` | `2.98x` | `1.02x` | GiB 级错位重叠是本轮最亮眼的收益点，当前已经非常接近唯一数据体积。 |

### 详细分析

#### 1. 写时复用已经真正落地，而不是只靠 `gc()`

最关键的变化不是“`gc()` 后能否压小”，而是“写完立刻是否已经健康”。

- standard 档 exact duplicate 从 `72.00 MiB` 直接降到 `12.00 MiB`
- standard 档 historical duplicate 从 `288.00 MiB` 直接降到 `12.00 MiB`
- pressure 档 exact duplicate 从 `1536.00 MiB` 直接降到 `512.00 MiB`

这说明当前大文件提交已经不是“先线性膨胀，再等维护命令回收”的模型，而是提交当下就直接复用已有 chunk。

#### 2. FastCDC 对 shifted overlap 的收益是实打实的

Phase 9 锚点最大的结构性短板是错位重叠：

- standard 档从 `6.00x` 唯一数据体积降到 `2.98x`
- pressure 档从 `2.98x` 进一步降到 `1.02x`

这不是噪声级收益，而是直接把“几乎无法复用”改成了“接近唯一体积”。也正因为这个结果已经足够明显，`fastcdc` 不再需要留在“实验路径”里。

#### 3. aligned overlap 要分开看“短期写时”与“最终极限”

当前 candidate 在 aligned overlap 上呈现出一个很有代表性的 trade-off：

- 写时空间明显比 anchor 健康，不再需要依赖后续 `gc()`
- 但 standard 档那个专门按旧固定 chunk 边界构造的合成数据，在 anchor 上 `gc()` 后可以压到更低的 `14.00 MiB`
- candidate 在 standard aligned case 上稳定在 `22.33 MiB`

这并不说明 candidate 退化成“更差格式”，而是说明：

- 旧锚点数据集对固定 chunk 非常友好
- 当前内容定义分块更偏向真实错位/近重复场景的总体收益
- 在更重的 pressure 档里，aligned overlap 已经能达到 `1.01x` unique，说明真实大体量场景下 candidate 更均衡

#### 4. 时间性能是“明显净收益 + 少数局部回退”的混合结果

当前不能把 Phase 10 简化成“所有时间路径都更快”。

已经确认的明显收益包括：

- standard `large_upload`、`small_read_all`、`snapshot_download_small`
- standard `full_verify`、`squash_history`
- pressure `large_read_range`

已经确认的局部回退包括：

- standard `large_read_range`
- standard `hf_hub_download_warm`
- standard `merge_non_fast_forward`
- pressure `hf_hub_download_cold`

因此当前最合理的工程结论不是回退 Phase 10，而是：

- 保留 FastCDC + 写时复用这条主线，因为它已经解决了最关键的空间问题
- 把后续时间侧工作聚焦到 range read、warm download、merge 三条可测热点

#### 5. 当前总体判断

如果按 Phase 9 当时提出的优先级来审视：

- “写时复用 / 短期空间膨胀控制”已经完成
- “是否值得做内容定义分块”也已经有了明确答案：值得，而且收益主要体现在 shifted overlap
- 剩余的性能工作已经从“空间正确性与去重模型”转向“若干读路径和 merge 路径的局部时间优化”

## 当前仓库状态下的结论

用最短的话概括当前真实状态：

- 时间性能：总体仍可接受，而且大文件写入、完整校验、历史压缩已经明显变好；但 warm download、merge 和部分 standard range read 还有回退要继续处理
- 空间性能：不只是长期 `gc()` 后健康，写后立刻也已经健康得多
- 复用能力：exact duplicate、historical duplicate 已基本达到 `1.0x`；shifted overlap 也已从明显短板收敛到接近唯一体积
- 当前最值得继续盯的点：range read 热点、warm detached view 路径、merge 时间路径，以及 aligned overlap 在特定合成数据集上的最终体积差异
