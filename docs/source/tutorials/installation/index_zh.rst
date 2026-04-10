安装
====

这个教程带你从干净的 Python 环境走到一个已经验证可用的 ``hubvault`` 安装。
它会说明安装后会得到什么、不需要额外安装什么，以及怎样确认 Python API 和
CLI 都能正常使用。

.. contents:: 本页内容
    :local:

安装后会得到什么
----------------

安装 ``hubvault`` 后会得到两套公开入口：

* 以 :class:`hubvault.api.HubVaultApi` 为中心的 Python 包
* 同时暴露为 ``hubvault`` 和 ``hv`` 的命令行工具

本地仓库格式是自包含的。一个仓库就是磁盘上的一个目录；它不需要服务端、
守护进程、外部数据库服务或全局注册状态。

这也是它的核心价值之一：``hubvault`` 可以在不依赖 Docker、Kubernetes、
远端 Hub 服务或外部对象存储（例如 OSS / S3）的前提下维护大规模深度学习
artifacts。对于离线环境、运维预算敏感场景、或者已经遇到托管服务免费资源
额度限制的用户，这一点尤其重要。

运行时要求
----------

项目支持 Python ``>= 3.7``，目标兼容 CPython ``3.7`` 到 ``3.14``。仓库格式
面向 Windows、主流 Linux 发行版和 macOS。

内部实现会使用 Python 标准库 ``sqlite3`` 管理 repo-local metadata。你不需要
安装或运行单独的 SQLite 服务。payload bytes 仍然是仓库根目录下的普通文件。

从 PyPI 安装
------------

普通使用场景直接安装最新发布版本：

.. code-block:: shell

    pip install hubvault

如果你的机器上有多个 Python 环境，建议使用显式解释器形式：

.. code-block:: shell

    python -m pip install hubvault

从开发分支安装
--------------

只有当你明确需要未发布改动时，才建议安装开发分支：

.. code-block:: shell

    python -m pip install -U git+https://github.com/hansbug/hubvault@main

大多数用户应该优先使用 PyPI 版本。开发分支适合提前验证修复，但变化也会比
发布包更快。

验证 Python API
---------------

先确认 Python 可以导入包，并且能看到主公开类：

.. code-block:: python

    from hubvault import HubVaultApi
    from hubvault.config.meta import __VERSION__

    print(HubVaultApi.__name__)
    # HubVaultApi

    print(__VERSION__)
    # 0.0.1  # 实际版本会随发布变化

如果这一步失败，先修 Python 环境，不要急着排查 CLI。最常见的问题是安装到
一个解释器里，却用另一个解释器运行。

验证 CLI
--------

``hubvault`` 安装后会提供两个等价命令名：

* ``hubvault``
* ``hv``

两个名字都检查一次：

.. code-block:: shell

    hubvault -v
    hv -v

期望输出形状大致如下：

.. code-block:: text

    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).
    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).

具体版本号会随发布变化，但两个命令都应该成功退出，并显示相同版本。

再看一次顶层帮助：

.. code-block:: shell

    hubvault --help

命令列表里应该能看到 ``init``、``commit``、``branch``、``tag``、``merge``、
``log``、``ls-tree``、``download``、``snapshot``、``verify``、``reset``、
``status`` 等公开操作。

跑一个最小仓库检查
------------------

导入和 CLI 检查都通过后，可以创建一个临时仓库确认完整本地链路：

.. code-block:: shell

    hubvault init /tmp/hubvault-install-check
    printf 'hello' > /tmp/hubvault-install-check.txt
    hubvault -C /tmp/hubvault-install-check commit \
        -m "seed" \
        --add demo.txt=/tmp/hubvault-install-check.txt
    hubvault -C /tmp/hubvault-install-check verify

这会验证仓库创建、显式提交、metadata 存储和校验都能在当前环境里跑通。

排查建议
--------

如果 Python 导入成功但 CLI 不工作：

* 确认 ``pip`` 对应的环境和当前 ``PATH`` 一致
* 优先尝试 ``python -m pip install hubvault``
* 检查该环境的脚本目录是否加入 ``PATH``

如果 CLI 正常但 Python 导入失败：

* 检查 ``python -c "import sys; print(sys.executable)"``
* 用这个解释器重新安装
* 从 shell 路径里移除过期虚拟环境

如果仓库创建失败：

* 确认目标目录可写
* 避免平台保留文件名
* 在旧 Windows 系统上先用更短的本地路径测试

内联校验示例
------------

Python 侧校验：

.. code-block:: python

    from hubvault import HubVaultApi
    from hubvault.config.meta import __VERSION__

    print(HubVaultApi.__name__)   # HubVaultApi
    print(__VERSION__)            # 0.0.1  # 实际版本会随发布变化

CLI 侧校验：

.. code-block:: shell

    hubvault -v                   # Hubvault, version 0.0.1.
    hv -v                         # Hubvault, version 0.0.1.
    hubvault --help               # 会列出 init/commit/branch/tag/log/download/snapshot/verify/...
    hubvault init install-check   # Initialized empty HubVault repository in install-check
    hubvault -C install-check verify
    # Quick verification OK

下一步
------

继续阅读 :doc:`../quick_start/index_zh`，创建真实仓库、写入提交、读取文件，并
生成 detached 下载视图。

在线文档可通过
`https://hubvault.readthedocs.io/zh/latest/ <https://hubvault.readthedocs.io/zh/latest/>`_
访问。
