# hubvault

[English README](README.md)

[![PyPI](https://img.shields.io/pypi/v/hubvault)](https://pypi.org/project/hubvault/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hubvault)
[![Documentation Status](https://readthedocs.org/projects/hubvault/badge/?version=latest)](https://hubvault.readthedocs.io/en/latest/)
[![Code Test](https://github.com/hansbug/hubvault/workflows/Code%20Test/badge.svg)](https://github.com/hansbug/hubvault/actions?query=workflow%3A%22Code+Test%22)
[![Package Release](https://github.com/hansbug/hubvault/workflows/Package%20Release/badge.svg)](https://github.com/hansbug/hubvault/actions?query=workflow%3A%22Package+Release%22)
[![codecov](https://codecov.io/gh/hansbug/hubvault/branch/main/graph/badge.svg?token=XJVDP4EFAT)](https://codecov.io/gh/hansbug/hubvault)
[![GitHub license](https://img.shields.io/github/license/hansbug/hubvault)](https://github.com/hansbug/hubvault/blob/master/LICENSE)

`hubvault` 是一个 API-first、embedded、portable 的本地版本化仓库，面向模型权重、数据集、评测结果和其它 ML artifacts。

它提供接近 Hugging Face Hub 的文件 API 手感，也提供接近 Git 的 commit / branch / tag / merge 语义，但仓库本身仍然只是一个可以整体移动的本地目录。不需要远端服务，也不需要你额外维护 repo 外数据库。

面向对象：想评估、安装和使用 `hubvault` 的仓库用户。

## 快速开始

安装:

```bash
pip install hubvault
```

只有在你需要 HTTP server 或 remote client 时，才额外安装对应 extras：

| 安装目标 | 命令 | 启用能力 |
| --- | --- | --- |
| 本地仓库基础能力 | `pip install hubvault` | 本地 Python API、CLI、embedded repo |
| 内建 HTTP server + web UI | `pip install 'hubvault[api]'` | `hubvault serve`、`python -m hubvault.server`、FastAPI app factory |
| Remote HTTP client | `pip install 'hubvault[remote]'` | `hubvault.remote.HubVaultRemoteApi` |
| 全量能力 | `pip install 'hubvault[full]'` | 本地仓库 + server + remote client |

基础安装仍然可以完整使用本地仓库能力。可选功能采用 lazy failure：
`import hubvault` 不会因为缺 extras 而直接失败，只有当你真的调用 server 或
remote 能力时，才会抛出 `MissingOptionalDependencyError`。

```python
from hubvault.optional import MissingOptionalDependencyError
from hubvault.server import create_app

try:
    create_app(repo_path="demo-repo", token_rw=("dev-token",))
except MissingOptionalDependencyError as err:
    print(err)
    # hubvault server app factory requires optional dependencies from
    # 'hubvault[api]'. Install them with 'pip install hubvault[api]'. ...
```

创建本地仓库、提交文件、读取文件，并拿到安全的 detached download view:

```python
from pathlib import Path

from hubvault import CommitOperationAdd, HubVaultApi

repo_dir = Path("demo-repo")
api = HubVaultApi(repo_dir)

info = api.create_repo()
print(info.default_branch)  # main

api.upload_file(
    path_or_fileobj=b"weights-v1",
    path_in_repo="artifacts/model.safetensors",
    commit_message="add model weights",
)

api.create_commit(
    operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
    commit_message="add readme",
)

print(api.list_repo_files())
print(api.read_bytes("README.md").decode("utf-8").strip())

download_path = api.hf_hub_download("artifacts/model.safetensors")
print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))

snapshot_dir = api.snapshot_download()
print(snapshot_dir)

print(api.quick_verify().ok)
```

如果你更喜欢 shell 工作流，可以用 CLI:

```bash
hubvault init demo-repo
printf 'weights-v1' > model.bin

hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
hubvault -C demo-repo ls-tree
hubvault -C demo-repo download artifacts/model.bin
hubvault -C demo-repo verify
```

`hubvault` 和 `hv` 指向同一个 CLI 入口。当前命令面包括 `init`、`commit`、`branch`、`tag`、`merge`、`log`、`ls-tree`、`download`、`snapshot`、`verify`、`reset`、`status`。

## 启动服务端

当你需要 HTTP API 或内建 web UI 时，安装 API extra：

```bash
pip install 'hubvault[api]'
```

CLI 下可直接快速启动内建服务。默认模式是 `frontend`，会同时提供 JSON API 和
浏览器界面，默认端口是 `9472`：

```bash
hubvault serve demo-repo \
  --init \
  --token-rw dev-token

# 浏览器界面: http://127.0.0.1:9472/
```

如果你只想暴露 API，并保留 `/docs` 下的接口文档，可以切到 `api` 模式：

```bash
hubvault serve demo-repo \
  --mode api \
  --init \
  --token-ro read-token \
  --token-rw write-token

# OpenAPI 文档: http://127.0.0.1:9472/docs
```

同一套运行时也支持模块方式启动：

```bash
python -m hubvault.server demo-repo \
  --mode frontend \
  --init \
  --token-rw dev-token
```

如果你希望像普通 Python 模块一样导入启动，直接使用一级模块
`hubvault.server`：

```python
from pathlib import Path

from hubvault.server import SERVER_MODE_FRONTEND, ServerConfig, launch

config = ServerConfig(
    repo_path=Path("demo-repo"),
    mode=SERVER_MODE_FRONTEND,
    token_rw=("dev-token",),
    init=True,
)
launch(config)
```

ASGI factory 也支持标准导入式部署。`uvicorn` 可以直接走 application
factory 模式：

```bash
export HUBVAULT_REPO_PATH=./demo-repo
export HUBVAULT_SERVE_MODE=frontend
export HUBVAULT_TOKEN_RW=dev-token

uvicorn --factory hubvault.server.asgi:create_app \
  --host 127.0.0.1 \
  --port 9472
```

如果你使用 Gunicorn，可以配合 ASGI worker 走 Gunicorn 的 application
factory 语法：

```bash
export HUBVAULT_REPO_PATH=./demo-repo
export HUBVAULT_SERVE_MODE=frontend
export HUBVAULT_TOKEN_RW=dev-token

gunicorn \
  --bind 127.0.0.1:9472 \
  --workers 2 \
  -k uvicorn.workers.UvicornWorker \
  'hubvault.server.asgi:create_app()'
```

## Docker

仓库现在也带了一套基于 Alpine 的轻量容器镜像。镜像会按 `full` extra 构建，
并把编译后的前端静态资源一并打进去，所以启动后前端界面可以直接使用。默认配置如下：

- `frontend` 模式
- 自动初始化仓库
- 仓库存储目录 `/data/repo`
- 监听地址 `0.0.0.0`
- 默认端口 `9472`

如果你只是想直接运行，先拉取已发布镜像：

```bash
docker pull ghcr.io/hansbug/hubvault:latest
# 如果你更习惯 Docker Hub，也可以尝试镜像同步源
docker pull hansbug/hubvault:latest
```

然后直接用一条 `docker run` 命令启动，并把仓库数据持久化到 named volume：

```bash
docker run --rm -it \
  -e HUBVAULT_TOKEN_RW=dev-token \
  -v hubvault-data:/data/repo \
  -p 9472:9472 \
  ghcr.io/hansbug/hubvault:latest
```

如果你是从源码仓库本地构建，再执行：

```bash
docker build -t hubvault:local .
```

如果你想直接走仓库内置命令，也可以：

```bash
make docker_build
```

如果你要运行本地构建出的镜像，只需要把镜像名改成 `hubvault:local`：

```bash
docker run --rm -it \
  -e HUBVAULT_TOKEN_RW=dev-token \
  -v hubvault-data:/data/repo \
  -p 9472:9472 \
  hubvault:local
```

同样的本地运行流程也可以直接用 `make docker_run`。

如果你希望仓库固定落在某个本地目录，可以改成 bind mount：

```bash
docker run --rm -it \
  -e HUBVAULT_TOKEN_RW=dev-token \
  -e HUBVAULT_PORT=8080 \
  -v "$(pwd)/demo-repo:/data/repo" \
  -p 8080:8080 \
  hubvault:local
```

或者直接使用 `make docker_run_bind DOCKER_REPO_DIR=./demo-repo DOCKER_PORT=8080`。

如果你在 Linux 上用 bind mount，并且希望生成的仓库文件继续归宿主机当前用户所有，
可以额外加上 `--user "$(id -u):$(id -g)"`，避免文件落成 `root`。

容器读取和 import / ASGI 启动完全相同的 `HUBVAULT_*` 环境变量，因此你可以直接覆盖：

- `HUBVAULT_PORT`
- `HUBVAULT_SERVE_MODE`
- `HUBVAULT_REPO_PATH`
- `HUBVAULT_TOKEN_RO`
- `HUBVAULT_TOKEN_RW`
- `HUBVAULT_INIT`
- `HUBVAULT_INITIAL_BRANCH`
- `HUBVAULT_LARGE_FILE_THRESHOLD`

## Remote Client

如果你要从另一个 Python 进程访问运行中的服务端，安装 remote extra：

```bash
pip install 'hubvault[remote]'
```

然后把 `HubVaultRemoteApi` 指到服务端 URL：

```python
from hubvault.remote import HubVaultRemoteApi

api = HubVaultRemoteApi("http://127.0.0.1:9472/api/v1", token="dev-token")

repo = api.repo_info()
print(repo.default_branch)

api.upload_file(
    path_or_fileobj=b"remote-weights-v1",
    path_in_repo="artifacts/model.bin",
    commit_message="upload model through remote api",
    show_progress=True,
)

print(api.list_repo_tree(recursive=True))
print(api.read_bytes("artifacts/model.bin"))
```

浏览器前端也使用同一套 bearer token。临时本地使用时，也可以直接打开类似
`http://127.0.0.1:9472/repo/overview?token=dev-token` 这样的链接，前端会先
消费 token，然后自动跳转到正常页面路径。

## 它适合什么

`hubvault` 适合那些想维护深度学习 artifacts，但不想先搭一整套重型基础设施的场景。它让你把大模型权重、数据集、评测结果、实验产物放进一个本地持久化仓库里，而这个仓库本身仍然只是一个可以整体移动的普通目录。

它最强的地方在于系统要求极低：不需要 Docker，不需要 Kubernetes，不需要远端 Hub 服务，不需要额外对象存储（例如 OSS / S3），也不需要 repo 外数据库。对于离线环境、预算敏感场景、或者已经遇到 Hugging Face 这类托管服务免费资源限制的使用者，`hubvault` 提供的是一个 repo-local 的替代方案。

它尤其适合你需要这些能力时使用：

- 持久维护多代深度学习大规模数据和模型 artifacts
- 用显式 commit、refs、回滚和校验替代临时缓存目录
- 需要原子写入语义，中断写入应回滚，而不是留下半发布状态
- 需要稳定的已提交数据，以及不会误改仓库真相的 detached 读取路径
- 需要通过 `get_storage_overview()`、`gc()`、`squash_history()` 自定义资源释放策略
- 需要 Hugging Face 风格文件操作，但底层是本地 embedded repository

`hubvault` 不是下面这些东西:

- 不是远端 Hub 服务
- 不是 Git remote / PR / code review 系统
- 不是 Git workspace 或 staging area 替代品
- 不是返回仓库真相文件路径给你随便改的可写缓存

## 性能快照

下面是当前 benchmark 快照中的实测值。测试环境是 Linux `x86_64`，CPython `3.10.10`。表格直接列出实测吞吐，并把它和同一轮测试里的本机顺序读写基线放在一起。

这些数字是一个具体参考点，不是对所有机器的保证。warm cache 行可能超过原始磁盘读基线，因为它们主要测的是 detached view 复用和缓存命中，不是纯物理磁盘读取。

### 字节型读写负载

| 工况 | benchmark 档位 | 实测吞吐 | 同轮磁盘基线 | 约等于基线 |
| --- | --- | ---: | ---: | ---: |
| 本机顺序读 | standard | `9296.92 MiB/s` | 读基线 | `100.00%` |
| 本机顺序写 | standard | `360.61 MiB/s` | 写基线 | `100.00%` |
| 大文件上传 | standard | `230.69 MiB/s` | 写 `360.61 MiB/s` | `63.97%` |
| 大文件范围读 | standard | `1113.59 MiB/s` | 读 `9296.92 MiB/s` | `11.98%` |
| 冷下载大文件 | standard | `846.98 MiB/s` | 读 `9296.92 MiB/s` | `9.11%` |
| 热下载大文件 | standard | `13761.47 MiB/s` | 读 `9296.92 MiB/s` | `148.02%` |
| 缓存密集热下载 | standard | `19704.43 MiB/s` | 读 `9296.92 MiB/s` | `211.95%` |
| 大文件上传 | pressure | `332.13 MiB/s` | 写 `360.22 MiB/s` | `92.20%` |
| 大文件范围读 | pressure | `910.23 MiB/s` | 读 `9532.68 MiB/s` | `9.55%` |
| 冷下载大文件 | pressure | `422.80 MiB/s` | 读 `9532.68 MiB/s` | `4.44%` |
| 热下载大文件 | pressure | `637608.97 MiB/s` | 读 `9532.68 MiB/s` | cache/view hit |
| 缓存密集热下载 | pressure | `39457.46 MiB/s` | 读 `9532.68 MiB/s` | `413.92%` |

### 元数据、历史和维护负载

这些工况不是单纯搬字节，所以直接拿它们和磁盘带宽比并不准确。这里列出来，是因为版本化 artifact 仓库真正用久以后，历史、树遍历、merge 和维护路径会明显影响体感。

| 工况 | 公开 API 面 | 实测结果 | wall time |
| --- | --- | ---: | ---: |
| 深历史列举 | `list_repo_commits` / `list_repo_refs` / `list_repo_reflog` | `15221.94 ops/s` | `4.40 s` |
| 递归目录树列举 | `list_repo_tree(recursive=True)` | `31185.03 ops/s` | `0.88 s` |
| 重型非快进合并 | `merge` | `126.65 MiB/s` | `0.43 s` |
| 历史压缩和后续清理 | `squash_history` | `146.83 MiB/s` | `1.48 s` |
| 分块阈值扫描 | `upload_file` + `get_paths_info` | `74.20 MiB/s` | `0.27 s` |
| 小文件全量读路径 | `read_bytes` | `5.76 MiB/s`，`1473.64 ops/s` | `0.91 s` |

直接结论是：大文件上传已经比较接近本机写入基线，范围读和冷下载是实打实的搬字节场景并带有仓库层开销，热下载主要体现缓存和 view 复用能力。当前最值得继续优化的是小文件热读，以及 warm path 里的 metadata 短路。

## 你现在能得到什么

- 仓库元数据、refs、reflog、事务状态、chunk 可见性和 object metadata 都在 repo root 下的 `metadata.sqlite3`
- payload bytes 继续以普通文件形式留在文件系统:
  - `objects/blobs/*.data`
  - `chunks/packs/*.pack`
- 仓库级公开并发边界由 `locks/repo.lock` 提供
- 读 API 返回的是 detached user view，不是可写 repo truth alias
- `quick_verify()`、`full_verify()`、`gc()`、`squash_history()`、`get_storage_overview()` 都是公开维护 API

对用户来说，这意味着仓库当前已经提供“repo-local metadata database + filesystem payload storage”的组合。你不需要直接操作数据库，公开 API 仍然面向仓库操作本身。

## 核心卖点

### 1. 仓库根目录本身就是产品

仓库所有持久状态都留在 repo root 内部。你可以:

- 移动整个目录到新的绝对路径
- 打包归档后再解压重开
- 把目录交给另一台机器或另一个进程继续使用

仓库真相不依赖绝对路径，不依赖外部注册状态，也不依赖 repo 外数据库。

### 2. 接近 Git 的历史模型，但不是 Git workspace

`hubvault` 提供:

- Git 风格 40 hex commit / tree / blob OID
- branch / tag / reflog
- fast-forward / merge-commit / conflict 三类 merge 结果
- 显式 commit API，而不是隐式 staging area

它更像“本地 artifact repository with Git-like history”，而不是“把 Git 生搬硬套到大文件目录上”。

### 3. 接近 Hugging Face Hub 的文件 API 手感

公开 API 以 `HubVaultApi` 为中心，包含:

- `upload_file()` / `upload_folder()`
- `hf_hub_download()` / `snapshot_download()`
- `list_repo_files()` / `list_repo_tree()` / `get_paths_info()`
- `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`

能对齐 `huggingface_hub` 的地方尽量对齐，纯本地 embedded repo 上没有实际行为意义的参数则不会为了“长得像”而保留成 no-op。

### 4. 读视图是 detached 的

- `hf_hub_download("artifacts/model.safetensors")` 返回的路径会保留 repo-relative suffix
- 该路径是一个可读用户视图
- 删除或修改这个路径，不会直接破坏 committed repository truth
- 下次需要时，系统可以重新 materialize 这个视图

也就是说，读 API 暴露的是“安全视图”，不是“仓库真相文件本体”。

### 5. 小文件与大文件都能走同一个版本化心智模型

- 小文件可直接作为普通 object 进入版本历史
- 大文件达到阈值后会切到 chunk / pack 存储
- 公开 file metadata 继续保留 HF 风格的 `oid` / `blob_id` / `sha256`
- 内部 object addressing 和公开 file metadata 分离，方便后续继续演进存储层

## 当前运行时布局

当前布局可以先记成下面这样:

```text
repo/
├── FORMAT
├── metadata.sqlite3
├── locks/
│   └── repo.lock
├── objects/
│   └── blobs/
│       └── ... *.data
├── chunks/
│   └── packs/
│       └── ... *.pack
├── cache/
├── txn/
└── quarantine/
```

通常你不需要直接检查这些内部文件。这里展示布局，是为了说明仓库为什么可以作为一个目录整体复制、归档和重新打开。

## 适用场景与非目标

适用场景:

- 本地模型仓库
- 数据集和评测集快照归档
- 训练输出、报告和可复现实验工件管理
- 需要 branch / merge / verify / GC 的离线 artifact repository

当前非目标:

- 远端同步协议
- 多租户服务端
- Git 工作区和 staging area 兼容层
- 把 payload bytes 全量塞进 SQLite

## 文档与开发入口

- English docs: https://hubvault.readthedocs.io/en/latest/
- 中文文档: https://hubvault.readthedocs.io/zh/latest/
- 贡献指南: [CONTRIBUTING.md](CONTRIBUTING.md)
- 仓库协作规范: [AGENTS.md](AGENTS.md)
- Benchmark 记录: [build/benchmark/](build/benchmark/)

## 项目状态

当前版本仍是 `0.0.1`，仓库整体处于 pre-stable 阶段，但以下能力已经形成真实可用的主体:

- SQLite truth-store
- detached read views
- local history / refs / merge / reflog
- verify / gc / squash / storage overview
- Python API 与 CLI 双入口

如果你需要的是一个本地、可移动、面向 ML artifacts 的版本化仓库，`hubvault` 现在已经值得作为实验性基础设施使用；如果你追求的是稳定的远端协作平台或完全成熟的热读性能，当前版本还在继续收敛中。
