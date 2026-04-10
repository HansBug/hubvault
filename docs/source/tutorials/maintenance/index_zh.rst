校验、GC 与历史压缩
===================

这个教程说明当仓库已经积累了真实历史、detached cache 和多代 artifacts
之后，应该怎样通过公开维护 API 保持仓库健康、分析空间占用并安全回收空间。
这些维护 API 是公开能力，本来就是日常运维的一部分，而不是隐藏实现细节。

.. contents:: 本页内容
    :local:

什么时候应该看这个教程
----------------------

当你遇到下面这些情况时，就该进入维护视角了：

* 已经写入了多代大文件
* detached 下载或快照缓存开始占明显空间
* 准备把仓库归档、迁移或交给别人前，需要做健康检查
* 想释放空间，但又不想靠猜测去删内部目录

维护路径其实可以拆成四个问题：

1. 仓库健康吗？
2. 空间花在哪里？
3. 哪些东西已经能安全回收？
4. 真正的阻塞项是不是旧历史仍然可达？

步骤 1：先做校验
----------------

``hubvault`` 对外暴露了两种校验强度：

.. code-block:: python

    quick = api.quick_verify()
    print(quick.ok)
    # True

    full = api.full_verify()
    print(full.ok)
    # True

它们的使用场景不同：

* ``quick_verify()``：普通写入后的低成本完整性检查
* ``full_verify()``：维护窗口、可疑状态、迁移检查、归档交接前使用的深入校验

一个很常见的顺序是：普通写入后 quick，正式维护和交接前 full。

步骤 2：删东西前先看空间画像
----------------------------

在手工删任何文件前，先让仓库自己给出结构化空间画像：

.. code-block:: python

    overview = api.get_storage_overview()

    print(overview.total_size > 0)
    # True

    print(overview.reachable_size >= 0)
    # True

    print(overview.historical_retained_size >= 0)
    # True

    print(overview.reclaimable_gc_size >= 0)
    # True

    print(overview.reclaimable_cache_size >= 0)
    # True

这些字段分别回答不同问题：

* ``total_size``：仓库总体占了多少空间？
* ``reachable_size``：为了保住当前 live refs，至少需要保留多少数据？
* ``historical_retained_size``：仍然被旧历史保留的空间有多少？
* ``reclaimable_gc_size``：现在立刻跑 GC 能回收多少？
* ``reclaimable_cache_size``：detached view cache 有多少可以安全丢弃？
* ``reclaimable_temporary_size``：temporary / quarantine residue 有多少可清理？

同时还会给你：

* ``sections``：按区域拆分的空间明细
* ``recommendations``：基于当前状态给出的维护建议顺序

只有先看到这些信息，你才能判断问题到底是 cache、GC，还是历史保留。

步骤 3：先 dry-run 再 GC
--------------------------

在真正修改仓库前，先跑 dry-run：

.. code-block:: python

    dry_gc = api.gc(dry_run=True, prune_cache=True)

    print(dry_gc.dry_run)
    # True

    print(dry_gc.reclaimed_size >= 0)
    # True

    print(dry_gc.notes[:2])
    # ['dry-run: ...', '...']  # 实际提示会随仓库状态变化

dry-run 会告诉你 ``hubvault`` 打算回收什么，但不会立即修改仓库状态。判断
cache 清理是否足够时，这一步尤其重要。

步骤 4：回收已经可安全删除的数据
----------------------------------

如果 dry-run 结果合理，再执行真实 GC：

.. code-block:: python

    gc_report = api.gc(dry_run=False, prune_cache=True)

    print(gc_report.reclaimed_size >= 0)
    # True

    print(gc_report.removed_file_count >= 0)
    # True

    print(gc_report.reclaimed_cache_size >= 0)
    # True

普通 GC 只会回收已经明确安全的东西：

* 不可达 object 数据
* 不可达 chunk / pack 数据
* 可重建的 detached cache
* 不再需要保留的 temporary / quarantine residue

如果旧历史仍然被某个分支引用，GC 会故意保留它。

步骤 5：当真正的问题是旧历史仍然可达时，使用 squash
------------------------------------------------------

很多大仓库最占空间的其实不是 cache，而是仍然可达的旧历史。遇到这种情况时，
显式调用 ``squash_history()``：

.. code-block:: python

    squash = api.squash_history(
        "main",
        commit_message="squash main history",
        run_gc=True,
        prune_cache=True,
    )

    print(squash.rewritten_commit_count >= 1)
    # True

    print(squash.dropped_ancestor_count >= 0)
    # True

    print(squash.blocking_refs)
    # []  # 或者仍然保留旧历史的其它 ref

``squash_history()`` 会保留 branch tip 的可见文件状态，但让这个分支更老的历史
从该分支上变得不可达。若 ``run_gc=True``，方法会立即跟进一次 GC，把刚刚变成
不可达的数据回收掉。

实际使用时怎么判断该跑什么
--------------------------

一个比较稳妥的顺序是：

1. 普通写入后先跑 ``quick_verify()``
2. 正式维护或归档交接前跑 ``full_verify()``
3. 先看 ``get_storage_overview()``
4. 预览 ``gc(dry_run=True)``
5. 再跑真实 ``gc()``
6. 只有当旧历史是主要空间占用时，才使用 ``squash_history()``

这样可以避免既清不干净，又误删风险高的两头不到岸。

不要做什么
----------

尽量避免这些习惯：

* 觉得某些目录“看起来像临时目录”就手工删除
* 没看 overview / GC 就直接删 cache、chunk 或 object 文件
* 误以为 GC 会重写仍然可达的历史
* 把 squash 当成“没后果的普通优化”

应该优先使用公开维护 API，它们已经知道怎样在不破坏仓库真相的前提下清理
安全可删内容。

完整维护示例
------------

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("maintenance-repo")
    api.create_repo(large_file_threshold=32)
    api.upload_file(
        path_or_fileobj=b"A" * 64,
        path_in_repo="model.bin",
        commit_message="seed v1",
    )
    api.upload_file(
        path_or_fileobj=b"B" * 64,
        path_in_repo="model.bin",
        commit_message="seed v2",
    )
    api.hf_hub_download("model.bin")    # 先生成一个 detached view

    quick = api.quick_verify()
    print(quick.ok)                     # True

    full = api.full_verify()
    print(full.ok)                      # True

    overview = api.get_storage_overview()
    print(overview.total_size > 0)      # True
    print(overview.reclaimable_cache_size >= 0)     # True
    print(overview.reclaimable_gc_size >= 0)        # True

    dry_gc = api.gc(dry_run=True, prune_cache=True)
    print(dry_gc.dry_run)               # True
    print(dry_gc.reclaimed_size >= 0)   # True

    gc_report = api.gc(dry_run=False, prune_cache=True)
    print(gc_report.reclaimed_size >= 0)        # True
    print(gc_report.removed_file_count >= 0)    # True

    squash = api.squash_history(
        "main",
        commit_message="squash main history",
        run_gc=True,
        prune_cache=True,
    )
    print(squash.rewritten_commit_count >= 1)   # True
    print(squash.dropped_ancestor_count >= 0)   # True

.. note::

   具体字节数会随平台、Python 版本和文件系统变化；稳定的是字段含义，以及
   这些维护动作之间的推荐顺序。
