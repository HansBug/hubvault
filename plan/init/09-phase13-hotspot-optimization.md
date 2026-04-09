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

根据 Phase 10 A/B 结果，当前最值得继续盯的路径包括：

- `read_range()`
  standard 档 1 MiB range read 出现回退，优先怀疑可见索引加载、逐 chunk lookup 与逐 chunk 校验链路。
- warm `hf_hub_download()`
  warm 路径已有 detached view 复用语义，但时间结果出现明显回退，优先怀疑 view existence check、目录扫描和 metadata 解析路径。
- 冷 `hf_hub_download()` / `snapshot_download()`
  继续观察 cache amplification、目录物化与文件树扫描的成本。
- `merge_non_fast_forward`
  当前不是主优化面，但已有可测回退，适合在 Phase 12 补齐 `merge-heavy` 数据集后重新排序。
- `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`
  深历史与 refs-heavy 仓库下仍可能出现明显 metadata hot path，需要 Phase 12 的 `history-deep` 数据集来验证。

## 优化顺序

Phase 13 的优化顺序固定如下：

1. 先用扩容 benchmark 排序热点，确认真正的前 2-3 个回退点。
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

- 对 `read_range()`、warm `hf_hub_download()`、`merge_non_fast_forward` 至少完成一轮 benchmark + profiling + 优化闭环
- 至少有 2 个热点在不改协议的前提下获得稳定收益
- 所有收益都能回写到 benchmark compare 报告和计划文档里，而不是只体现在 commit message 里

## Deferred Items

下面这些内容明确不属于 Phase 13 MVP：

- 新的默认存储格式或新的公开兼容层
- 以压缩或新协议替代当前主线实现
- 大规模重写 benchmark harness 本身
- 为所有热点一口气做并行复杂优化而缺少逐项归因

## Todo

* [ ] 基于 Phase 12 的完整 benchmark 结果，重新排序当前最值得优先处理的 2-3 个热点。
* [ ] 为 `read_range()`、warm `hf_hub_download()`、`snapshot_download()`、`merge_non_fast_forward`、`list_repo_commits()` 固定 profiling 命令、输入 shape 与产物保存位置。
* [ ] 优先尝试调用级 cache、批量 lookup、目录扫描合并和 metadata parse 收敛等零协议风险优化。
* [ ] 每轮优化后重跑同一批 benchmark，并把收益、无收益和伴随回退统一追记到计划文档。
* [ ] 为已证明高噪声的场景补“只看趋势不设门禁”的说明，避免误报。

## Checklist

* [ ] 每项优化都能追溯到一个具体的 benchmark 场景和 profiling 证据。
* [ ] 所有优化都保持公开语义、磁盘协议和恢复语义不变。
* [ ] 至少两条当前热点路径完成 benchmark -> profiling -> optimize -> benchmark 的闭环。
* [ ] 回归结果不只写“变快了”，而是明确写出收益比例、残余风险和未解决点。
* [ ] 如果某个优化方向收益不足，就明确停止，不继续堆复杂度。
