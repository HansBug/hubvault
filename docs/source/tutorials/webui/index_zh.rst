内建 Web UI
===========

这个教程聚焦于打包在 Python 包和独立可执行文件中的浏览器前端。

.. contents:: 本页内容
    :local:

Web UI 的前提
-------------

浏览器前端和 JSON API 共用同一个内建 HTTP 运行时，因此需要安装 server extra：

.. code-block:: shell

    pip install 'hubvault[api]'

然后以前端模式启动，并提供一个读写 token：

.. code-block:: shell

    hubvault serve demo-repo --init --token-rw dev-token

接着打开 ``http://127.0.0.1:9472/``。

登录与直连 token 入口
---------------------

登录页支持手工输入 bearer token。对于本地临时访问，也可以直接打开类似下面的
链接：

.. code-block:: text

    http://127.0.0.1:9472/repo/overview?token=dev-token

前端会消费这个 query token，把它存入当前浏览器 session，然后跳转回干净路由，
避免 token 长时间留在 URL 里。

浏览器前端提供什么
------------------

内建 UI 的定位是仓库操作控制台。目前它覆盖：

* 带 README 渲染、仓库摘要和最近提交的 overview 页
* 带自然排序、文件类型图标、直接下载动作和独立文件详情页的文件树
* 面向文本/代码、Markdown、图像、音频、视频以及安全 binary fallback 的 blob 页
* commit detail 页，支持文本 diff、媒体预览，以及仅对不可展示 binary 变更显示元信息卡
* refs、history、storage overview 和上传工作流

上传流程
--------

上传队列位于从 Files 页面进入的独立上传页。你可以多次追加文件、检查待上传
队列、让 UI 自动生成 placeholder commit message，或者在提交前手工覆盖。

大文件上传期间，页面会持续显示当前阶段和字节进度，因此在去重检查、chunk 规划
和流式上传过程中不会看起来像卡死。

构建与打包流程
--------------

``hubvault/server/static/webui/`` 下的静态文件来自 ``webui/`` 源码工作区：

.. code-block:: shell

    make webui_package

该命令会：

1. 在需要时安装前端依赖
2. 构建 ``webui/dist/``
3. 把产物同步到 ``hubvault/server/static/webui/``

面向发布的命令已经依赖这个同步步骤：

* ``make package`` 会把同步后的前端资源打进 sdist 和 wheel
* ``make build`` 会把同一套前端资源打进独立可执行文件

验证方法
--------

发布 UI 改动前，使用维护中的前端检查命令：

.. code-block:: shell

    make webui_test
    make webui_coverage
    make webui_e2e
    make webui_build

下一步
------

如果你需要部署细节，回到 :doc:`../service/index_zh`；如果你更需要的是 Python
remote client 而不是浏览器界面，继续看 :doc:`../remote/index_zh`。
