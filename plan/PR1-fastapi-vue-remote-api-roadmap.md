# PR 1. FastAPI 服务、Vue 内置前端与 Remote API Phase 1-9 执行方案

## Status

- 状态：Proposed
- PR：https://github.com/HansBug/hubvault/pull/1
- 目标分支：`main`
- 工作分支：`dev/api`

## 背景

`hubvault` 当前已经完成本地嵌入式仓库的稳定基线，但仍缺少一层面向“简易前端 + 远程 Python API”的官方服务面。下一阶段要补的不是多租户 Hub，而是一套单仓库、轻部署、可选依赖、仍保持 repo root 自包含的 FastAPI 服务层。

这份文档是一个 post-init 的独立执行计划，因此 phase 编号从 `1` 重新开始，不沿用初始化阶段或 Phase 15 之前的编号。这里的 `Phase 1-9` 专门对应“FastAPI 服务、内置前端、Remote API、打包发布”这一条新工作流。

## 目标

1. 提供基于 FastAPI 的官方服务层，支持“像 Gradio 一样快速起服务”和“标准 ASGI 部署”两类启动方式。
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

### 4. 双启动入口

必须同时支持：

- 快速启动：适合本地临时访问、单机内网、小团队共享、测试环境
- 标准部署：适合 `uvicorn` / 进程管理器 / 容器 / 反向代理场景

快速启动由 CLI 负责，标准部署由 app factory 负责，但两者必须复用同一个 app 构造逻辑。

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
│   ├── asgi.py
│   ├── app.py
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

### CLI 快速启动

推荐默认形式：

```bash
hubvault serve /path/to/repo \
  --host 127.0.0.1 \
  --port 7860 \
  --token-ro readonly-token \
  --token-rw readwrite-token \
  --mode frontend \
  --open-browser
```

只开 API：

```bash
hubvault serve /path/to/repo \
  --host 0.0.0.0 \
  --port 7860 \
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

### 标准 ASGI 部署

推荐：

```bash
export HUBVAULT_REPO_PATH=/path/to/repo
export HUBVAULT_SERVE_MODE=frontend
export HUBVAULT_TOKEN_RW=readwrite-token
uvicorn hubvault.server.asgi:create_app --factory --host 0.0.0.0 --port 7860
```

约束：

- `hubvault.server.asgi:create_app` 必须从环境变量或显式参数读取配置
- CLI 启动和 ASGI factory 启动必须共用同一套 `ServerConfig`

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
    base_url="http://127.0.0.1:7860",
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
- `test/test_phase1.py` 到 `test/test_phase9.py` 中对应本次计划的集成回归文件
- 新增服务端 PyInstaller smoke test，用于验证静态资源被打进可执行文件

建议至少覆盖：

- `hubvault serve --mode api`
- `hubvault serve --mode frontend`
- `make build` 后的可执行文件可启动服务
- 可执行文件在 `frontend` 模式下能返回首页和 `/api/v1/meta/service`

## 打包与发布设计

### 同一个 PyPI 包

落地要求：

- 所有 Python 代码继续由 `setup.py` 的同一个 `hubvault` 包发布
- `extras_require` 继续由 `requirements-*.txt` 自动生成
- 需要额外新增 `requirements-full.txt`
- 不创建新的发布名

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

- `make unittest`
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

* [ ] 明确本计划是 post-init 独立 phase，编号从 `1` 开始。
* [ ] 冻结 `api` / `frontend` 两种模式，并规定默认值为 `frontend`。
* [ ] 明确 `frontend` 的含义是 “API + frontend 同时提供”。
* [ ] 冻结 `hubvault serve` 的职责边界与 app factory 的职责边界。
* [ ] 冻结 `HubVaultRemoteApi` 公开命名，并决定是否提供 `HubVaultRemoteAPI` 别名。
* [ ] 冻结“同一个 PyPI 包、同一个可执行文件”原则。
* [ ] 冻结 API、frontend、remote 共用同一 FastAPI app 的原则。

### Checklist

* [ ] 文档中不再出现 `api+frontend` 这种旧模式命名。
* [ ] `frontend` 默认模式已经在 CLI 和部署说明里一致体现。
* [ ] 命名、模式和范围足够稳定，可以支撑后续直接实现。

## Phase 2. 依赖拆分、目录落位与打包骨架

### Goal

把依赖、目录与构建骨架搭出来，确保实现开始后不会在包结构上反复返工。

### Todo

* [ ] 新增 `requirements-api.txt`、`requirements-remote.txt`、`requirements-full.txt`。
* [ ] 新增 `hubvault/server/`、`hubvault/remote/`、`hubvault/entry/server.py` 骨架。
* [ ] 新增 `webui/` 前端源码目录与 `hubvault/server/static/webui/` 静态产物目录。
* [ ] 补齐 `setup.py` / `MANIFEST.in` / 其它打包配置，使前端静态资源能进入包产物。
* [ ] 为 `make build` 准备静态资源收集方案。
* [ ] 为 `webui` 准备 `npm run test`、`npm run build`、资源同步脚本。

### Checklist

* [ ] extras 仍然挂在同一个 `hubvault` 包上。
* [ ] wheel / sdist / PyInstaller 的资源收集路径已经定清。
* [ ] 前端源码与前端产物职责分离。

## Phase 3. 服务配置、启动入口与鉴权骨架

### Goal

打通服务最小骨架，让 `hubvault serve` 和 ASGI factory 都能起同一套 app，并完成 token 鉴权基线。

### Todo

* [ ] 实现 `server/config.py`，统一承载 repo path、mode、token、host、port 等配置。
* [ ] 实现 `server/asgi.py` 与 `server/app.py` 的 app factory。
* [ ] 实现 `entry/server.py` 并把 `serve` 注册到 CLI。
* [ ] 实现 `server/auth.py` 与权限依赖。
* [ ] 实现 `server/exception_handlers.py`。
* [ ] 实现 `/api/v1/meta/service` 和 `/api/v1/meta/whoami`。
* [ ] 增加 `test/server/test_config.py`、`test/server/test_auth.py`、`test/entry/test_server.py`。

### Checklist

* [ ] `hubvault serve --mode api` 可以成功起服务。
* [ ] `hubvault serve --mode frontend` 可以成功起服务。
* [ ] `ro` / `rw` token 行为已可区分。
* [ ] 无 token、坏 token、权限不足的错误语义稳定。

## Phase 4. 只读 API 路由与下载闭环

### Goal

先完成只读 HTTP 闭环，让 repo 浏览、历史查看、文件下载、range 读取全部可用。

### Todo

* [ ] 实现 `repo`、`content`、`refs`、`history` 的只读路由。
* [ ] 实现 schema / serde 第一版，覆盖所有只读模型。
* [ ] 实现单文件下载路由。
* [ ] 实现 range 读取路由。
* [ ] 实现 `snapshot-plan` 路由。
* [ ] 增加 `test/server/test_routes_repo.py`、`test/server/test_routes_content.py`、`test/server/test_routes_refs.py`、`test/server/test_routes_history.py`。

### Checklist

* [ ] `ro` token 可以完整浏览 repo 与历史。
* [ ] 单文件下载路径仍保留 repo 相对路径后缀。
* [ ] range 读取与本地 API 行为一致。
* [ ] 快照下载计划可被 remote client 消费。
* [ ] `make unittest` 通过。

## Phase 5. Remote 只读 client、错误映射与缓存

### Goal

做出可用的只读 `HubVaultRemoteApi`，把 HTTP 协议包装回本地风格接口。

### Todo

* [ ] 实现 `remote/client.py` HTTP 传输层。
* [ ] 实现 `remote/serde.py` 和 `remote/errors.py`。
* [ ] 实现 `remote/cache.py`。
* [ ] 对齐 `repo_info`、`get_paths_info`、`list_repo_tree`、`list_repo_files`、`list_repo_commits`、`list_repo_refs`、`list_repo_reflog`、`read_bytes`、`read_range`、`hf_hub_download`、`snapshot_download`。
* [ ] 实现 `open_file()` 的远程文件对象包装。
* [ ] 增加 `test/remote/test_api.py`、`test/remote/test_serde.py`、`test/remote/test_cache.py`、`test/remote/test_errors.py`。

### Checklist

* [ ] remote 只读方法返回模型字段与本地 API 对齐。
* [ ] remote 异常映射稳定，不泄漏底层 HTTP client 细节。
* [ ] 远程下载缓存与快照缓存路径语义稳定。
* [ ] `make unittest` 通过。

## Phase 6. Vue 前端只读壳与静态托管

### Goal

先交付一套只读 Web UI，让用户在浏览器中登录、浏览、查看历史，而无需先补复杂写操作。

### Todo

* [ ] 建立 `webui/` 的 Vue 3 + Element Plus + Vite 骨架。
* [ ] 实现 token 登录页与全局请求封装。
* [ ] 实现 Overview、Files、Commits、Refs 页面。
* [ ] 实现 `ro` / `rw` 权限门禁与导航控制。
* [ ] 实现 `frontend` 模式下的静态资源托管和 fallback。
* [ ] 增加 `webui/tests/unit/`、`webui/tests/components/`、`webui/tests/e2e/`。
* [ ] 增加 `test/server/test_ui.py`，验证 `api` 模式不暴露 UI，`frontend` 模式暴露 UI。

### Checklist

* [ ] `frontend` 模式可以正常打开首页。
* [ ] 前端所有读取都经由 `/api/v1/**`。
* [ ] `ro` 用户看不到或无法触发写操作入口。
* [ ] 前端构建产物能够被 FastAPI 正确托管。

## Phase 7. 写路径 API 与 Remote 写能力

### Goal

把远程写路径打通，让 server 与 remote client 都能完成核心 repo 修改动作。

### Todo

* [ ] 实现 `create_commit` 的 multipart manifest 协议。
* [ ] 实现 `upload_file`、`create_branch`、`delete_branch`、`create_tag`、`delete_tag`。
* [ ] 实现 `merge`、`reset_ref`、`delete_file`、`delete_folder`。
* [ ] 实现 `upload_folder`、`upload_large_folder` 的首版 multipart 协议。
* [ ] 对齐 `HubVaultRemoteApi` 的写方法。
* [ ] 为 `CommitOperationAdd` 的路径 / bytes / fileobj 三种输入写完整测试。
* [ ] 增加 `test/server/test_routes_writes.py` 与 remote 写路径测试。

### Checklist

* [ ] `rw` token 可以完成核心写操作。
* [ ] `ro` token 在所有写路径上被稳定拒绝。
* [ ] merge 冲突能通过 HTTP 与 remote 保持结构化返回。
* [ ] `make unittest` 通过。

## Phase 8. 前端写操作、维护操作与可执行文件闭环

### Goal

补齐浏览器端常用写操作和 maintenance 操作，并确认打包后的可执行文件可独立提供完整服务。

### Todo

* [ ] Vue 前端接入上传文件、上传目录、delete、commit、branch/tag、merge、reset。
* [ ] 实现维护 API：`quick_verify`、`full_verify`、`get_storage_overview`、`gc`、`squash_history`。
* [ ] Vue 前端接入 verify / storage / gc / squash history 页面与操作对话框。
* [ ] 扩展 `make test_cli` 或新增 smoke 测试，验证可执行文件的 `serve --mode frontend`。
* [ ] 验证 PyInstaller 产物包含前端静态资源。
* [ ] 增加前端 e2e 与 Python 端到端联测。

### Checklist

* [ ] 浏览器端可完成常见 repo 维护动作。
* [ ] 可执行文件可直接启动完整 `frontend` 模式。
* [ ] `/` 与 `/api/v1/meta/service` 在可执行文件模式下均可访问。
* [ ] `make unittest`、`make build`、`make test_cli` 通过。

## Phase 9. 文档、发布、回归矩阵与收尾

### Goal

把 docs、README、构建链路、发布说明和回归矩阵全部收口，形成可持续维护状态。

### Todo

* [ ] 更新 `README.md`、`README_zh.md`，补 `serve`、`frontend` 模式、`HubVaultRemoteApi` 示例。
* [ ] 更新 docs，补 service / remote / web UI 使用说明。
* [ ] 如涉及公开模块和 docstring，执行 `make rst_auto`。
* [ ] 跑并记录：
  - `make unittest`
  - `make package`
  - `make build`
  - `make test_cli`
  - `cd webui && npm run test`
  - `cd webui && npm run build`
* [ ] 检查 sdist / wheel / 可执行文件都包含前端资源。
* [ ] 补充发布注意事项，明确前端构建和静态资源同步流程。

### Checklist

* [ ] 用户可以通过同一个 `hubvault` PyPI 包安装本地、API、remote 全部能力。
* [ ] 用户可以通过同一个可执行文件启动 `api` 或 `frontend` 模式。
* [ ] 文档、CLI help、README、实际行为保持一致。
* [ ] 回归命令均实际跑过并有记录。
