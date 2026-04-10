仓库结构与工作原理
==================

这个教程解释当前仓库在磁盘上的布局，以及为什么这个布局会直接影响可搬迁性、
detached 视图、大文件存储、维护能力和崩溃安全。

.. contents:: 本页内容
    :local:

为什么布局本身值得讲清楚
------------------------

``hubvault`` 从一开始就不是“某个本地缓存目录”，而是一个自包含的本地仓库
格式。目录树不是偶然的实现细节，而是可搬迁和安全语义的一部分。

一个有效仓库在下面这些场景后仍应继续工作：

* 被移动到另一个绝对路径
* 被整体打包归档后再恢复
* 被其他进程在同机或另一台机器上重新打开

当前顶层布局
------------

一个典型的仓库根目录现在大致长这样：

.. code-block:: text

    FORMAT
    metadata.sqlite3
    cache/
    chunks/
    locks/
    objects/
    quarantine/
    txn/

这些区域的关键职责如下：

* ``FORMAT``：仓库格式标记
* ``metadata.sqlite3``：steady-state metadata 和 object truth-store
* ``locks/``：仓库级 shared / exclusive 锁文件
* ``objects/blobs/*.data``：已发布的 blob payload bytes
* ``chunks/packs/*.pack``：已发布的 pack chunk payload bytes
* ``cache/``：detached 单文件和快照视图
* ``txn/``：进行中的 staging 和 residue cleanup 区
* ``quarantine/``：必要时用于恢复或维护隔离的残留区域

哪些东西在 SQLite，哪些东西还在文件系统
----------------------------------------

当前仓库模型会刻意把 metadata 真相层和 payload bytes 分开。

SQLite 里保存的是 steady-state metadata 和 object 记录，包括：

* 仓库元数据
* refs
* reflog
* 事务日志状态
* chunk 可见性元数据
* commit / tree / file / blob metadata

文件系统里仍然保存 payload bytes：

* ``objects/blobs/`` 下的 blob 数据文件
* ``chunks/packs/`` 下的 pack chunk payload
* ``cache/`` 下的 detached 用户视图

这种设计让仓库拥有一个 repo-local metadata truth store，同时又保持 payload
存储足够简单、可移动、可随仓库整体打包。

哪些东西该当成真相层，哪些不该
------------------------------

最关键的操作规则是：

* ``metadata.sqlite3`` 是 steady-state metadata 真相源
* detached cache 是可重建视图，不是真相
* ``txn/`` 和 ``quarantine/`` 是维护 / 恢复区域，不是用户数据区

某些旧布局目录在仓库树里仍可能出现，用于迁移或兼容场景，但不应被当成当前
仓库的主要真相层理解。

公开文件元数据和私有存储寻址不是一回事
----------------------------------------

``hubvault`` 会刻意区分“给用户看的文件标识”和“引擎内部如何存储”。

对公开的 :class:`hubvault.models.RepoFile` 来说，最重要的用户字段是：

* ``path``：repo 相对路径
* ``oid`` / ``blob_id``：Git/HF 风格文件标识
* ``sha256``：裸 64 位十六进制内容摘要
* ``lfs``：大文件时额外附带的元数据

这些字段不是内部存储记录的机械暴露。这样做是为了让调用者理解文件，而不必
依赖私有实现细节。

小文件和大文件分别怎么走
------------------------

``hubvault`` 当前有两条存储路径：

* 小文件走普通 object 存储
* 大于等于 ``large_file_threshold`` 的文件走 chunked 存储

从公开调用者视角看，repo 路径并不会变化：

.. code-block:: python

    small, large = api.get_paths_info(["artifacts/small.bin", "artifacts/large.bin"])

    print(small.lfs is None)
    # True

    print(large.lfs is not None)
    # True

    print(large.sha256)
    # 64 位十六进制摘要，具体值每次不同

即便文件内部已经 chunk 化，``hf_hub_download()`` 返回的路径仍然保留原始
repo 相对后缀，比如 ``artifacts/large.bin``。

detached 视图本来就是结构设计的一部分
--------------------------------------

``cache/`` 不是偶然产生的杂项目录，而是用户视图层。正是因为有它，
``hubvault`` 才能在返回真实磁盘路径的同时，不暴露仓库真相的可写别名。

这背后有一个重要承诺：

* 删除或修改下载出的文件，不会破坏已提交数据
* 下一次读取时，可以从仓库真相重新构建 detached 视图

这也是为什么 download 和 snapshot 可以安全地交给其他本地工具使用。

一次写操作从高层看怎么完成
--------------------------

一次公开写操作，大致遵循下面这个顺序：

1. 获取仓库 writer 锁
2. 在事务局部区域中 staging payload 和 metadata 变化
3. 发布不可变 payload bytes
4. 原子提交 metadata 真相层
5. 清理 residue，并释放锁

外部应该观察到的规则很简单：

    如果一次写入没有成功完成，那么仓库应该看起来像这次写入从未发生。

这种 rollback-oriented 行为，也是为什么 ``hubvault`` 必须保留显式事务区和
恢复相关区域，而不能直接就地改写仓库真相。

为什么这个结构天然支持可搬迁
----------------------------

因为仓库把持久状态都保留在一个根目录里：

* 不存在 repo 外 sidecar 数据库需要一起带走
* 仓库真相不依赖绝对路径
* 归档 / 恢复之后，不需要额外 rebuild 才能重新打开

这就是为什么 ``hubvault`` 可以像一个 portable local artifact repository，
而不是依赖宿主机状态的缓存目录。

完整结构示例
------------

.. code-block:: python

    from pathlib import Path

    from hubvault import HubVaultApi

    repo_dir = Path("structure-repo")
    api = HubVaultApi(repo_dir)
    api.create_repo(large_file_threshold=32)

    api.upload_file(
        path_or_fileobj=b"small-file",
        path_in_repo="artifacts/small.bin",
        commit_message="add small file",
    )
    api.upload_file(
        path_or_fileobj=b"A" * 64,
        path_in_repo="artifacts/large.bin",
        commit_message="add large file",
    )

    print((repo_dir / "FORMAT").exists())               # True
    print((repo_dir / "metadata.sqlite3").exists())     # True
    print((repo_dir / "locks" / "repo.lock").exists())  # True

    small, large = api.get_paths_info(
        ["artifacts/small.bin", "artifacts/large.bin"]
    )
    print(small.lfs is None)            # True
    print(large.lfs is not None)        # True

    download_path = api.hf_hub_download("artifacts/large.bin")
    print(Path(download_path).as_posix().endswith("artifacts/large.bin"))
    # True

    overview = api.get_storage_overview()
    print(overview.total_size > 0)      # True

.. note::

   具体 ID、文件数和 pack 数量会随仓库状态变化；稳定的是各区域职责、
   metadata 真相层与 payload bytes 的分工，以及 detached 视图语义。
