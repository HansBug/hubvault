校验、GC 与历史压缩
===================

这个教程说明当仓库已经积累了真实历史和真实大文件之后，应该怎样通过公开维
护 API 保持仓库健康、分析空间占用并安全释放空间。

.. contents:: 本页内容
    :local:

什么时候应该看这个教程
----------------------

当出现以下场景时，就该进入维护阶段了：

* 已经写入了多代大文件
* detached 下载或快照缓存占了不少空间
* 准备把仓库归档、迁移或交给别人前，需要做健康检查
* 想释放空间，但又不想靠猜测去删目录

维护路径可以拆成四步：校验、分析、回收，以及在必要时重写历史。

步骤 1：先做校验
----------------

hubvault 对外暴露了两种校验强度：

.. code-block:: python

    quick = api.quick_verify()
    print(quick.ok)
    # True

    full = api.full_verify()
    print(full.ok)
    # True

它们适合不同场景：

* ``quick_verify()``：普通写入后的低成本完整性检查
* ``full_verify()``：维护窗口、可疑状态、归档前检查时使用的深入校验

步骤 2：先看空间到底花在哪里
----------------------------

在真正清理前，先让仓库自己给出空间画像：

.. code-block:: python

    overview = api.get_storage_overview()

    print(overview.total_size > 0)
    # True

    print(overview.historical_retained_size >= 0)
    # True

    print(overview.reclaimable_cache_size >= 0)
    # True

    print(overview.recommendations[:2])
    # ['...', '...']  # 实际文本会随仓库状态变化

这些字段回答的问题并不相同：

* ``total_size``：仓库总体占了多少空间？
* ``historical_retained_size``：有多少空间仍被旧历史保留？
* ``reclaimable_cache_size``：有多少 detached 视图缓存可安全回收？
* ``reclaimable_gc_size``：已经可以直接通过 GC 回收多少空间？
* ``recommendations``：仓库建议你下一步先做什么？

这一步的价值在于，能先判断问题到底是缓存、GC 还是历史保留。

步骤 3：先 dry-run 再 GC
--------------------------

不要靠猜，先跑预览版 GC：

.. code-block:: python

    dry_gc = api.gc(dry_run=True, prune_cache=True)

    print(dry_gc.dry_run)
    # True

    print(dry_gc.notes[:2])
    # ['dry-run: ...', '...']  # 实际提示会变化

这样可以先看到 hubvault 计划回收什么，而不会立即修改仓库状态。

步骤 4：回收已经可安全删除的数据
----------------------------------

确认 dry-run 结果合理后，再正式执行：

.. code-block:: python

    gc_report = api.gc(dry_run=False, prune_cache=True)

    print(gc_report.reclaimed_size >= 0)
    # True

    print(gc_report.removed_file_count >= 0)
    # True

单纯 GC 只能回收“已经不可达或已经明确可删”的部分。如果旧历史仍然可达，
那些字节会继续被保留，这是有意设计出来的安全行为。

步骤 5：当真正的阻塞项是历史保留时，显式 squash
--------------------------------------------------

很多大型仓库真正占空间的是历史，而不是缓存。这种情况下应该显式调用
``squash_history()``：

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

它的作用不是“神秘压缩”，而是把指定分支的旧历史重写掉，让此前仍被保留的
老对象真正变成不可达，之后才能被安全回收。

实际使用时如何判断该跑什么
--------------------------

一个比较稳妥的顺序是：

1. 普通写入后先跑 ``quick_verify()``
2. 进入正式维护或交付前跑 ``full_verify()``
3. 先看 ``get_storage_overview()`` 再决定动作
4. 正式清理前先 ``gc(dry_run=True)``
5. 只有当旧历史是主要占用时，才使用 ``squash_history()``

这样可以避免既清不干净、又误删风险高的两头不到岸状态。

配套可执行示例
--------------

完整脚本：

.. literalinclude:: maintenance.demo.py
    :language: python
    :linenos:

实际输出：

.. literalinclude:: maintenance.demo.py.txt
    :language: text
    :linenos:

.. note::

   具体字节数会受平台、Python 版本和文件系统行为影响。更重要的是理解每个
   字段的含义，以及这些维护动作之间的先后关系。
