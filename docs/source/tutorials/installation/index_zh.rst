安装
===================

hubvault 目前托管在 PyPI 上，需要 Python >= 3.7，并且已在 CPython 3.7 到 3.14 上完成测试。

你可以使用以下命令从 PyPI 简单安装 hubvault：

.. code:: shell

    pip install hubvault

你也可以通过 GitHub 安装最新版本：

.. code:: shell

    pip install -U git+https://github.com/hansbug/hubvault@main

你可以通过以下 Python 脚本检查你的安装：

.. literalinclude:: install_check.demo.py
    :language: python
    :linenos:

输出应该如下所示，这意味着你的安装成功了。

.. literalinclude:: install_check.demo.py.txt
    :language: text
    :linenos:

你也可以使用 CLI 命令进行检查

.. literalinclude:: cli_check.demo.sh
    :language: shell
    :linenos:

.. literalinclude:: cli_check.demo.sh.txt
    :language: txt
    :linenos:

hubvault 仍在开发中，你也可以通过 `https://hansbug.github.io/hubvault/main/index.html <https://hansbug.github.io/hubvault/main/index.html>`_ 查看稳定版本的文档。
