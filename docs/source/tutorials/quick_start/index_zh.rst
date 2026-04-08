快速开始
========

这个教程串起最短但真正有用的一条 Python API 路径：

* 创建本地仓库
* 通过公开 API 写入几次 commit
* 查看文件清单与提交历史
* 生成 detached 单文件下载视图和快照视图
* 执行一次校验

这里不再只给一个脚本就结束，而是按步骤解释每一步为什么这么做、结果代表
什么含义。完整可执行示例放在文末作为 companion。

.. contents:: 本页内容
    :local:

先建立正确的心智模型
--------------------

使用 hubvault 前，最重要的一点是先接受它不是一个 mutable workspace：

* 写入必须经过显式的公开 commit API
* 读取基于某个 revision，默认通常是 ``main``
* 当你需要真实文件路径时，下载 API 返回的是 detached 用户视图

只要先把这三点记住，后面的 API 会非常顺手。

步骤 1：创建仓库
----------------

从空目录开始初始化：

.. code-block:: python

    from pathlib import Path
    from hubvault import HubVaultApi

    repo_dir = Path("demo-repo")
    api = HubVaultApi(repo_dir)
    info = api.create_repo()

    print(info.default_branch)
    # main

    print(info.head is not None)
    # True

第二行很关键。``create_repo()`` 并不是只创建目录结构，它会立刻生成一个空的
``Initial commit``，因此仓库从一开始就有合法历史根，不存在“尚未初始化历史”
这种额外状态。

步骤 2：通过公开提交 API 写入内容
----------------------------------

常见的公开写入路径有两种：

* 用 :meth:`hubvault.api.HubVaultApi.upload_file` 做单文件便捷提交
* 用 :meth:`hubvault.api.HubVaultApi.create_commit` 搭配操作列表构造显式 commit

先用 ``upload_file()`` 写入模型文件：

.. code-block:: python

    weights_commit = api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.safetensors",
        commit_message="add model weights",
    )

    print(weights_commit.commit_message)
    # add model weights

再用 ``create_commit()`` 显式增加 README：

.. code-block:: python

    from hubvault import CommitOperationAdd

    readme_commit = api.create_commit(
        operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
        commit_message="add readme",
    )

    print(len(readme_commit.oid))
    # 40

此时历史里已经有三次提交：

* 自动生成的 ``Initial commit``
* ``add model weights``
* ``add readme``

步骤 3：检查仓库当前状态
------------------------

提交完成后，马上用公开读 API 看结果：

.. code-block:: python

    print(api.list_repo_files())
    # ['README.md', 'artifacts/model.safetensors']

    print([item.title for item in api.list_repo_commits(formatted=True)])
    # ['add readme', 'add model weights', 'Initial commit']

    print(api.read_bytes("README.md").decode("utf-8").strip())
    # # Demo repo

这三类查询分别回答三个不同问题：

* ``list_repo_files()``：当前 revision 下到底有哪些文件？
* ``list_repo_commits()``：当前状态是由哪些提交形成的？
* ``read_bytes()``：某个已提交文件的精确内容是什么？

步骤 4：生成 detached 读取视图
------------------------------

有些场景需要真实文件路径或真实目录树，这时使用下载 API：

单文件下载：

.. code-block:: python

    download_path = api.hf_hub_download("artifacts/model.safetensors")

    print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))
    # True

快照下载：

.. code-block:: python

    snapshot_dir = Path(api.snapshot_download())
    files = sorted(
        str(path.relative_to(snapshot_dir)).replace("\\\\", "/")
        for path in snapshot_dir.rglob("*")
        if path.is_file()
    )
    print(files)
    # ['README.md', 'artifacts/model.safetensors']

这里最重要的语义不是“能下载”，而是“下载结果是 detached 的”。也就是说：

* 这些路径可以像普通文件那样读取
* 但它们不是仓库真值的可写别名
* 即便用户改写或删除这些文件，也不会破坏已提交数据
* 需要时可以再次从仓库真值重建

步骤 5：执行一次校验
--------------------

普通写入完成后，最低成本的完整性检查是 ``quick_verify()``：

.. code-block:: python

    report = api.quick_verify()
    print(report.ok)
    # True

这适合作为日常的“刚刚做完写操作，现在确认仓库状态仍然健康”的检查。
更深入的维护路径会在后面的维护教程里展开。

这个例子真正展示了什么
----------------------

虽然这个 quick start 很短，但它已经覆盖了几个关键公开承诺：

* 仓库在 ``create_repo()`` 后立刻可用
* commit 通过公开 API 显式创建，并返回公开模型
* commit ID 是真实的 40 位十六进制标识
* 下载路径保留 repo 相对后缀
* 下载和快照都是与仓库真值隔离的 detached 视图

容易犯的错
----------

不要把 hubvault 当成普通工作区：

* 不要修改下载出来的文件并期望仓库自动被修改
* 不要期待存在未提交 workspace
* 不要把缓存里的临时路径当成永久稳定的内部结构

如果你希望仓库真正发生变化，就必须显式调用公开写 API。

配套可执行示例
--------------

完整脚本：

.. literalinclude:: quick_start.demo.py
    :language: python
    :linenos:

实际输出：

.. literalinclude:: quick_start.demo.py.txt
    :language: text
    :linenos:

.. note::

   每次运行时，commit ID 和临时缓存路径都会变化；稳定的是输出结构和这些
   API 的公开语义。
