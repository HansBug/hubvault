# PR 1. FastAPI 服务、Vue 内置前端与 Remote API Phase 1-10 执行方案

## Status

- 状态：In Progress（Phase 1-8 已完成，Phase 9-10 待完成）
- PR：https://github.com/HansBug/hubvault/pull/1
- 目标分支：`main`
- 工作分支：`dev/api`

## 背景

`hubvault` 当前已经完成本地嵌入式仓库的稳定基线，但仍缺少一层面向“简易前端 + 远程 Python API”的官方服务面。下一阶段要补的不是多租户 Hub，而是一套单仓库、轻部署、可选依赖、仍保持 repo root 自包含的 FastAPI 服务层。

这份文档是一个 post-init 的独立执行计划，因此 phase 编号从 `1` 重新开始，不沿用初始化阶段或 Phase 15 之前的编号。这里的 `Phase 1-10` 专门对应“FastAPI 服务、内置前端、Remote API、打包发布”这一条新工作流。

## 目标

1. 提供基于 FastAPI 的官方服务层，支持 Python import 快速启动、CLI 快速启动和标准 ASGI 部署。
2. 前端采用 `Vue 3` + 成熟扁平化组件库，实现简洁、低样板代码的内置 Web UI。
3. 前端与 API 共享同一个 FastAPI app、同一个端口、同一棵根路由树，不另开第二个服务。
4. 启动模式只保留两种：`api` 和 `frontend`，其中 `frontend` 的含义是“同时提供 API + frontend”，并作为默认模式。
5. 提供 `HubVaultRemoteApi`，让远程站点调用体验尽量对齐 `HubVaultApi`。
6. 将 API、remote 相关依赖放在 extras 中，但所有代码、静态资源、CLI、可执行文件都保持在同一个 `hubvault` PyPI 包和同一个构建产物体系内。
7. 将实现计划细化到可以直接开工的粒度，包括测试、构建、打包、发布与回归策略。

## 非目标

- 不做多租户、多 repo 聚合、组织/用户系统、OAuth、SSO。
- 不做 PR、review、评论、通知等协作平台能力。
- 不把 repo 外部数据库、宿主注册表、外部对象存储引入为 correctness 前提。
- 不做首版 WebSocket、SSE、后台任务队列、异步 worker 架构。
- 不做首版“云端 Hub 完整替代品”。

## 总体定位

这套能力是 `hubvault` 的可选远程访问层，而不是新产品线。核心原则如下：

- 仓库真相仍然只有 repo root。
- SQLite + filesystem 仍然是底层事实。
- FastAPI、Vue UI、remote client 都只能站在现有公开 API 语义之上扩展。
- 不能因为服务层引入第二套 truth-store 或不可搬迁状态。

## 核心设计决策

### 1. 单包原则

- 仍然只有一个 PyPI 包：`hubvault`
- 不拆出 `hubvault-server`、`hubvault-remote`、`hubvault-webui` 之类的新包
- server、remote、frontend 代码都在同一个源码树内维护
- 前端构建产物最终打包进同一个 wheel / sdist / PyInstaller 可执行文件

extras 的意义只用于依赖解析，不用于拆包：

- `hubvault[api]`
- `hubvault[remote]`
- `hubvault[full]`，推荐作为 `api + remote` 的聚合 extra

### 2. 单服务原则

- API 和 frontend 必须挂在同一个 FastAPI app 上
- API 和 frontend 必须共享同一个 host / port
- API 和 frontend 必须共享同一套 token 鉴权和同一个 repo 绑定
- frontend 只能调用这个 app 下的 `/api/v1/**`

### 3. 启动模式

`hubvault serve` 的 `--mode` 只保留两个值：

- `api`
- `frontend`

其中：

- `api` = 仅注册 API 路由与 API 文档
- `frontend` = 注册 API 路由 + Vue 静态资源 + 前端 fallback

默认值：

- `--mode frontend`

### 4. 启动入口分层

必须同时支持：

- Python import 快速启动：适合像 Gradio 一样从普通 Python 脚本里直接启动服务
- CLI 快速启动：适合本地临时访问、单机内网、小团队共享、测试环境
- 标准 ASGI 部署：适合 `uvicorn` / `gunicorn` / 进程管理器 / 容器 / 反向代理场景

`hubvault/server/` 是与 `hubvault/repo/` 同级的一级 runtime module，负责 server 配置、app factory、路由、鉴权、异常映射、import 启动 helper 和 ASGI import target。`hubvault/entry/server.py` 只做 CLI 参数解析与命令注册，不持有 server runtime 逻辑。

Python import、CLI 和 ASGI 部署必须复用同一个 `ServerConfig` 和同一个 app 构造逻辑。

### 5. 运行边界

- 一个服务进程只绑定一个 repo root
- 仍然复用现有 `repo.lock`
- 仍然复用现有 SQLite 连接策略和 rollback-only 恢复语义
- 服务层不应把私有 backend 细节泄漏成第二套公开契约

## 建议目录布局

```text
hubvault/
├── api.py
├── remote/
│   ├── api.py
│   ├── client.py
│   ├── serde.py
│   ├── cache.py
│   └── errors.py
├── server/
│   ├── __init__.py
│   ├── __main__.py
│   ├── asgi.py
│   ├── app.py
│   ├── launch.py
│   ├── config.py
│   ├── auth.py
│   ├── deps.py
│   ├── schemas.py
│   ├── serde.py
│   ├── exception_handlers.py
│   ├── static/
│   │   └── webui/
│   └── routes/
│       ├── meta.py
│       ├── repo.py
│       ├── refs.py
│       ├── history.py
│       ├── content.py
│       ├── writes.py
│       ├── maintenance.py
│       └── ui.py
├── entry/
│   ├── cli.py
│   └── server.py
└── ...
webui/
├── package.json
├── vite.config.ts
├── vitest.config.ts
├── src/
│   ├── main.ts
│   ├── router.ts
│   ├── api/
│   ├── composables/
│   ├── views/
│   ├── components/
│   └── styles/
└── tests/
test/
├── server/
├── remote/
├── entry/
└── ...
```

约束：

- `hubvault/__init__.py` 不塞业务实现，只保留薄导出
- `hubvault/server/__init__.py` 只做 `create_app`、`launch`、`ServerConfig` 等公开 server 启动面的薄导出
- `hubvault/server/__main__.py` 可作为 `python -m hubvault.server` 快速启动入口，但必须复用 `hubvault.server.launch`
- `hubvault/entry/server.py` 只能调用 `hubvault.server` 公开面，不能复制配置解析、app 构造或运行时逻辑
- `webui/` 是前端源码目录，不是独立发布包
- `hubvault/server/static/webui/` 只存放构建产物

## 依赖与 extras 设计

### Python 依赖拆分

基础依赖继续放在 `requirements.txt`。

新增：

- `requirements-api.txt`
- `requirements-remote.txt`
- `requirements-full.txt`

预期职责：

- `requirements-api.txt`
  - FastAPI
  - ASGI server runtime
  - multipart 支持
  - 可能的 JSON/streaming 兼容依赖
- `requirements-remote.txt`
  - HTTP client
  - 远程缓存 / streaming 支持
- `requirements-full.txt`
  - `api + remote` 的并集，便于一条命令安装完整能力

版本约束：

- 必须显式选择仍支持 Python `3.7` 的版本区间
- 不让平台相关加速扩展成为 correctness 必需项
- 即使 extras 未安装，基础本地 API 和 CLI 仍可工作

### 可选依赖 import 纪律

必须明确区分“可导入”和“可执行”两个层次：

- `import hubvault`、现有本地 CLI、现有本地 API 不能因为未安装 `hubvault[api]` 或 `hubvault[remote]` 而失败
- `from hubvault.server import ServerConfig, create_app, launch` 与 `from hubvault.remote.api import HubVaultRemoteApi` 应尽量保持 import-time 稳定，不在模块导入阶段强依赖 FastAPI、ASGI runtime、HTTP client
- 真正需要第三方依赖的动作应在调用点或 runtime 装配点延迟导入，并给出明确安装提示，例如 `pip install hubvault[api]` 或 `pip install hubvault[remote]`
- `hubvault/__init__.py`、`hubvault/entry/*.py`、以及其它基础安装下常驻导入的模块，不得在顶层直接 import FastAPI、Starlette、uvicorn、httpx 之类 extras 依赖
- 类型注解如需引用 extras 类型，优先使用 `typing.TYPE_CHECKING`、字符串注解或本地 protocol，避免把第三方依赖变成 import-time 前提
- 允许 `hubvault/server/routes/*`、`hubvault/server/app.py`、`hubvault/remote/client.py` 这类 runtime 实现模块在实际使用时要求 extras，但公开薄导出层必须先把 import 边界处理好

### Node 依赖

前端构建和测试依赖只放在 `webui/package.json`，不进入 Python 运行时依赖。

推荐：

- `vue`
- `vue-router`
- `element-plus`
- `vite`
- `vitest`
- `@vue/test-utils`
- `playwright` 或等价 e2e 工具，仅作为开发/CI 依赖

## 启动与部署设计

### Python import 快速启动

推荐默认形式：

```python
from hubvault.server import launch

launch(
    repo_path="/path/to/repo",
    host="127.0.0.1",
    port=9472,
    token_ro=["readonly-token"],
    token_rw=["readwrite-token"],
    mode="frontend",
    open_browser=True,
)
```

需要把 app 嵌入现有 ASGI 进程时：

```python
from hubvault.server import ServerConfig, create_app

app = create_app(
    ServerConfig(
        repo_path="/path/to/repo",
        mode="frontend",
        token_rw=["readwrite-token"],
    )
)
```

行为约束：

- 上述公开启动面定义在 `hubvault.server`，而不是 `hubvault.entry`
- `launch(...)` 只是 quick-start helper，本质上仍然围绕 `ServerConfig` + app factory 组装
- import 启动与 CLI 启动必须共用同一套 `ServerConfig`
- 未安装 `hubvault[api]` 时，`hubvault.server` 的公开 import 不应在导入阶段崩溃，而应在实际调用 `create_app(...)` / `launch(...)` 时给出安装提示

### CLI 快速启动

推荐默认形式：

```bash
hubvault serve /path/to/repo \
  --host 127.0.0.1 \
  --port 9472 \
  --token-ro readonly-token \
  --token-rw readwrite-token \
  --mode frontend \
  --open-browser
```

只开 API：

```bash
hubvault serve /path/to/repo \
  --host 0.0.0.0 \
  --port 9472 \
  --token-rw readwrite-token \
  --mode api
```

建议参数：

- `path`
- `--host`
- `--port`
- `--mode`，默认 `frontend`
- `--token-ro`，可重复
- `--token-rw`，可重复
- `--default-revision`
- `--init`
- `--initial-branch`
- `--large-file-threshold`
- `--open-browser`

行为约束：

- `frontend` 模式一定同时暴露 `/api/v1/**`
- `api` 模式不注册 UI 静态资源与 fallback
- 未安装 `hubvault[api]` 或 `hubvault[full]` 时，`serve` 命令必须给出明确安装提示
- `hubvault serve` 只负责命令行参数体验与 quick-start 调用，不承载 server runtime 主实现
- 如果保留 `python -m hubvault.server`，其参数语义必须与 `hubvault serve` 保持一致
- 缺少 API extras 时失败点必须落在命令执行阶段，而不是 CLI 模块导入阶段

### 标准 ASGI 部署

推荐：

```bash
export HUBVAULT_REPO_PATH=/path/to/repo
export HUBVAULT_SERVE_MODE=frontend
export HUBVAULT_TOKEN_RW=readwrite-token
uvicorn hubvault.server.asgi:create_app --factory --host 0.0.0.0 --port 9472

gunicorn "hubvault.server.asgi:create_app()" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:9472
```

约束：

- `hubvault.server.asgi:create_app` 必须从环境变量或显式参数读取配置
- `uvicorn` / `gunicorn` 风格的 import string 必须直接指向 `hubvault.server` 公开 runtime，而不是 `hubvault.entry`
- Python import 启动、CLI 启动和 ASGI factory 启动必须共用同一套 `ServerConfig`
- 缺少 API extras 时，ASGI import target 应返回明确的安装错误，而不是在 unrelated import 链上抛出难以理解的 `ModuleNotFoundError`

## 路由树设计

### `api` 模式

```text
/
└── api/
    └── v1/
        ├── meta/
        ├── repo
        ├── refs
        ├── history/
        ├── content/
        ├── writes/
        └── maintenance/
```

### `frontend` 模式

```text
/
├── api/
│   └── v1/
│       ├── meta/
│       ├── repo
│       ├── refs
│       ├── history/
│       ├── content/
│       ├── writes/
│       └── maintenance/
├── assets/
│   └── ...
├── favicon.ico
└── {frontend route fallback -> index.html}
```

约束：

- frontend 路由走 `/`
- API 路由走 `/api/v1`
- 二者共享同一个根路径树和同一个 app
- 不允许再起第二个 Vite 运行时服务

## 鉴权与权限模型

### Token 模型

- 只支持 Bearer token
- token 分为 `ro` 和 `rw`
- token 来源先收敛到启动参数和环境变量
- token 是服务运行时配置，不写入 repo 真相层

### 权限语义

`ro` 允许：

- `repo_info`
- `get_paths_info`
- `list_repo_tree`
- `list_repo_files`
- `list_repo_commits`
- `list_repo_refs`
- `list_repo_reflog`
- `open_file`
- `read_bytes`
- `read_range`
- `hf_hub_download`
- `snapshot_download`
- `quick_verify`
- `full_verify`
- `get_storage_overview`

`rw` 在 `ro` 基础上额外允许：

- `create_repo`
- `create_commit`
- `merge`
- `create_branch`
- `delete_branch`
- `create_tag`
- `delete_tag`
- `upload_file`
- `upload_folder`
- `upload_large_folder`
- `delete_file`
- `delete_folder`
- `reset_ref`
- `gc`
- `squash_history`

### 前端 token 使用

- 用户首次进入站点时输入 token
- token 保存在 `sessionStorage`
- 所有请求统一注入 `Authorization: Bearer <token>`
- `GET /api/v1/meta/whoami` 用于 token 校验和角色探测

## API 契约与序列化设计

### 通用约束

- API 前缀统一为 `/api/v1`
- 所有错误返回结构化 JSON
- 所有 dataclass 模型通过显式 schema / serde 层转换
- `datetime` 统一走 ISO 8601 字符串
- response 头统一返回 `X-HubVault-Api-Version: 1`

错误响应：

```json
{
  "error": {
    "type": "RevisionNotFoundError",
    "message": "Revision 'dev' was not found.",
    "details": {}
  }
}
```

异常状态码映射：

- `RepositoryNotFoundError` -> `404`
- `RevisionNotFoundError` -> `404`
- `EntryNotFoundError` -> `404`
- `ConflictError` -> `409`
- `UnsupportedPathError` -> `422`
- `HubVaultValidationError` -> `422`
- `IntegrityError` -> `500`
- `VerificationError` -> `500`

### 路由映射

| `HubVaultApi` 方法 | HTTP | 路由 | 说明 |
| --- | --- | --- | --- |
| `create_repo` | `POST` | `/api/v1/repo` | 仅 `rw` |
| `repo_info` | `GET` | `/api/v1/repo` | `revision` query |
| `get_paths_info` | `POST` | `/api/v1/content/paths-info` | body 传路径数组 |
| `list_repo_tree` | `GET` | `/api/v1/content/tree` | `path_in_repo`、`recursive` |
| `list_repo_files` | `GET` | `/api/v1/content/files` | 返回路径列表 |
| `list_repo_commits` | `GET` | `/api/v1/history/commits` | `revision`、`formatted` |
| `list_repo_refs` | `GET` | `/api/v1/refs` | `include_pull_requests` |
| `create_branch` | `POST` | `/api/v1/refs/branches` | 仅 `rw` |
| `delete_branch` | `DELETE` | `/api/v1/refs/branches/{branch}` | 仅 `rw` |
| `create_tag` | `POST` | `/api/v1/refs/tags` | 仅 `rw` |
| `delete_tag` | `DELETE` | `/api/v1/refs/tags/{tag}` | 仅 `rw` |
| `list_repo_reflog` | `GET` | `/api/v1/history/reflog/{ref_name}` | `limit` |
| `read_bytes` | `GET` | `/api/v1/content/blob/{path:path}` | 八位流响应 |
| `read_range` | `GET` | `/api/v1/content/blob/{path:path}/range` | `start`、`length` |
| `hf_hub_download` | `GET` | `/api/v1/content/download/{path:path}` | 远程单文件下载 |
| `snapshot_download` | `POST` | `/api/v1/content/snapshot-plan` | 返回 manifest，由 client 逐文件拉取 |
| `create_commit` | `POST` | `/api/v1/writes/commit` | multipart manifest + file parts |
| `merge` | `POST` | `/api/v1/writes/merge` | 仅 `rw` |
| `upload_file` | `POST` | `/api/v1/writes/upload-file` | multipart |
| `upload_folder` | `POST` | `/api/v1/writes/upload-folder` | multipart + 相对路径清单 |
| `upload_large_folder` | `POST` | `/api/v1/writes/upload-large-folder` | multipart；tar 优化延后 |
| `delete_file` | `POST` | `/api/v1/writes/delete-file` | 仅 `rw` |
| `delete_folder` | `POST` | `/api/v1/writes/delete-folder` | 仅 `rw` |
| `reset_ref` | `POST` | `/api/v1/writes/reset-ref` | 仅 `rw` |
| `quick_verify` | `POST` | `/api/v1/maintenance/quick-verify` | `ro` 可读 |
| `full_verify` | `POST` | `/api/v1/maintenance/full-verify` | `ro` 可读 |
| `get_storage_overview` | `GET` | `/api/v1/maintenance/storage-overview` | `ro` 可读 |
| `gc` | `POST` | `/api/v1/maintenance/gc` | 仅 `rw` |
| `squash_history` | `POST` | `/api/v1/maintenance/squash-history` | 仅 `rw` |

### 写路径协议

#### `create_commit`

为了兼容 `CommitOperationAdd(path, path_or_fileobj)` 的多种输入，远程协议必须使用 `multipart/form-data`。

结构：

- `spec`: JSON part
- `file_*`: 各 add 操作的文件 part

`spec` 示例：

```json
{
  "revision": "main",
  "commit_message": "seed",
  "commit_description": "",
  "parent_commit": null,
  "operations": [
    {
      "op": "add",
      "path_in_repo": "demo.txt",
      "upload_field": "file_0"
    },
    {
      "op": "copy",
      "src_path_in_repo": "src.txt",
      "path_in_repo": "dst.txt",
      "src_revision": "main"
    },
    {
      "op": "delete",
      "path_in_repo": "obsolete/",
      "is_folder": true
    }
  ]
}
```

remote client 负责把：

- 本地路径
- `bytes`
- file object

统一归一化为 multipart 上传。

#### `upload_folder` / `upload_large_folder`

首版不要求服务端接受 tar 包作为唯一协议，而是先走：

- manifest + 多文件 multipart
- 前端目录上传依赖 `webkitdirectory` / `webkitRelativePath`

tar 流优化可以延后到后续 phase。

## Remote Client 设计

### 对外形态

```python
from hubvault.remote.api import HubVaultRemoteApi

api = HubVaultRemoteApi(
    base_url="http://127.0.0.1:9472",
    token="readwrite-token",
    revision="main",
    timeout=30.0,
)
```

### 核心原则

- 方法名尽量与 `HubVaultApi` 对齐
- 返回值复用现有 `hubvault.models`
- 错误类型复用现有 `hubvault.errors`
- 下载路径继续尽量保留 repo 相对路径后缀
- `open_file()` 返回可读 file object，而不是原始 HTTP response

### 本地缓存

建议新增 `hubvault.remote.cache`，职责如下：

- 管理 remote `hf_hub_download()` 的本地缓存目录
- 管理 remote `snapshot_download()` 的快照目录
- 保证缓存是 client 本地视图，不是 repo 真相

### Serde 设计

建议新增：

- `remote/serde.py`
- `server/serde.py`

职责分工：

- `server/serde.py`：dataclass -> response schema
- `remote/serde.py`：response JSON -> dataclass / exception

## 前端设计

### 技术栈

- `Vue 3`
- `Element Plus`
- `Vite`
- `vue-router`
- 尽量不引入 Pinia，首版优先 composable + `provide/inject`

### 页面范围

- 登录页
- Repo Overview
- Files
- Commits
- Refs
- Write Actions
- Maintenance

### 前端代码约束

- API 调用统一收口到 `webui/src/api/`
- token 注入和错误处理统一收口到一个请求封装层
- 组件尽量以“页面壳 + 复用列表/对话框组件”的方式实现
- 避免把 repo 逻辑直接散落到单个页面组件里

### UI 方向

- 扁平化浅色主题为默认
- 高信息密度、低装饰
- 重点使用成熟组件库现成能力，避免重造表格、树、表单、对话框

## 测试与回归设计

## 测试总原则

- Python 侧测试仍以 `pytest` 为主
- server / remote 测试优先走真实 HTTP 契约，不直接碰 backend 私有实现
- 前端测试分成单元测试、组件测试、构建后烟雾测试三层
- 打包测试必须验证 wheel / sdist / PyInstaller 可执行文件都带上前端资源
- 默认基础环境下的 `make unittest` 不能因为 API / remote extras 缺失而 collection 失败
- CI 至少拆成 base install 与 full install 两类 Python 测试环境

## 可选依赖测试纪律

- `test/server/**`、`test/remote/**`、以及依赖前端构建产物的测试，不得在模块顶层无保护地导入 extras 依赖
- 这些测试应在文件入口、fixture 或公共 helper 中先做 `pytest.importorskip(...)` 或等价依赖探测，再导入对应 runtime 模块
- base install 环境的目标是验证“未安装 extras 时基础能力仍可运行且 import 不炸”
- full install 环境的目标是验证 server、remote、frontend、打包链路的完整行为
- 新增一类显式的 import-stability 回归，覆盖 `import hubvault`、CLI 入口导入、`from hubvault.server import ...`、`from hubvault.remote.api import ...` 在缺少 extras 时的语义

### Server 测试分层

建议新增：

- `test/server/test_config.py`
- `test/server/test_auth.py`
- `test/server/test_schemas.py`
- `test/server/test_serde.py`
- `test/server/test_exception_handlers.py`
- `test/server/test_routes_meta.py`
- `test/server/test_routes_repo.py`
- `test/server/test_routes_content.py`
- `test/server/test_routes_refs.py`
- `test/server/test_routes_history.py`
- `test/server/test_routes_writes.py`
- `test/server/test_routes_maintenance.py`
- `test/server/test_ui.py`

覆盖方式：

- 配置测试：环境变量、CLI 参数转 `ServerConfig`
- 鉴权测试：无 token、坏 token、`ro`/`rw` 权限差异
- schema / serde 测试：`RepoFile` / `RepoFolder` discriminator、`datetime` 序列化、`CommitInfo` 恢复
- route 测试：真实 FastAPI app + `TestClient`
- integration 测试：真实临时 repo、真实上传文件、真实下载与 range read

重点断言：

- 同一路由在 `api` 与 `frontend` 模式下 API 契约一致
- `frontend` 模式会正确提供 `index.html` fallback
- `api` 模式不会暴露 UI 静态资源

### Remote Client 测试分层

建议新增：

- `test/remote/test_api.py`
- `test/remote/test_serde.py`
- `test/remote/test_cache.py`
- `test/remote/test_errors.py`

覆盖方式：

- `serde` 单测：JSON 到 dataclass / exception 的恢复
- `cache` 单测：下载缓存目录、快照目录、路径后缀保真
- API 契约测试：把 remote client 指向 test FastAPI app
- 真实上传测试：`CommitOperationAdd` 的三种输入类型都要覆盖

重点断言：

- remote 只读方法与本地 `HubVaultApi` 返回模型字段一致
- remote 写路径能保留 commit / merge / refs 语义
- remote 异常映射不会把 HTTP client 原生异常泄漏给业务调用方

### Frontend 测试分层

建议新增：

- `webui/tests/unit/`
- `webui/tests/components/`
- `webui/tests/e2e/`

工具建议：

- 单元/组件测试：`vitest` + `@vue/test-utils`
- 端到端烟雾测试：`playwright`

覆盖方式：

- 单元测试
  - 请求封装层 token 注入
  - 401/403 处理
  - route guard
  - `ro` / `rw` 权限门禁
- 组件测试
  - 文件树
  - commit 列表
  - refs 列表
  - 上传对话框
  - 确认对话框
- e2e 测试
  - 登录
  - 文件浏览
  - 下载按钮可见性
  - `ro` 模式写操作隐藏或禁用
  - `rw` 模式可执行基础上传和 refs 操作

### CLI / 打包 / 可执行文件测试

建议新增：

- `test/entry/test_server.py`
- `test/test_phase1.py` 到 `test/test_phase10.py` 中对应本次计划的集成回归文件
- 新增服务端 PyInstaller smoke test，用于验证静态资源被打进可执行文件

建议至少覆盖：

- `hubvault serve --mode api`
- `hubvault serve --mode frontend`
- `make build` 后的可执行文件可启动服务
- 可执行文件在 `frontend` 模式下能返回首页和 `/api/v1/meta/service`
- base install 下 `import hubvault`、导入现有 CLI、以及收集默认 unittest 用例都不会因为缺少 extras 而失败

## 打包与发布设计

### 同一个 PyPI 包

落地要求：

- 所有 Python 代码继续由 `setup.py` 的同一个 `hubvault` 包发布
- `extras_require` 继续由 `requirements-*.txt` 自动生成
- 需要额外新增 `requirements-full.txt`
- 不创建新的发布名
- extras 只控制依赖安装，不允许把缺少 extras 变成基础导入路径的崩溃点

### 前端资源进入 wheel / sdist

实现要求：

- `webui/` 仅作为源码目录
- 构建产物必须同步到 `hubvault/server/static/webui/`
- `package_data` 或 `MANIFEST.in` 必须确保静态资源进入 sdist / wheel

建议增加一个同步脚本或 make target，例如：

- `make webui_build`
- `make webui_test`
- `make webui_sync`

流程建议：

1. `cd webui && npm ci`
2. `cd webui && npm run test`
3. `cd webui && npm run build`
4. 将 `webui/dist/` 同步到 `hubvault/server/static/webui/`
5. 跑 Python 回归
6. 再执行 `make package`

### 前端资源进入 PyInstaller 可执行文件

实现要求：

- `make build` 产出的单文件或目录式可执行物都必须带上 `hubvault/server/static/webui/**`
- 如果现有 PyInstaller spec 或构建脚本没有显式收集静态资源，必须补上
- `make test_cli` 需要扩展为包含 `serve` 模式 smoke test

建议 smoke 验证：

- 启动可执行文件 `hubvault serve --mode frontend`
- 请求 `/`
- 请求 `/api/v1/meta/service`
- 验证二者都返回成功

### 发布前回归矩阵

实现完成后至少应跑：

- base install 下的 `make unittest`
- full install 下的 `make unittest`
- `make package`
- `make build`
- `make test_cli`
- `make rst_auto`，如果新增公开 docstring / 模块文档

前端改动时还应跑：

- `cd webui && npm run test`
- `cd webui && npm run build`

## MVP Cut

MVP 建议收敛为：

- FastAPI app factory
- `hubvault serve`
- `api` / `frontend` 两种模式
- `ro` / `rw` token
- 只读 API 全量
- `HubVaultRemoteApi` 只读对齐
- Vue UI 的登录、概览、文件、提交历史、refs 浏览
- 单文件上传、基础 commit、branch/tag 管理

## Deferred After MVP

- tar 流目录上传优化
- 并发下载与断点续传
- 更完整的浏览器目录上传兼容性
- OpenAPI 生成辅助 client
- 多 repo 路由复用
- 细粒度 token 生命周期与审计
- WebSocket / SSE 进度
- 更复杂的 UI 主题与动效

## Phase 1. 范围冻结、命名与运行模式定稿

### Goal

冻结这条路线的范围、术语、启动模式与公开命名，避免后续边做边改。

### Todo

* [x] 明确本计划是 post-init 独立 phase，编号从 `1` 开始。
* [x] 冻结 `api` / `frontend` 两种模式，并规定默认值为 `frontend`。
* [x] 明确 `frontend` 的含义是 “API + frontend 同时提供”。
* [x] 冻结 `hubvault.server` 作为与 `hubvault.repo` 同级一级 module 的职责边界。
* [x] 冻结 `hubvault.server.launch(...)`、`hubvault.server.create_app(...)` 与 `hubvault serve` 三类启动面的职责边界。
* [x] 冻结 `HubVaultRemoteApi` 公开命名，并决定是否提供 `HubVaultRemoteAPI` 别名。
* [x] 冻结“同一个 PyPI 包、同一个可执行文件”原则。
* [x] 冻结 API、frontend、remote 共用同一 FastAPI app 的原则。
* [x] 冻结“extras 缺失时公开 import 仍稳定、失败点后移到调用期”的原则。

### Checklist

* [x] 文档中不再出现 `api+frontend` 这种旧模式命名。
* [x] `frontend` 默认模式已经在 CLI 和部署说明里一致体现。
* [x] `hubvault.entry` 不再被表述为 server runtime 的唯一承载位置。
* [x] 可选依赖的 import 边界已经定清，不会把缺依赖问题扩散到基础安装路径。
* [x] 命名、模式和范围足够稳定，可以支撑后续直接实现。

## Phase 2. 依赖拆分、目录落位与打包骨架

### Goal

把依赖、目录与构建骨架搭出来，确保实现开始后不会在包结构上反复返工。

### Todo

* [x] 新增 `requirements-api.txt`、`requirements-remote.txt`、`requirements-full.txt`。
* [x] 新增 `hubvault/server/`、`hubvault/remote/`、`hubvault/entry/server.py` 骨架。
* [x] 在 `hubvault/server/` 下补齐 `__init__.py`、`__main__.py`、`launch.py` 的公开启动面骨架。
* [x] 增加统一的 missing-extra 提示与延迟导入骨架，避免顶层 import 触发 FastAPI / HTTP client 依赖。
* [x] 新增 `webui/` 前端源码目录与 `hubvault/server/static/webui/` 静态产物目录。
* [x] 补齐 `setup.py` / `MANIFEST.in` / 其它打包配置，使前端静态资源能进入包产物。
* [x] 为 `make build` 准备静态资源收集方案。
* [x] 为 `webui` 准备 `npm run test`、`npm run build`、资源同步脚本。

### Checklist

* [x] extras 仍然挂在同一个 `hubvault` 包上。
* [x] wheel / sdist / PyInstaller 的资源收集路径已经定清。
* [x] 前端源码与前端产物职责分离。
* [x] `hubvault.server` 的 import 路径和 `hubvault serve` 的适配关系已经定清。
* [x] base install 下 `import hubvault` 与默认 unittest 收集不会因为 extras 缺失而失败。

## Phase 3. 服务配置、启动入口与鉴权骨架

### Goal

打通服务最小骨架，让 `hubvault.server.launch(...)`、`hubvault serve` 和 ASGI factory 都能起同一套 app，并完成 token 鉴权基线。

### Todo

* [x] 实现 `server/config.py`，统一承载 repo path、mode、token、host、port 等配置。
* [x] 实现 `server/asgi.py`、`server/app.py` 与 `server/launch.py`，分别承载 ASGI import target、app factory 与 quick-start helper。
* [x] 实现 `server/__init__.py` 与 `server/__main__.py`，暴露薄 public API 与模块级命令入口。
* [x] 实现 `entry/server.py` 并把 `serve` 注册到 CLI，但保持其为 `hubvault.server` 的薄适配层。
* [x] 实现 API extras 缺失时的延迟导入与友好报错，不让 CLI / import surface 在模块导入阶段崩溃。
* [x] 实现 `server/auth.py` 与权限依赖。
* [x] 实现 `server/exception_handlers.py`。
* [x] 实现 `/api/v1/meta/service` 和 `/api/v1/meta/whoami`。
* [x] 增加 `test/server/test_config.py`、`test/server/test_launch.py`、`test/server/test_auth.py`、`test/entry/test_server.py`、基础安装下的 import-stability 回归。

### Checklist

* [x] `from hubvault.server import ServerConfig, create_app, launch` 可以稳定导入并按预期工作。
* [x] `hubvault serve --mode api` 可以成功起服务。
* [x] `hubvault serve --mode frontend` 可以成功起服务。
* [x] `uvicorn` / `gunicorn` 风格的 import string 可以在不经过 `hubvault.entry` 的情况下起服务。
* [x] 缺少 API extras 时，server 相关公开 import 保持稳定，实际调用时返回明确安装提示。
* [x] `ro` / `rw` token 行为已可区分。
* [x] 无 token、坏 token、权限不足的错误语义稳定。

## Phase 4. 只读 API 路由与下载闭环

### Goal

先完成只读 HTTP 闭环，让 repo 浏览、历史查看、文件下载、range 读取全部可用。

### Todo

* [x] 实现 `repo`、`content`、`refs`、`history` 的只读路由。
* [x] 实现 schema / serde 第一版，覆盖所有只读模型。
* [x] 实现单文件下载路由。
* [x] 实现 range 读取路由。
* [x] 实现 `snapshot-plan` 路由。
* [x] 增加 `test/server/test_routes_repo.py`、`test/server/test_routes_content.py`、`test/server/test_routes_refs.py`、`test/server/test_routes_history.py`。

### Checklist

* [x] `ro` token 可以完整浏览 repo 与历史。
* [x] 单文件下载路径仍保留 repo 相对路径后缀。
* [x] range 读取与本地 API 行为一致。
* [x] 快照下载计划可被 remote client 消费。
* [x] `make unittest` 通过。

## Phase 5. Remote 只读 client、错误映射与缓存

### Goal

做出可用的只读 `HubVaultRemoteApi`，把 HTTP 协议包装回本地风格接口。

### Todo

* [x] 实现 `remote/client.py` HTTP 传输层。
* [x] 实现 `remote/serde.py` 和 `remote/errors.py`。
* [x] 实现 `remote/cache.py`。
* [x] 实现 remote extras 缺失时的延迟导入与友好报错，不让公开 import surface 在模块导入阶段崩溃。
* [x] 对齐 `repo_info`、`get_paths_info`、`list_repo_tree`、`list_repo_files`、`list_repo_commits`、`list_repo_refs`、`list_repo_reflog`、`read_bytes`、`read_range`、`hf_hub_download`、`snapshot_download`。
* [x] 实现 `open_file()` 的远程文件对象包装。
* [x] 增加 `test/remote/test_api.py`、`test/remote/test_serde.py`、`test/remote/test_cache.py`、`test/remote/test_errors.py` 与 remote import-stability 回归。

### Checklist

* [x] remote 只读方法返回模型字段与本地 API 对齐。
* [x] remote 异常映射稳定，不泄漏底层 HTTP client 细节。
* [x] 远程下载缓存与快照缓存路径语义稳定。
* [x] 缺少 remote extras 时，remote 公开 import 保持稳定，实际调用时返回明确安装提示。
* [x] `make unittest` 通过。

## Phase 6. Vue 前端只读壳与静态托管

### Goal

先交付一套只读 Web UI，让用户在浏览器中登录、浏览、查看历史，而无需先补复杂写操作。

### Frontend Implementation Detail

Phase 6 的 UI 目标不是只做一个占位页，而是交付一套接近 Hugging Face repo 页信息架构的只读前端外壳。除不实现 README tag / pipeline tag / social metrics 这类当前本地 repo 不具备的数据外，页面布局和主要阅读流保持 HF 风格：

- 顶部 repo header：
  - repo 名称与本地路径标识
  - branch / tag 切换器
  - 访问级别标记（`ro` / `rw`）
  - 默认分支、当前 revision、HEAD、refs 数量、文件数等关键信息
- 一级导航采用 repo 视图而非操作台：
  - `Overview`
  - `Files`
  - `Commits`
  - `Refs`
  - `Storage`
- `Overview` 页承担 HF 的 model card / repo home 角色：
  - 读取并渲染根目录 `README.md`
  - 展示 repo 元信息摘要
  - 展示 refs / commits / files / storage 的摘要卡片
  - 最近提交列表放在侧栏
- `Files` 页承担 HF 的 Files and versions 角色：
  - 当前目录 breadcrumb
  - 文件/目录表格
  - 每一行都展示最近改动 commit 标题与时间
  - 文件详情区支持文本预览、README markdown 预览、二进制摘要与下载按钮
- `Commits` 页承担 HF 的 commit history 角色：
  - 基于当前 revision 展示 commit timeline
  - 展示 commit title、message 摘要、commit id、作者、时间
- `Refs` 页承担 branch / tag 浏览角色：
  - branch、tag 分栏列表
  - 当前选中 revision 高亮
  - 默认分支显式标注
- `Storage` 页承担本地 repo 特有的运维只读摘要角色：
  - repo 存储分析总览
  - 分 section 的大小与 reclaim strategy
  - quick / full verify 结果摘要

### Data Mapping

前端所有读取都必须经由 `/api/v1/**`，不允许直接读静态 JSON 或绕过 server app state。

Phase 6 预期使用的数据源如下：

- `/api/v1/meta/service`
  - UI 顶部 repo / mode / auth / default branch 摘要
- `/api/v1/meta/whoami`
  - token 校验与角色探测
- `/api/v1/repo`
  - revision 切换后的 repo 元信息
- `/api/v1/content/files`
  - README 探测与全量文件数量
- `/api/v1/content/tree`
  - Files 页目录浏览
- `/api/v1/content/paths-info`
  - 指定路径详情与最近改动 commit / time
- `/api/v1/content/blob/{path}`
  - README 与文本文件预览
- `/api/v1/content/download/{path}`
  - 单文件下载
- `/api/v1/history/commits`
  - commit timeline
- `/api/v1/refs`
  - branch / tag 切换器与 Refs 页
- `/api/v1/maintenance/quick-verify`
  - Storage 页 verify 摘要
- `/api/v1/maintenance/full-verify`
  - Storage 页深度 verify 摘要
- `/api/v1/maintenance/storage-overview`
  - Storage 页总览与 section 明细

### Frontend Stack

- 使用 `Vue 3` + `Vue Router` + `Element Plus` + `Vite`
- 状态管理保持轻量，优先使用组合式 API 与 app-level reactive store，不额外引入复杂 store 框架
- README markdown 渲染需做显式 HTML sanitization
- token 仅保存在 `sessionStorage`
- 构建目标显式收敛到 `es2015`
- 允许使用额外成熟 JS 库来减少重复造轮子，但最终产物仍需通过 `Vite/esbuild` 输出为 `es2015` 兼容代码
- 需要兼顾 2018 年前后主流浏览器环境，首版兼容目标至少覆盖当年的主流 Chrome / Firefox / Safari / Edge，而不是只面向最新浏览器
- API client 统一处理：
  - bearer token 注入
  - HTTP 错误展开
  - revision query 透传
  - 文本 / 二进制下载分流

### Information Architecture

前端路由与页面壳按 HF repo page 的阅读顺序组织，但保持 `hubvault` 自己的视觉语言：

- `/login`
  - token 输入
  - 调用 `/api/v1/meta/whoami` 做即时校验
  - 成功后跳转到当前 revision 的 `Overview`
- `/`
  - 重定向到 `/repo/overview?revision=<selected-ref>`
- `/repo/overview?revision=<selected-ref>`
  - repo header
  - README 主区
  - repo / refs / commits / files / storage 摘要侧栏
  - 最近提交列表
- `/repo/files?revision=<selected-ref>&path=<dir-or-file>`
  - breadcrumb
  - branch/tag 切换器
  - 文件表格
  - 当前选中文件预览 / 下载
- `/repo/commits?revision=<selected-ref>`
  - commit timeline
  - commit title / body / time / oid
- `/repo/refs?revision=<selected-ref>`
  - branches / tags 双列表
  - 当前 revision 高亮
- `/repo/storage?revision=<selected-ref>`
  - storage overview 卡片
  - sections 表格
  - quick/full verify 摘要

其中 `revision` 可以是 branch、tag 或具体 commit，统一放在 query string 中以兼容带 `/` 的 ref 名，并确保页面内所有读取都带相同 revision 查询参数。

### Component Plan

Phase 6 前端建议拆成以下复用组件：

- `AppShell`
  - 顶部品牌、repo 摘要、revision 切换器、权限徽标
- `RepoRevisionSwitch`
  - 统一展示 branches / tags
  - 支持筛选、当前项高亮、切换后保留当前 tab
- `RepoSummaryCards`
  - repo、refs、files、storage 总览卡
- `ReadmeViewer`
  - markdown 渲染、sanitize、代码块样式
- `FileTable`
  - 路径、类型、大小、最近提交标题、最近时间
- `FilePreviewPanel`
  - markdown / text / binary 三种预览模式
- `CommitTimeline`
  - commit 列表与相对时间展示
- `RefsPanel`
  - branches / tags 分栏
- `StorageOverviewPanel`
  - usage summary、recommendations、sections 明细、verify 状态

### Data Semantics

- `content/tree` 与 `content/paths-info` 返回的 `RepoFile` / `RepoFolder` 必须补齐 `last_commit`
- `Files` 页每一行至少展示：
  - repo-relative path
  - entry type
  - size（目录显示 `-`）
  - 最近改动 commit title
  - 最近改动时间
- `Overview` 页的 README 加载规则：
  - 优先探测 `README.md`
  - 再回退 `README.rst`、`README.txt`
  - 无 README 时显示明确 empty state
- 文本预览首版支持：
  - markdown
  - 常见 UTF-8 文本
  - JSON pretty display
  - 二进制文件给出 metadata + download CTA

### Interaction Details

- revision 切换必须是全局状态，但仍以 URL 为准，避免刷新后状态丢失
- 进入页面时若 token 缺失或失效，统一跳转回 `/login`
- `ro` 用户只显示只读导航，不展示写操作 CTA
- 页面加载采用 skeleton / empty / error 三态，避免裸白屏
- `Files` 页桌面端采用“表格 + 右侧预览”，移动端收敛为单列卡片加抽屉预览
- README 与文件预览都不得绕过 API 直接读取静态资源
- 所有下载链接都通过 `/api/v1/content/download/{path}` 暴露
- 避免把过新的 Web API 当作 correctness 前提，例如仅最新浏览器才稳定支持的 API、CSS 特性或模块语法

### Visual Direction

- 参考 HF repo 页的信息密度和阅读顺序，但不照搬品牌色
- 视觉基调采用偏青色的浅色背景、青灰边框、深墨色正文与低阴影扁平卡片，不再沿用暖灰/琥珀主强调
- 重点不是“后台系统感”，而是“可阅读的仓库主页”
- 桌面端采用主内容 + 侧栏摘要布局，移动端收敛为单列卡片流
- 首页主区优先强调 README / content，可读性高于“控制台面板感”
- 文件表格和 commit timeline 允许更高信息密度，尽量接近 HF 页面那种浏览节奏
- 动效仅限页面初载入、tab 切换和 skeleton 淡入，不做过度 hover 装饰

### Testing and Validation

- `webui/tests/unit/`
  - 格式化函数、markdown/preview 选择逻辑、token/session 状态逻辑
- `webui/tests/components/`
  - branch switcher、file table、README viewer、storage summary 等核心组件
- `webui/tests/e2e/`
  - 登录、revision 切换、README 渲染、文件浏览、commit/refs/storage 页面跳转
- Python 侧补 `test/server/test_ui.py`
  - `api` 模式不暴露 UI
  - `frontend` 模式托管 built assets
  - 前端所有读取流量仍经由 `/api/v1/**`
- 交付前需执行一次真实视觉校验：
  - build frontend
  - sync 到 `hubvault/server/static/webui/`
  - 启动 `frontend` 模式 server
  - 使用浏览器自动化生成截图并检查关键布局、README、文件表格、commit timeline、storage 卡片是否真实渲染
  - 保留 Playwright 截图与 HTML report 以便回看
- 构建配置需同时验证 legacy bundle 存在且页面在非最新浏览器语法目标下仍可加载

### Todo

* [x] 建立 `webui/` 的 Vue 3 + Element Plus + Vite 骨架。
* [x] 实现 token 登录页与全局请求封装。
* [x] 实现 Overview、Files、Commits、Refs 页面。
* [x] 实现 `ro` / `rw` 权限门禁与导航控制。
* [x] 实现 `frontend` 模式下的静态资源托管和 fallback。
* [x] 增加 `webui/tests/unit/`、`webui/tests/components/`、`webui/tests/e2e/`。
* [x] 增加 `test/server/test_ui.py`，验证 `api` 模式不暴露 UI，`frontend` 模式暴露 UI。

### Checklist

* [x] `frontend` 模式可以正常打开首页。
* [x] 前端所有读取都经由 `/api/v1/**`。
* [x] `ro` 用户看不到或无法触发写操作入口。
* [x] 前端构建产物能够被 FastAPI 正确托管。

### Completion Update

- 已实现 `webui/` 下的 `Vue 3` + `Vue Router` + `Element Plus` + `Vite` + `TypeScript` 只读前端，包含 `Login`、`Overview`、`Files`、`Commits`、`Refs`、`Storage` 五个 repo 视图。
- 已在 `frontend` 模式下通过 `hubvault.server.app` 托管打包产物，并对非 `/api/` 路径启用 SPA fallback；`api` 模式下不暴露前端入口。
- 前端 token 仅保存在 `sessionStorage`，所有读取统一经由 `/api/v1/**`，revision 通过 query string 在各页面间透传。
- 当前 UI 保持只读信息架构，不暴露写操作 CTA；`ro` / `rw` 权限差异体现在登录鉴权结果、权限徽标与服务端接口能力边界上。
- 已补齐 `webui/tests/unit/`、`webui/tests/components/`、`webui/tests/e2e/`，以及 `test/server/test_ui.py`、`test/server/test_app.py`、`test/server/test_launch.py` 的前端托管回归。
- 已完成真实视觉校验，并保留 `webui/test-results/visual/*.png` 与 `webui/playwright-report/index.html` 作为回看产物。
- `hubvault/server/static/webui/` 现作为包内生成目录处理，Git 只保留占位文件，实际静态资源由 `make webui_package` / CI 构建后同步。
- 截至 2026-04-11，本阶段已通过本地与 CI 验证：`make webui_package`、`cd webui && npm run test:coverage`、`cd webui && npm run test:e2e`、`make package`，以及 GitHub Actions `Code Test` / `Release Test` workflow 全绿。

## Phase 7. 写路径 API 与 Remote 写能力

### Goal

把远程写路径打通，让 server 与 remote client 都能完成核心 repo 修改动作，并为上传链路补齐可重试、可校验、可减少实际传输字节数的 fast-path。

### Todo

* [x] 实现 `create_commit` 的 multipart manifest 协议。
* [x] 在 upload manifest 中补齐 `base_head` / `parent_commit` 约束，避免预检与实际写入之间被并发写操作污染。
* [x] 实现基于目标 base revision snapshot 的“秒传/快传”：
  - 完全相同文件可直接复用已有对象而不再上传文件字节
  - 大文件可基于已存在 chunk 只补传缺失 chunk，减少实际上传流量
* [x] 实现 `upload_file`、`create_branch`、`delete_branch`、`create_tag`、`delete_tag`。
* [x] 实现 `merge`、`reset_ref`、`delete_file`、`delete_folder`。
* [x] 实现 `upload_folder`、`upload_large_folder` 的首版 multipart 协议。
* [x] 对齐 `HubVaultRemoteApi` 的写方法。
* [x] 为 `CommitOperationAdd` 的路径 / bytes / fileobj 三种输入写完整测试。
* [x] 增加 `test/server/test_routes_writes.py` 与 remote 写路径测试。

### Checklist

* [x] `rw` token 可以完成核心写操作。
* [x] `ro` token 在所有写路径上被稳定拒绝。
* [x] merge 冲突能通过 HTTP 与 remote 保持结构化返回。
* [x] 上传预检结果与最终提交之间存在并发写入时，服务端会稳定返回冲突并要求重新 plan。
* [x] 完全重复文件不需要重复上传字节；可复用 chunk 的大文件实际上传字节显著减少。
* [x] `make unittest` 通过。

### Conclusion

- 截至 2026-04-11，server `write` 路由、`hubvault.server.uploads` 与 `HubVaultRemoteApi` 已打通同一套 `commit-plan` / `commit` 协议，并用 `base_head` / `parent_commit` 拒绝脏 plan。
- 秒传严格限定为目标分支 base snapshot 上的完全相同文件复用；快传严格限定为该 snapshot 可见 chunk 的复用，避免“预检看到的对象”和“实际提交时的对象”不一致。
- 本阶段已通过本地验证：`make unittest`，其中包含 `test/server/test_routes_writes.py`、`test/remote/test_api.py`、`test/remote/test_serde.py` 等写路径与冲突场景回归。

## Phase 8. 前端写操作、维护操作与可执行文件闭环

### Goal

补齐浏览器端常用写操作和 maintenance 操作，并确认打包后的可执行文件可独立提供完整服务。

### Todo

* [x] Vue 前端接入上传文件、上传目录、delete、commit、branch/tag、merge、reset。
* [x] 浏览器端上传至少支持 exact-match 秒传，并与服务端 `base_head` 校验保持一致。
* [x] 实现维护 API：`quick_verify`、`full_verify`、`get_storage_overview`、`gc`、`squash_history`。
* [x] Vue 前端接入 verify / storage / gc / squash history 页面与操作对话框。
* [x] 扩展 `make test_cli` 或新增 smoke 测试，验证可执行文件的 `serve --mode frontend`。
* [x] 验证 PyInstaller 产物包含前端静态资源。
* [x] 增加前端 e2e 与 Python 端到端联测。

### Checklist

* [x] 浏览器端可完成常见 repo 维护动作。
* [x] 浏览器端上传在预检过期时会明确提示用户刷新后重试，不会基于脏 plan 继续写入。
* [x] 可执行文件可直接启动完整 `frontend` 模式。
* [x] `/` 与 `/api/v1/meta/service` 在可执行文件模式下均可访问。
* [x] `make unittest`、`make build`、`make test_cli` 通过。

### Conclusion

- 浏览器端已接入 upload / delete / refs / maintenance 全链路；上传使用 `commit-plan` 预检，命中完全相同文件时可直接秒传，预检过期时前端会明确提示刷新后重试。
- 前端回归已覆盖真实服务与组件层：`cd webui && npm run test`、`cd webui && npm run build`、`cd webui && npm run test:e2e` 全部通过。
- `make build` 现固定走本地 `./venv/bin/python -m PyInstaller`，并在 spec 生成阶段收集 `fastapi` / `uvicorn` / `multipart` 等惰性可选依赖，使打包产物中的 `hubvault serve --mode frontend`、`/` 与 `/api/v1/meta/service` 均通过 `make test_cli` 实测。

## Phase 9. Web UI 深化、文件详情、Commit Diff 与上传体验增强

### Goal

把当前“可用”的内置前端推进到更接近 HF 浏览体验的状态：支持 `?token=` 直达登录、路径树与文件详情分离、文件高质量预览、commit diff 查看、上传队列与实时进度，并保持对较旧浏览器环境的兼容基线。

### 技术方案（截至 2026-04-12 调研）

#### 方案原则

- 能直接复用成熟轮子的，不在 Phase 9 自己手写 viewer、diff renderer、图标体系或上传进度协议。
- 轮子必须优先选择与现有 `Vue 3 + Element Plus + Vite` 栈兼容、无需引入 React/Monaco 之类重型异构 runtime 的方案。
- 前端构建继续维持 `Vite legacy + build.target=es2015` 这条兼容线，不把“现代浏览器独占 API”变成页面可用性的前提。
- 新增服务端能力仍然必须通过 `hubvault` 公共语义暴露；server route 不应直接把 backend 私有实现变成第二套前端专用协议。

#### 轮子选择与依据

- 路由与登录直达：
  继续使用 [Vue Router 官方 query / navigation 能力](https://router.vuejs.org/guide/essentials/navigation.html) 与 [dynamic matching / catch-all path](https://router.vuejs.org/guide/essentials/dynamic-matching.html)；`?token=` 只作为一次性引导入口，认证成功后立即写入 `sessionStorage` 并用 `router.replace` 去掉 URL 中的 token，避免 token 长时间停留在地址栏、历史记录和截图里。
- 图标与操作按钮：
  继续使用已经在仓库中的 [Element Plus Icon](https://element-plus.org/en-US/component/icon.html) 与 `el-button` / `el-link` 体系，不单独引入另一套 icon design system，避免视觉和交互语言冲突。
- 文件语法高亮与行号：
  采用 [PrismJS](https://prismjs.com/) 加 [官方 line-numbers plugin](https://prismjs.com/plugins/line-numbers/)。Prism 的优势是 DOM/CSS 集成简单、语言扩展成熟、对普通静态代码块友好，也更适合当前扁平风 UI，而不需要为单文件浏览引入编辑器级 runtime。
- Commit 文本 diff：
  采用 [Diff2Html](https://diff2html.xyz/) 渲染服务端生成的 unified diff。它已经内建 line-by-line / side-by-side 两种 diff 视图，能显著减少我们自己写 diff DOM、hunk 折叠、行号布局和增删样式的工作量。
- 图片对比：
  采用 [JuxtaposeJS](https://juxtapose.knightlab.com/) 做前后版本图片对比，并保留“初始化失败或浏览器特性不足时退化为左右并排图片”的 fallback。这里优先选更老牌、DOM 级的 before/after 方案，而不是把 custom-element 作为唯一实现路径。
- 浏览器上传进度：
  继续走 [Axios `onUploadProgress`](https://axios-http.com/docs/req_config) 官方能力，不额外造浏览器端上传传输层。
- Python Remote API 上传进度：
  增加可选 `tqdm` 集成；当 `tqdm` 可用时提供默认进度条，也允许显式 `silent` / `show_progress=False` 关闭。若未安装 `tqdm`，远端上传能力仍然照常可用，不把进度条依赖变成 correctness 前提。
- 旧浏览器兼容线：
  继续遵守 [Vite Browser Compatibility / legacy plugin](https://vite.dev/guide/build.html#browser-compatibility) 口径，保持 `@vitejs/plugin-legacy` 与 `build.target=es2015`，新增代码不默认依赖仅现代浏览器才稳定的 API。

#### 前端路由与页面结构

- 保留 `/repo/files` 作为“目录树 / 路径页”，只承担浏览目录、选择分支路径、下载入口和上传入口，不再在同页右侧嵌 preview。
- 新增独立文件详情页，采用类似 `/repo/blob/:pathMatch(.*)*?revision=...` 的 route，路径树页点击文件时跳转到详情页。
- 新增独立上传页，采用类似 `/repo/upload?revision=...&path=...` 的 route；`/repo/files` 只保留文件列表右上角的 upload 入口按钮，不再直接内嵌 upload queue 面板。
- 新增独立 commit 详情页，采用类似 `/repo/commits/:commitId?revision=...` 的 route，commit 列表页点击单条 commit 后进入详情页查看文件变化。
- 路径页与文件详情页中的 breadcrumb 视觉对齐当前 HF files 页面：
  - 顶层入口使用 home icon 表示 `<home>` / repository root
  - 每一级路径之间使用裸文本 `/`
  - 每一级祖先路径都可点击跳转
  - breadcrumb 本身不使用 pill / badge / card 式包裹，只保留文字与图标
- `?token=` 入口应在根路由、登录页和受保护路由守卫中都生效：
  - 未登录但 URL 带 `token` 时，先尝试 bootstrap；
  - 成功后立即清理 query 中的 token；
  - 失败则清空会话并落回登录页，同时保留错误信息；
  - 不能让 token 跟随后续路径切换和下载链接一起继续传播。

#### 文件详情页方案

- 文件详情页 header 至少包含：
  - repo-relative path
  - revision / last commit 摘要
  - download 按钮
  - 返回当前目录或上级目录按钮
- 文件详情页路径头部的 breadcrumb 必须与路径页保持一致，祖先路径可直接点击返回对应目录级别。
- 文件详情页当前用于展示目录、size、oid、sha256 等信息的 badge 需要压低高度，避免出现过厚的胶囊块，整体更接近 HF 的紧凑信息条。
- 文件预览模式按“文件类型 + 大小阈值”分流：
  - Markdown：继续复用 `markdown-it + DOMPurify`
  - 代码 / 纯文本：用 Prism 渲染，左侧固定行号
  - JSON：先格式化再按代码块渲染
  - 图片：直接在线展示
  - 其他二进制：明确显示“binary 无法在线展示”，并保留下载按钮
- 代码语言识别以扩展名映射为主，不做运行时 AST 识别；未知语言退化为纯文本高亮，不阻塞行号显示。
- 代码框中的行号与正文必须共享同一套行高、padding 与 `white-space` 规则，不能出现长文件时左侧行号与右侧内容错位的情况。
- 代码框字体必须强制使用仓库内随前端静态资源一起发布的等宽字体，不依赖宿主系统“刚好有某个 monospace”。
- 图片识别优先基于常见扩展名与 MIME/魔数兜底；不能稳定识别的内容按二进制 fallback 处理，而不是强行内嵌。
- 路径树页面中，文件行增加独立 download icon；目录行不加下载按钮。
- 文件列表中的 view / download / delete 等 icon-only 操作必须补 tooltip，避免歧义。

#### Commit 详情 / Diff API 方案

- 新增服务端 commit 详情 API，至少包含：
  - commit 基本信息
  - 第一父提交 ID；root commit 时允许为空
  - 变更文件列表
  - 对文本文件生成的 unified diff
  - 对二进制文件的 old/new size、sha256、oid/blob_id 元信息
  - 对图片文件的 old/new 下载地址
- 文本 diff 在服务端生成 unified diff，前端只负责交给 Diff2Html 渲染，避免在浏览器端重复实现 hunk 算法。
- 图片 diff 不尝试生成像素级 patch，前端基于 old/new 两张图做 before/after compare；若浏览器或库初始化失败，则退化为左右双栏对比。
- 不可在线渲染的二进制资源只展示：
  - path
  - change type
  - old/new size
  - old/new sha256
  - old/new 下载按钮
- merge commit 的首版 diff 明确只对第一父提交做比较，与 GitHub/HF 常见默认行为对齐，不在首版引入多父合并 diff UI。
- commit 列表中的 commit title 与文件列表 `last commit` 列都应直接可点击进入对应 commit diff 页面，减少额外的“先点 View Diff 再跳转”步骤。

#### 上传队列与进度方案

- 前端上传从“选择即立刻 commit”改成“两段式”：
  - 第一段：把文件或目录中的文件逐步加入待提交队列，允许多次追加
  - 第二段：用户确认 commit message 后，统一 `planCommit` + `applyCommit`
- 上传队列不直接常驻在 `/repo/files` 页面主体内，而是放到独立 upload 页面承载；文件页只保留入口按钮、当前路径上下文与必要的跳转。
- 队列内以 `path_in_repo` 作为主键，重复添加时后加入的条目覆盖前一个条目，并允许手动移除。
- 前端进度条至少展示：
  - 当前阶段（hash / plan / upload / finalize）
  - 已上传字节 / 总上传字节
  - 当命中秒传时应明确提示“无需上传字节”
- 浏览器端首版仍然优先走完整文件上传；服务端已有的秒传/快传逻辑继续通过 `commit-plan` 自行裁剪实际需要上传的 payload。
- Python `HubVaultRemoteApi` 侧补齐上传进度：
  - 默认 tqdm 进度条
  - `silent` 或 `show_progress=False` 关闭
  - 自定义 `progress_callback` 供非 CLI 调用方接管
  - 缺少 `tqdm` 时自动退化为无进度输出

#### 测试与回归口径

- 前端：
  - `router` / `session` 单测覆盖 `?token=` 入口、token 清理与受保护路由跳转
  - 组件 / 视图测试覆盖文件详情页、代码高亮、图片预览、binary fallback、下载按钮、上传队列和进度条
  - commit diff 页至少覆盖文本 diff、图片 diff、binary diff 三类展示
  - e2e 覆盖“URL 带 token 直达页面”“从路径树跳到文件详情”“上传队列多次追加后提交”
- Python：
  - server history 新 route 回归
  - remote client 对应 commit detail / diff / progress 的公共行为回归
  - 如新增公开模型或 docstring，同步补测试与 `rst_auto`

### Todo

* [ ] 在登录入口、路由守卫与初始化流程中支持 `?token=xxxx` 一次性登录入口，并在认证成功后清理 URL。
* [ ] 新增独立文件详情页，路径树页点击文件时跳转详情页，不再在同页右侧预览。
* [ ] 参考当前 HF files 页面重做路径 breadcrumb：顶层 home icon、祖先可点击、层级间使用 `/`、不再使用现有胶囊框。
* [ ] 路径树页把 `DIR` / `FILE` 文本替换为图标，并为文件增加独立下载图标；全站补齐与现有 Element Plus 风格一致的图标化操作入口。
* [ ] 文件列表中的 view / download / delete 等 icon 操作补齐 tooltip，降低误解成本。
* [ ] 文件详情页支持 Markdown、代码/纯文本带行号预览、图片在线展示、binary fallback 与下载。
* [ ] 修复代码预览中行号与正文行高不同步的问题，并为代码框引入随前端一起发布的等宽字体资源。
* [ ] 压低文件详情页路径 / size / oid / sha256 等 badge 的高度，改成更紧凑的信息展示。
* [ ] 增加 commit 详情 API 与页面，支持文本 diff、图片对比和 binary 元信息比较。
* [ ] commit 列表中的 title 与文件列表 `last commit` 列支持直接跳转到 commit diff 页面。
* [ ] 前端上传改成“文件页提供 upload 按钮，进入独立上传页后可多次追加到待提交队列，再统一 commit”的交互，并增加实时进度条。
* [ ] `HubVaultRemoteApi` 增加可静默的上传进度反馈能力。
* [ ] 增加前后端对应单元测试、前端 e2e 回归，并维持旧浏览器构建兼容线。

### MVP Cut / Deferred

- 首版 commit diff 只做第一父提交比较，不做多父 merge diff UI。
- 首版不做 rename / copy heuristics；commit 详情页先按路径级 add / delete / modify 展示。
- 首版不做 blame、行级评论、代码搜索、富媒体文档插件系统。
- 首版不把前端大文件分块上传单独下放到浏览器端；浏览器端仍以完整文件为输入，由服务端 `commit-plan` 决定秒传/快传裁剪。

### Checklist

* [ ] 用户可通过 `/?token=...` 直接进入 repo 页面，且认证成功后地址栏不再残留 token。
* [ ] 路径树页与文件详情页职责分离，文件点击后进入独立页面。
* [ ] 路径 breadcrumb 采用 HF 风格的文字级层级导航：home icon 顶层入口、`/` 分隔、每一级祖先均可点击。
* [ ] 文本和代码文件在详情页中带行号展示，代码按扩展名高亮。
* [ ] 代码框行号与正文逐行对齐，且代码字体使用仓库自带的等宽字体资源。
* [ ] 图片文件可在线查看，其他二进制文件有明确 fallback 与下载入口。
* [ ] 路径树页与文件详情页都能对文件执行下载。
* [ ] 文件列表中的 icon-only 操作具备清晰 tooltip，`last commit` 列可跳转 commit diff 页面。
* [ ] commit 页面可查看文本 diff、图片 diff 与 binary 元信息对比。
* [ ] commit 列表中的 title 可直接进入 commit diff 页面。
* [ ] 上传队列位于独立上传页，文件页只保留 upload 入口按钮。
* [ ] 文件详情页的信息 badge 已收紧高度，不再出现过高的胶囊块。
* [ ] 前端上传支持多次追加队列并展示实时进度，Python remote 上传也支持可控进度反馈。
* [ ] `cd webui && npm run test:coverage`、`cd webui && npm run test:e2e` 与相关 Python unittest 通过。

## Phase 10. 文档、发布、回归矩阵与收尾

### Goal

把 docs、README、构建链路、发布说明和回归矩阵全部收口，形成可持续维护状态。

### Todo

* [ ] 更新 `README.md`、`README_zh.md`，补 `serve`、`frontend` 模式、`HubVaultRemoteApi` 示例。
* [ ] 更新 docs，补 service / remote / web UI 使用说明。
* [ ] 在 README / docs 中明确 base install、`hubvault[api]`、`hubvault[remote]`、`hubvault[full]` 的安装与缺依赖报错语义。
* [ ] 如涉及公开模块和 docstring，执行 `make rst_auto`。
* [ ] 跑并记录：
  - base install 下的 `make unittest`
  - full install 下的 `make unittest`
  - `make package`
  - `make build`
  - `make test_cli`
  - `cd webui && npm run test`
  - `cd webui && npm run build`
* [ ] 检查 sdist / wheel / 可执行文件都包含前端资源。
* [ ] 检查基础安装环境下 `import hubvault`、现有 CLI 与默认 unittest 收集保持稳定。
* [ ] 补充发布注意事项，明确前端构建和静态资源同步流程。

### Checklist

* [ ] 用户可以通过同一个 `hubvault` PyPI 包安装本地、API、remote 全部能力。
* [ ] 用户可以通过同一个可执行文件启动 `api` 或 `frontend` 模式。
* [ ] 文档、CLI help、README、实际行为保持一致。
* [ ] 回归命令均实际跑过并有记录。
