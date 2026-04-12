服务端与 ASGI 启动
==================

这个教程说明建立在本地仓库核心之上的 HTTP 运行时入口：CLI 快速启动、
可导入的 :mod:`hubvault.server` 模块，以及通过 ``uvicorn`` / ``gunicorn``
部署 ASGI 应用。

.. contents:: 本页内容
    :local:

安装服务端 extra
----------------

内建 HTTP server 和 bundled web UI 是可选能力：

.. code-block:: shell

    pip install 'hubvault[api]'

如果没有安装这个 extra，``import hubvault`` 依然成立。只有当你真正调用
``hubvault serve`` 或 :func:`hubvault.server.create_app` 这类 server 能力时，
才会抛出缺依赖错误。

CLI 快速启动
------------

最快的启动方式是 CLI。默认模式是 ``frontend``，会在默认端口 ``9472`` 上同时
提供 JSON API 和浏览器前端。

.. code-block:: shell

    hubvault serve demo-repo \
        --init \
        --token-rw dev-token

该命令会在首次启动时自动创建仓库，并暴露：

* 浏览器界面：``http://127.0.0.1:9472/``
* API 根路径：``http://127.0.0.1:9472/api/v1``

如果你只想暴露 JSON API，可以切到 ``api`` 模式：

.. code-block:: shell

    hubvault serve demo-repo \
        --mode api \
        --init \
        --token-ro read-token \
        --token-rw write-token

在 ``api`` 模式下，OpenAPI 文档会保留在 ``/docs``。

模块入口启动
------------

同一套运行时也可以通过 ``python -m hubvault.server`` 启动：

.. code-block:: shell

    python -m hubvault.server demo-repo \
        --mode frontend \
        --init \
        --token-rw dev-token

当你需要明确指定解释器，或者把启动动作嵌入其它 Python 工具链时，这个入口会
更合适。

可导入的启动方式
----------------

一级模块 :mod:`hubvault.server` 直接暴露了稳定的启动面：

.. code-block:: python

    from pathlib import Path

    from hubvault.server import SERVER_MODE_FRONTEND, ServerConfig, launch

    config = ServerConfig(
        repo_path=Path("demo-repo"),
        mode=SERVER_MODE_FRONTEND,
        token_rw=("dev-token",),
        init=True,
    )
    launch(config)

如果你的 Python 进程本身就要控制启动，而不是 shell out 到 CLI，这就是推荐
入口。

ASGI 部署
---------

同一个应用也可以交给 ASGI server 托管。当没有显式传参时，factory 会从
``HUBVAULT_*`` 环境变量读取配置。

``uvicorn`` 的 application-factory 示例：

.. code-block:: shell

    export HUBVAULT_REPO_PATH=./demo-repo
    export HUBVAULT_SERVE_MODE=frontend
    export HUBVAULT_TOKEN_RW=dev-token

    uvicorn --factory hubvault.server.asgi:create_app \
        --host 127.0.0.1 \
        --port 9472

配合 ASGI worker 的 ``gunicorn`` application-factory 示例：

.. code-block:: shell

    export HUBVAULT_REPO_PATH=./demo-repo
    export HUBVAULT_SERVE_MODE=frontend
    export HUBVAULT_TOKEN_RW=dev-token

    gunicorn \
        --bind 127.0.0.1:9472 \
        --workers 2 \
        -k uvicorn.workers.UvicornWorker \
        'hubvault.server.asgi:create_app()'

Token 与访问模型
----------------

至少要提供一个 token。服务端会拒绝匿名启动，这样本地浏览器、脚本和 remote
client 都会走同一套认证路径。

* ``--token-ro`` 提供只读 API 权限
* ``--token-rw`` 提供读写 API 权限
* 可以重复参数来提供多个 token

下一步
------

如果你要让另一个 Python 进程访问正在运行的服务端，继续看
:doc:`../remote/index_zh`；如果你关注浏览器前端工作流，继续看
:doc:`../webui/index_zh`。
