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

## 当前可以成立的结论

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

## 当前建议的优化优先级

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

## 新技术引入建议

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

## 结论摘要

用最短的话概括当前状态：

- 时间性能：大文件 baseline 和 GiB 级 pressure 都可接受，小文件/快照仍偏慢
- 空间性能：长期看健康，短期看重复大文件会膨胀
- 复用能力：exact duplicate 和对齐 overlap 好，错位 overlap 差
- 优先方向：先做写时复用，再看是否值得做内容定义分块
