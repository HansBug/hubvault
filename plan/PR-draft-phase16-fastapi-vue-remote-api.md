# PR TBD. Phase 16-20 FastAPI 服务、Vue 内置前端与 Remote API 执行方案

## Status

- 状态：Proposed
- PR：待创建，创建后回填
- 目标分支：`main`
- 工作分支：`dev/api`

## 背景

`hubvault` 当前已经完成 Phase 15 的本地嵌入式仓库闭环，但还没有面向远程访问的官方服务层。接下来的增量目标不是把仓库改造成多租户 Hub，而是在不破坏“repo root 是唯一真相、SQLite + 文件系统仍是底层事实”的前提下，补一层可选安装的 HTTP 服务、内置简易前端，以及一套基于同一 REST 协议的 Python remote client。

这套能力的定位必须保持克制：

- 它是单仓库、单站点、轻部署、可选依赖的远程访问层。
- 它不是新的 metadata truth-store，也不是独立云端 Hub 产品。
- 它不应把前端或 remote client 的运行前提强加给纯本地用户。

## 目标

1. 提供 `hubvault[api]` 可选依赖，使用户可以把一个本地 repo 路径以 FastAPI 服务方式暴露出来。
2. 提供内置前端，和 API 同进程启动，前端只通过 HTTP API 操作 repo，不直连 backend 私有逻辑。
3. 提供 `hubvault[remote]` 可选依赖，使远程站点可以通过 `HubVaultRemoteApi` 获得与 `HubVaultApi` 近乎一致的调用体验。
4. 令鉴权模型先收敛到两种 token 权限：`ro` 与 `rw`。
5. 保持当前跨平台与 Python `3.7`-`3.14` 兼容承诺，不让 Node、额外数据库、对象存储、宿主注册表等成为运行正确性的前提。

## 非目标

- 不做多租户、多 repo 聚合、组织/用户系统、OAuth、SSO。
- 不把 PR、review、讨论、通知流等 GitHub/GitLab 式协作产品能力拉进来。
- 不让服务端持久化自己的 repo 外部真相层。
- 不做首版 WebSocket、SSE 实时进度推送。
- 不在首版引入复杂后台任务队列、worker 池或异步对象搬运系统。

## 关键设计约束

### 1. 进程模型

- 一个 `hubvault serve <repo_path>` 进程只绑定一个 repo root。
- 服务端不直接操作 `RepositoryBackend` 私有细节，对外路由统一走 `HubVaultApi` 语义层。
- 现有 `repo.lock`、短连接 SQLite、rollback-only 恢复语义保持不变。
- API 与前端都挂在同一个 FastAPI app 上，不另开第二个服务、第二个端口或第二套后端接口。
- 启动时可以选择只启 API，或同时启 API + Vue 前端。

### 2. 依赖拆分

- 基础安装 `pip install hubvault` 继续只提供本地 API 与 CLI。
- `requirements-api.txt` 承载 FastAPI 服务端依赖。
- `requirements-remote.txt` 承载 Python remote client 依赖。
- 前端构建依赖放在独立 `webui/package.json`，仅参与构建，不成为 Python 运行时依赖。

### 3. 前端技术路线

- 前端采用 `Vue 3`。
- 组件库优先选 `Element Plus`，原因是成熟、扁平化风格足够稳定、表格/树/表单/对话框能力现成、样板代码少。
- 构建工具使用 `Vite`。
- 运行时只分发构建产物，不要求目标机器安装 Node。
- 前端只消费 `/api/v1/**`，不允许绕过 API 直接嵌入 Python 模板逻辑执行业务操作。

### 4. Remote public naming

- 规范名称保持和现有 `HubVaultApi` 一致的缩写风格，首选 `HubVaultRemoteApi`。
- 如果后续确实需要兼容 `HubVaultRemoteAPI` 这种更显式的命名，应只做薄别名，不新增第二套实现。
- 具体实现模块放到新包路径，不把业务逻辑塞进 `__init__.py`。

### 5. 安全边界

- token 只分 `ro` 与 `rw` 两级。
- `ro` 可调用读接口与查看 UI，只能做 repo 浏览、历史查看、下载、校验结果读取等无副作用能力。
- `rw` 在 `ro` 基础上额外拥有写接口与维护接口能力。
- token 配置属于服务进程运行时配置，不写入 repo correctness-critical truth。

## 建议目录布局

```text
hubvault/
├── api.py
├── remote/
│   ├── api.py
│   ├── client.py
│   ├── serde.py
│   └── errors.py
├── server/
│   ├── asgi.py
│   ├── app.py
│   ├── config.py
│   ├── auth.py
│   ├── deps.py
│   ├── schemas.py
│   ├── exception_handlers.py
│   ├── routes/
│   │   ├── meta.py
│   │   ├── repo.py
│   │   ├── refs.py
│   │   ├── history.py
│   │   ├── content.py
│   │   ├── writes.py
│   │   ├── maintenance.py
│   │   └── ui.py
│   └── static/
│       └── webui/   # Vite 构建产物
├── entry/
│   └── server.py
└── ...
webui/
├── package.json
├── vite.config.ts
├── src/
│   ├── main.ts
│   ├── router.ts
│   ├── api/
│   ├── composables/
│   ├── views/
│   ├── components/
│   └── styles/
└── ...
test/
├── server/
├── remote/
└── entry/
```

## Python extras 设计

### `requirements-api.txt`

用途：

- FastAPI app
- ASGI 启动
- multipart 上传
- 服务端 JSON/streaming 路由支持

约束：

- 版本需要显式卡在仍支持 Python `3.7` 的最后兼容区间。
- 不使用把更高 Python 版本作为硬前提的新语法或新运行时特性。
- 不让 `uvloop`、`httptools` 之类平台相关加速包成为 correctness 必需项。

### `requirements-remote.txt`

用途：

- HTTP client
- 远程下载缓存与流式传输支持

约束：

- 版本同样要明确保持 Python `3.7` 可安装。
- remote client 只能依赖公开 HTTP 协议，不得共享服务端内部模块。

## CLI 入口设计

新增命令需要同时覆盖两类使用方式：

- Gradio-like 快速启动：命令行给定 repo 路径、token、端口，必要时自动打开浏览器。
- 正经部署：允许通过 ASGI app factory / 环境变量方式挂到 `uvicorn`、systemd、supervisor、容器入口等部署流程。

快速启动建议：

```bash
hubvault serve /path/to/repo \
  --host 127.0.0.1 \
  --port 7860 \
  --token-ro readonly-token \
  --token-rw readwrite-token \
  --mode api+frontend \
  --open-browser
```

只启 API 的快速启动建议：

```bash
hubvault serve /path/to/repo \
  --host 0.0.0.0 \
  --port 7860 \
  --token-rw readwrite-token \
  --mode api
```

标准 ASGI 部署建议：

```bash
export HUBVAULT_REPO_PATH=/path/to/repo
export HUBVAULT_TOKEN_RW=readwrite-token
export HUBVAULT_SERVE_MODE=api
uvicorn hubvault.server.asgi:create_app --factory --host 0.0.0.0 --port 7860
```

建议参数：

- `path`：绑定的 repo root，缺省时继承全局 `-C`
- `--host`
- `--port`
- `--token-ro`，可重复
- `--token-rw`，可重复
- `--mode`，取值 `api` 或 `api+frontend`
- `--default-revision`
- `--init`，当目标路径还不是 repo 时允许初始化
- `--initial-branch`
- `--large-file-threshold`
- `--open-browser`

行为约束：

- 未安装 `hubvault[api]` 时，命令应明确报错并提示安装额外依赖。
- `--init` 未显式给出时，默认要求 repo 已存在。
- `api` 模式只注册 API 路由和 API 文档。
- `api+frontend` 模式在同一个 FastAPI app 中额外注册 Vue 静态资源与前端 fallback。
- 前端与 API 同进程、同 host、同 port、同认证体系启动。

## 路由树与部署模式

同一套 FastAPI app 根据 mode 注册不同路由：

```text
api mode:
/
└── api/
    └── v1/
        ├── meta/
        ├── repo/
        ├── content/
        ├── refs/
        ├── history/
        ├── writes/
        └── maintenance/

api+frontend mode:
/
├── api/
│   └── v1/
│       ├── meta/
│       ├── repo/
│       ├── content/
│       ├── refs/
│       ├── history/
│       ├── writes/
│       └── maintenance/
├── assets/
│   └── ... Vue/Vite static files ...
└── {frontend route fallback}
```

约束：

- Vue 前端必须调用同一个 app 下的 `/api/v1/**`。
- 不允许额外启动 Vite dev server 作为运行期依赖。
- 开发期可以用 Vite dev server 做前端热更新，但最终打包、测试和发布路径必须走 FastAPI 托管的静态资源。
- `api` 与 `api+frontend` 只影响路由注册，不影响 API 协议本身。

## 鉴权与权限模型

### token 来源

- 启动参数直接传入的 `--token-ro` / `--token-rw`
- 后续可以增补 `--token-file`，但不作为首版 MVP 前提

### 鉴权方式

- Python remote client 使用 `Authorization: Bearer <token>`
- Vue 前端首次进入站点时显示 token 输入页
- 前端把 token 保存在 `sessionStorage`
- 前端所有 API 调用统一带 `Authorization` 头
- 服务端提供 `GET /api/v1/meta/whoami` 用于验证 token 和返回当前 role

### 权限矩阵

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

`rw` 额外允许：

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

## REST API 版本与返回约束

- API 统一挂在 `/api/v1`
- 服务端返回 `X-HubVault-Api-Version: 1`
- remote client 初始化时先探测 `/api/v1/meta/service`
- 所有错误统一返回结构化 JSON：

```json
{
  "error": {
    "type": "RevisionNotFoundError",
    "message": "Revision 'dev' was not found.",
    "details": {}
  }
}
```

- `type` 必须可以映射到现有 `hubvault.errors` 公开异常
- dataclass 模型不直接把内部 Python 对象裸暴露给 FastAPI，统一走显式 schema / serde 层

## REST 路由映射

| `HubVaultApi` 方法 | HTTP | 路由 | 说明 |
| --- | --- | --- | --- |
| `create_repo` | `POST` | `/api/v1/repo` | 仅 `rw` |
| `repo_info` | `GET` | `/api/v1/repo` | `revision` 查询参数 |
| `get_paths_info` | `POST` | `/api/v1/content/paths-info` | body 传路径数组 |
| `list_repo_tree` | `GET` | `/api/v1/content/tree` | `path_in_repo`、`recursive` |
| `list_repo_files` | `GET` | `/api/v1/content/files` | 只返回路径列表 |
| `list_repo_commits` | `GET` | `/api/v1/history/commits` | `revision`、`formatted` |
| `list_repo_refs` | `GET` | `/api/v1/refs` | `include_pull_requests` |
| `create_branch` | `POST` | `/api/v1/refs/branches` | 仅 `rw` |
| `delete_branch` | `DELETE` | `/api/v1/refs/branches/{branch}` | 仅 `rw` |
| `create_tag` | `POST` | `/api/v1/refs/tags` | 仅 `rw` |
| `delete_tag` | `DELETE` | `/api/v1/refs/tags/{tag}` | 仅 `rw` |
| `list_repo_reflog` | `GET` | `/api/v1/history/reflog/{ref_name}` | `limit` |
| `read_bytes` | `GET` | `/api/v1/content/blob/{path:path}` | `application/octet-stream` |
| `read_range` | `GET` | `/api/v1/content/blob/{path:path}/range` | `start`、`length` |
| `hf_hub_download` | `GET` | `/api/v1/content/download/{path:path}` | `revision` 查询参数 |
| `snapshot_download` | `POST` | `/api/v1/content/snapshot-plan` | 返回 manifest，由 client 逐文件拉取 |
| `create_commit` | `POST` | `/api/v1/writes/commit` | multipart manifest + file parts |
| `merge` | `POST` | `/api/v1/writes/merge` | 仅 `rw` |
| `upload_file` | `POST` | `/api/v1/writes/upload-file` | multipart |
| `upload_folder` | `POST` | `/api/v1/writes/upload-folder` | multipart，支持相对路径清单 |
| `upload_large_folder` | `POST` | `/api/v1/writes/upload-large-folder` | multipart / 打包上传 |
| `delete_file` | `POST` | `/api/v1/writes/delete-file` | 仅 `rw` |
| `delete_folder` | `POST` | `/api/v1/writes/delete-folder` | 仅 `rw` |
| `reset_ref` | `POST` | `/api/v1/writes/reset-ref` | 仅 `rw` |
| `quick_verify` | `POST` | `/api/v1/maintenance/quick-verify` | `ro` 可读 |
| `full_verify` | `POST` | `/api/v1/maintenance/full-verify` | `ro` 可读 |
| `get_storage_overview` | `GET` | `/api/v1/maintenance/storage-overview` | `ro` 可读 |
| `gc` | `POST` | `/api/v1/maintenance/gc` | 仅 `rw` |
| `squash_history` | `POST` | `/api/v1/maintenance/squash-history` | 仅 `rw` |

## 写路径协议设计

### `create_commit`

`create_commit()` 是最需要额外约束的远程接口，因为 `CommitOperationAdd` 可以接收本地文件路径、`bytes` 或 file object。远程协议需要保留这个调用手感，但不能把这些 Python 对象直接 JSON 化。

建议协议：

- 请求使用 `multipart/form-data`
- `spec` part 为 JSON
- 每个 add 操作对应一个文件 part
- copy / delete 操作只出现在 `spec` JSON 中

`spec` 样式：

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

这样 remote client 可以继续接受：

- `CommitOperationAdd("a.txt", "/local/file")`
- `CommitOperationAdd("a.txt", b"bytes")`
- `CommitOperationAdd("a.txt", fileobj)`

并在客户端本地归一化为 multipart 上传。

### `upload_folder` / `upload_large_folder`

首版建议分两类输入：

- Python remote client：客户端扫描本地目录后按相对路径清单 + 多文件 multipart 提交，必要时在 Phase 18 后引入 tar 打包模式降低大目录请求开销
- Vue 前端：使用浏览器 `webkitdirectory` 或多文件上传，并通过 `webkitRelativePath` 传递相对路径

这样可以先避免引入额外服务端解包逻辑，再根据性能和浏览器兼容性决定是否追加 tar 流模式。

## 内置前端设计

### 前端目标

- 手感接近 HF 的 repo 浏览体验
- 页面简洁、扁平、组件复用优先
- 尽量少写胶水代码
- 所有状态只围绕当前单 repo 服务实例

### 页面范围

建议首版页面：

- 登录页：输入 token，探测权限等级
- Repo Overview：基础信息、默认分支、HEAD、storage overview 摘要
- Files：目录树、文件表、下载、文本预览、二进制信息展示
- Commits：历史列表、commit message/body、parents、时间信息
- Refs：branch/tag 浏览与创建删除
- Write Actions：上传文件、上传目录、删除、commit、merge、reset
- Maintenance：quick verify、full verify、gc、squash history

### Vue 结构建议

- `vue-router` 负责页面切换
- 不强制引入 Pinia；全局状态先用 composable + `provide/inject` 收敛
- 通用 API 请求层统一处理：
  - token 注入
  - 错误提示
  - 401 跳转登录
  - `ro` / `rw` 权限门禁
- 核心通用组件：
  - file tree / breadcrumb
  - commit list
  - ref list
  - upload dialog
  - action confirm dialog

### 视觉方向

- 扁平化浅色主题为默认
- 以信息密度和可读性优先，不做大面积渐变或重动画
- 利用 `Element Plus` 现成 tokens 做轻量主题覆盖，不单独引入复杂设计系统

## Remote Client 设计

### 定位

`HubVaultRemoteApi` 的目标不是重新发明一套远程 SDK，而是让远程站点在方法名、返回模型、错误类型上尽量贴近 `HubVaultApi`。

### 初始化形态

建议：

```python
from hubvault.remote.api import HubVaultRemoteApi

api = HubVaultRemoteApi(
    base_url="http://127.0.0.1:7860",
    token="readwrite-token",
    revision="main",
)
```

初始化参数建议：

- `base_url`
- `token`
- `revision`
- `timeout`
- `cache_dir`

### 行为对齐原则

- 方法名尽量与 `HubVaultApi` 完整对齐
- 返回值复用现有 `hubvault.models`
- 错误抛出复用现有 `hubvault.errors`
- `hf_hub_download()` / `snapshot_download()` 在 remote 侧返回本地缓存路径，并尽量保留 repo 相对路径后缀
- `open_file()` 通过本地 `SpooledTemporaryFile` 或命名临时文件封装成可读 file object

### 特殊差异点

- `repo_path` 不再存在，改为 `base_url`
- remote 下载缓存属于 client 本地临时/缓存层，不是 repo truth
- `snapshot_download()` 远程侧不依赖服务端先打整包压缩；优先走 manifest + 按文件下载

## 模型与序列化约束

- `server/schemas.py` 提供明确的请求/响应 schema
- `remote/serde.py` 负责 schema 到 dataclass 的转换
- 对于 `datetime` 字段统一使用 ISO 8601 字符串
- `CommitInfo` 这类带 `str` 兼容行为的模型，必须通过显式构造恢复，不依赖 FastAPI 自动 dataclass 序列化
- `RepoFile` / `RepoFolder` 联合返回需要有稳定 discriminator，避免 remote 端猜类型

## 错误映射约束

服务端需要把公开异常映射为稳定 HTTP 状态码：

- `RepositoryNotFoundError` -> `404`
- `RevisionNotFoundError` -> `404`
- `EntryNotFoundError` -> `404`
- `ConflictError` -> `409`
- `UnsupportedPathError` -> `422`
- `HubVaultValidationError` -> `422`
- `IntegrityError` -> `500`
- `VerificationError` -> `500`

remote client 读取 `error.type` 后，应重新抛出相应公开异常，而不是暴露 HTTP client 自身异常给业务代码。

## 测试与回归设计

新增测试树建议：

- `test/server/test_config.py`
- `test/server/test_auth.py`
- `test/server/test_schemas.py`
- `test/server/test_routes_meta.py`
- `test/server/test_routes_content.py`
- `test/server/test_routes_refs.py`
- `test/server/test_routes_history.py`
- `test/server/test_routes_writes.py`
- `test/server/test_routes_maintenance.py`
- `test/server/test_ui.py`
- `test/remote/test_api.py`
- `test/remote/test_serde.py`
- `test/entry/test_server.py`
- `test/test_phase16.py`
- `test/test_phase17.py`
- `test/test_phase18.py`

测试原则：

- server 测试通过真实 FastAPI app + `TestClient` 或等价 ASGI 客户端执行
- remote 测试只走 HTTP 协议，不 monkeypatch 私有 backend
- 端到端测试要覆盖 `ro` / `rw` 权限差异
- 上传/下载测试优先使用真实临时目录和真实文件

## 文档与发布要求

- `README.md` / `README_zh.md` 增加 optional extras、`hubvault serve`、remote client 简要示例
- docs 增加 API service 和 remote client 页面
- 如果新增公共模块，补 `make rst_auto`
- packaging 变化需要跑 `make package`

## MVP Cut

MVP 建议收敛为：

- `hubvault[api]` 与 `hubvault serve`
- Bearer token 鉴权与 `ro` / `rw` 权限模型
- 只读 API 全量打通
- Vue UI 的登录、概览、文件浏览、提交历史、refs 浏览
- `HubVaultRemoteApi` 的只读能力对齐
- 单文件上传、基础 commit、branch/tag 创建删除

这样可以先交付“可浏览、可下载、可基础写入”的一套轻服务闭环，再继续补复杂写路径和维护路径。

## Deferred After MVP

- tar 流目录上传优化
- 并发文件下载与断点续传
- 浏览器端更完整的目录上传兼容性兜底
- OpenAPI 自动生成的 remote client 辅助代码
- 多 repo 路由复用
- 细粒度操作审计、token 过期、token 描述信息
- WebSocket/SSE 进度
- UI 深色主题和更复杂的交互细节

## Phase 16. 服务骨架、依赖切分与协议冻结

### Goal

冻结服务边界、依赖边界、鉴权模型、HTTP 契约和前端/remote 的公共约束，避免后续实现阶段反复改协议。

### Todo

* [ ] 新增 `requirements-api.txt` 与 `requirements-remote.txt`，并明确各自只承载什么依赖。
* [ ] 确定 `hubvault/server/`、`hubvault/remote/`、`webui/` 的目录职责。
* [ ] 冻结 `hubvault serve` CLI 入口参数及默认行为。
* [ ] 冻结快速启动与标准 ASGI 部署两种服务入口。
* [ ] 冻结 `api` / `api+frontend` 两种启动模式。
* [ ] 冻结 Bearer token + `ro` / `rw` 权限模型。
* [ ] 冻结 `/api/v1` 基础路由、错误 JSON 结构、版本探测接口。
* [ ] 冻结 remote client 的初始化参数与方法对齐原则。
* [ ] 冻结 Vue 3 + Element Plus + Vite 的前端实现路线。
* [ ] 明确不把业务实现塞进 `__init__.py`，只保留薄导出。

### Checklist

* [ ] 依赖拆分后，纯本地用户仍可只安装基础包。
* [ ] 运行时不要求 Node。
* [ ] 前端只能通过 API 操作，不存在第二套后门写路径。
* [ ] `api` 与 `api+frontend` 模式只共用一个 FastAPI app 和一棵路由树。
* [ ] Remote API 的命名、模型、异常与现有公开表面兼容。
* [ ] Phase 16 文档足够支撑后续直接开工实现。

## Phase 17. FastAPI 服务端与只读 HTTP 闭环

### Goal

先做出稳定的只读服务闭环，让 repo 浏览、历史查看、下载和 remote 只读调用全部可用。

### Todo

* [ ] 实现 `server/config.py` 与 app factory。
* [ ] 实现 token 校验依赖、权限依赖和公共异常处理。
* [ ] 实现 `meta`、`repo`、`content`、`history`、`refs` 只读路由。
* [ ] 实现文件流式下载和 range 读取路由。
* [ ] 实现 `snapshot-plan` 接口，返回 filtered manifest 而不是整包压缩流。
* [ ] 实现 schema / serde 第一版，覆盖只读模型。
* [ ] 实现 `HubVaultRemoteApi` 只读方法。
* [ ] 增加服务端只读路由与 remote 只读 client 测试。

### Checklist

* [ ] `ro` token 可以完整浏览 repo、列历史、列 refs、下载文件、下载快照。
* [ ] remote 只读 client 返回的模型与本地 `HubVaultApi` 对齐。
* [ ] 文件下载路径仍保留 repo 相对路径后缀。
* [ ] `open_file()`、`read_bytes()`、`read_range()` 都能经 HTTP 正确工作。
* [ ] 无效 token 返回 `401`，权限不足返回 `403`。
* [ ] `make unittest` 通过。

## Phase 18. Vue 前端与核心写路径

### Goal

把站点从“能远程读取”扩成“能在浏览器里完成常见 repo 操作”的最小完整产品。

### Todo

* [ ] 建立 `webui/` 项目骨架，接入 Vue 3、Vite、Element Plus。
* [ ] 实现登录页、全局 token 管理、401/403 错误回退。
* [ ] 实现概览页、文件页、提交历史页、refs 页。
* [ ] 实现基础写路径 API：`create_commit`、`upload_file`、`create_branch`、`delete_branch`、`create_tag`、`delete_tag`。
* [ ] 为 `create_commit` 的 multipart manifest 协议补上服务端实现。
* [ ] Vue 前端接入文件上传、commit、branch/tag 操作。
* [ ] 把 `webui` 构建产物打包进 `hubvault/server/static/webui/`，并由 FastAPI 统一托管。
* [ ] 在 `api+frontend` 模式下注册 Vue 静态资源与前端 fallback，在 `api` 模式下不注册 UI。
* [ ] 增加 UI 集成测试与 CLI `serve` 启动 smoke test。

### Checklist

* [ ] 前端无需额外后端模板逻辑即可完成浏览与基础写入。
* [ ] `rw` token 可以完成单文件上传、基础 commit、分支和标签操作。
* [ ] `ro` token 在 UI 中看不到可执行写操作，或执行时被明确拒绝。
* [ ] 构建产物能够随 Python 包一起分发。
* [ ] `api` 模式不暴露 UI routes，`api+frontend` 模式不改变 `/api/v1` 协议。
* [ ] `make unittest` 通过。

## Phase 19. 扩展写路径、维护操作与 Remote API 对齐

### Goal

补齐高价值写路径和 maintenance 能力，让 remote client 与浏览器都能完成常见管理动作。

### Todo

* [ ] 实现 `upload_folder`、`upload_large_folder`、`delete_file`、`delete_folder`、`merge`、`reset_ref` HTTP 路由。
* [ ] 实现 `quick_verify`、`full_verify`、`get_storage_overview`、`gc`、`squash_history` HTTP 路由。
* [ ] Vue 前端接入目录上传、删除、merge、reset、verify、gc、squash-history。
* [ ] `HubVaultRemoteApi` 对齐剩余公开方法。
* [ ] 为目录上传、merge 冲突、维护接口增加端到端测试。
* [ ] 评估目录上传 multipart 是否足够，必要时补 tar 模式但不阻塞其它能力落地。

### Checklist

* [ ] remote client 已覆盖绝大多数 `HubVaultApi` 公开方法。
* [ ] 浏览器端可以完成常见 maintenance 动作。
* [ ] merge 冲突在 HTTP 与 UI 中保持结构化展示。
* [ ] 维护操作仍遵守现有 rollback-only 与 repo lock 语义。
* [ ] `make unittest` 通过。

## Phase 20. 文档、打包、兼容性与发布收尾

### Goal

收尾文档、构建链路、额外依赖说明和兼容性验证，确保这套能力能被正常发布和维护。

### Todo

* [ ] 更新 `README.md`、`README_zh.md`、docs 使用示例。
* [ ] 为服务端和 remote client 补公开 API 文档。
* [ ] 如公开 docstring / 模块导出结构变化，执行 `make rst_auto`。
* [ ] 验证 `setup.py` extras 与打包产物包含前端静态资源。
* [ ] 跑 `make unittest` 与 `make package`。
* [ ] 明确记录前端构建命令、静态资源同步方式与 release 注意事项。

### Checklist

* [ ] 用户能按文档安装 `hubvault[api]` 与 `hubvault[remote]`。
* [ ] 发布包里包含前端构建产物。
* [ ] docs、README、CLI help、Python 示例彼此一致。
* [ ] 打包与测试命令均实际跑过并记录结果。
