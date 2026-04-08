安装
====

这个教程说明安装后到底会得到什么、应该如何确认 Python API 和 CLI
都能正常使用，以及在进入正式工作流教程前最少应该做哪些检查。

.. contents:: 本页内容
    :local:

安装后会得到什么
----------------

``hubvault`` 对外提供两套公开入口：

* 以 :class:`hubvault.api.HubVaultApi` 为核心的 Python API
* 同时暴露为 ``hubvault`` 和 ``hv`` 的 CLI

项目当前要求 Python >= 3.7，并且在 CPython 3.7 到 3.14 上测试。仓库
格式本身也以跨平台为目标，要求在 Windows、主流 Linux 发行版和 macOS
之间都能正常使用。

从 PyPI 安装
------------

通常情况下，直接安装最新发布版本即可：

.. code-block:: shell

    pip install hubvault

如果你需要当前开发分支，也可以直接从 GitHub 安装：

.. code-block:: shell

    pip install -U git+https://github.com/hansbug/hubvault@main

大多数使用者都应该优先使用 PyPI 版本，只有在验证未发布修复或功能时才
需要跟 GitHub 主分支。

验证 Python API
---------------

第一步应该先确认包能正常导入，并且暴露了预期的公开表面：

.. code-block:: python

    from hubvault import HubVaultApi
    from hubvault.config.meta import __VERSION__

    print(HubVaultApi.__name__)
    # HubVaultApi

    print(__VERSION__)
    # 0.0.1  # 实际版本会随发布变化

如果这里失败，先修好 Python 环境，不要急着排查 CLI。

验证 CLI 名称
-------------

hubvault 安装后会提供两个等价命令名：

* ``hubvault``
* ``hv``

建议两个名字都检查一次：

.. code-block:: shell

    hubvault -v
    hv -v

期望输出形状大致如下：

.. code-block:: text

    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).
    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).

具体版本号会变化，但两个命令都应该成功退出，并显示相同版本。

然后再看一次顶层帮助：

.. code-block:: shell

    hubvault --help

当前帮助里至少应包含 ``init``、``commit``、``log``、``download``、
``snapshot``、``merge``、``verify`` 等公开子命令。

如果校验失败该看什么
--------------------

如果 Python 导入成功但 CLI 不工作：

* 确认 ``pip`` 对应的解释器和你当前 ``PATH`` 里的环境一致
* 优先尝试 ``python -m pip install hubvault``
* 检查该环境的脚本目录是否已经加入 ``PATH``

如果 CLI 正常但 Python 导入失败：

* 检查当前运行脚本使用的解释器是否就是安装所在环境
* 看一下 ``python -c "import sys; print(sys.executable)"``
* 必要时重新安装到正确环境

最小自动化检查
--------------

仓库里保留了可直接执行的 companion 检查文件，用来把文档和真实行为绑在
一起。

Python 导入检查：

.. literalinclude:: install_check.demo.py
    :language: python
    :linenos:

实际输出：

.. literalinclude:: install_check.demo.py.txt
    :language: text
    :linenos:

CLI 检查：

.. literalinclude:: cli_check.demo.sh
    :language: shell
    :linenos:

实际输出：

.. literalinclude:: cli_check.demo.sh.txt
    :language: text
    :linenos:

下一步
------

安装验证完成后，建议继续阅读 :doc:`../quick_start/index_zh`。那个教程会
真正创建一个仓库、写入 commit、读取文件，并展示 detached 下载/快照视图
的语义。

在线文档可通过
`https://hansbug.github.io/hubvault/main/index_zh.html <https://hansbug.github.io/hubvault/main/index_zh.html>`_
访问。
