快速开始
========

这个教程串起最短但真正有用的一条 Python API 路径。你会创建仓库、提交文件、
查看历史、读取已提交内容，并为下游工具生成 detached 读取视图。

.. contents:: 本页内容
    :local:

一分钟心智模型
--------------

``hubvault`` 不是 mutable workspace。先记住三条规则：

* 写入是显式 commit
* 读取会解析某个 revision，通常是 ``main``
* 下载 API 返回 detached 用户视图，而不是仓库内部可写路径

这个模型让仓库可以作为一个目录安全移动、归档和重新打开。

步骤 1：创建仓库
----------------

从空目录开始：

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

``create_repo()`` 会创建仓库布局，并立刻生成一个空的 ``Initial commit``。
仓库从一开始就有合法历史根，因此普通历史 API 可以直接使用。

步骤 2：添加单个文件
--------------------

最常见的单文件写入路径是 :meth:`hubvault.api.HubVaultApi.upload_file`：

.. code-block:: python

    weights_commit = api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.safetensors",
        commit_message="add model weights",
    )

    print(weights_commit.commit_message)
    # add model weights

这个方法会直接写入一个真实 commit。它不是把文件放进 staging area 等待后续
操作。

步骤 3：创建显式多操作提交
--------------------------

当你希望自己组织 commit 操作列表时，使用
:meth:`hubvault.api.HubVaultApi.create_commit`：

.. code-block:: python

    from hubvault import CommitOperationAdd

    readme_commit = api.create_commit(
        operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
        commit_message="add readme",
    )

    print(len(readme_commit.oid))
    # 40

commit ID 是 Git 兼容的 40 位十六进制标识。返回值是公开的
:class:`hubvault.models.CommitInfo`，用于描述 commit 创建结果。

步骤 4：查看文件和历史
----------------------

现在通过读 API 检查仓库状态：

.. code-block:: python

    print(api.list_repo_files())
    # ['README.md', 'artifacts/model.safetensors']

    commits = api.list_repo_commits(formatted=True)
    print([item.title for item in commits])
    # ['add readme', 'add model weights', 'Initial commit']

    print(api.read_bytes("README.md").decode("utf-8").strip())
    # # Demo repo

这些 API 分别回答：

* ``list_repo_files()``：这个 revision 下有哪些文件？
* ``list_repo_commits()``：当前状态由哪些历史形成？
* ``read_bytes()``：某个文件的已提交字节内容是什么？

步骤 5：查看路径元数据
----------------------

当你需要公开元数据而不是文件内容时，使用 ``get_paths_info()``：

.. code-block:: python

    readme_info, model_info = api.get_paths_info(
        ["README.md", "artifacts/model.safetensors"]
    )

    print(readme_info.path)
    # README.md

    print(model_info.sha256 is not None)
    # True

公开文件模型会暴露面向用户的 ``oid`` / ``blob_id`` / ``sha256``，调用者不需要
理解内部存储布局。

步骤 6：生成 detached 视图
--------------------------

有些工具需要真实路径。单文件用 ``hf_hub_download()``：

.. code-block:: python

    download_path = api.hf_hub_download("artifacts/model.safetensors")

    print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))
    # True

整个树用 ``snapshot_download()``：

.. code-block:: python

    snapshot_dir = Path(api.snapshot_download())
    files = sorted(
        str(path.relative_to(snapshot_dir)).replace("\\\\", "/")
        for path in snapshot_dir.rglob("*")
        if path.is_file()
    )
    print(files)
    # ['README.md', 'artifacts/model.safetensors']

这些路径是 detached 视图。修改或删除它们不会破坏已提交仓库数据，需要时可以
重新生成。

步骤 7：校验仓库
----------------

完成有意义的写入后，跑一次低成本完整性检查：

.. code-block:: python

    report = api.quick_verify()
    print(report.ok)
    # True

普通操作后使用 ``quick_verify()``。维护窗口、归档交接或怀疑仓库状态异常时，
再使用 ``full_verify()``。

这个例子展示了什么
------------------

quick start 覆盖了最重要的公开保证：

* 仓库创建后立刻可用
* 修改只通过显式公开写 API 发生
* commit ID 是 Git 兼容标识
* 读 API 基于 revision
* 下载和快照路径保留 repo 相对后缀
* detached 视图不能修改已提交真相

常见误区
--------

不要做这些假设：

* 修改下载出来的文件会改变仓库
* 存在隐藏的 mutable workspace
* cache 路径是永久公开存储
* 需要手工编辑仓库内部文件

如果你希望仓库持久变化，就创建 commit。

完整示例
--------

.. code-block:: python

    from pathlib import Path

    from hubvault import CommitOperationAdd, HubVaultApi

    repo_dir = Path("demo-repo")
    api = HubVaultApi(repo_dir)

    info = api.create_repo()
    print(info.default_branch)          # main
    print(info.head is not None)        # True

    weights_commit = api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.safetensors",
        commit_message="add model weights",
    )
    print(weights_commit.commit_message)    # add model weights

    readme_commit = api.create_commit(
        operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
        commit_message="add readme",
    )
    print(len(readme_commit.oid))       # 40

    print(api.list_repo_files())
    # ['README.md', 'artifacts/model.safetensors']

    commits = api.list_repo_commits(formatted=True)
    print([item.title for item in commits])
    # ['add readme', 'add model weights', 'Initial commit']

    print(api.read_bytes("README.md").decode("utf-8").strip())
    # # Demo repo

    readme_info, model_info = api.get_paths_info(
        ["README.md", "artifacts/model.safetensors"]
    )
    print(readme_info.path)             # README.md
    print(model_info.sha256 is not None)    # True

    download_path = api.hf_hub_download("artifacts/model.safetensors")
    print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))
    # True

    snapshot_dir = Path(api.snapshot_download())
    files = sorted(
        str(path.relative_to(snapshot_dir)).replace("\\\\", "/")
        for path in snapshot_dir.rglob("*")
        if path.is_file()
    )
    print(files)
    # ['README.md', 'artifacts/model.safetensors']

    report = api.quick_verify()
    print(report.ok)                    # True

.. note::

   每次运行时 commit ID 和 cache 路径都会变化；稳定的是公开行为：显式提交、
   基于 revision 的读取，以及 detached 视图。
