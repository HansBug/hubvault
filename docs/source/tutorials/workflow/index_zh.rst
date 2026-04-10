分支、标签与合并工作流
======================

这个教程覆盖 quick start 之后最常见的历史工作流：从已有 tip 切分支、独立提
交、创建标签、合并回主线、检查 refs，以及理解冲突结果。

.. contents:: 本页内容
    :local:

工作流视角
----------

``hubvault`` 借用了 Git 的历史模型，但仍保留自己的本地仓库语义：

* ref 指向不可变 commit
* commit 通过公开 API 显式创建
* merge 本质上也是一次事务化仓库更新
* 冲突会返回结构化结果，而不是留下“合到一半”的仓库

步骤 1：建立主线
----------------

先创建仓库，并在 ``main`` 上放一个真实内容提交：

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("workflow-repo")
    api.create_repo()
    api.upload_file(
        path_or_fileobj=b"base-model",
        path_in_repo="weights/model.bin",
        commit_message="seed main",
    )

此时仓库已经有：

* 自动生成的 ``Initial commit``
* ``main`` 上的一条真实内容提交

步骤 2：创建功能分支
--------------------

从当前主线 tip 切一个分支：

.. code-block:: python

    feature_ref = api.create_branch(branch="feature")
    print(feature_ref.ref)
    # refs/heads/feature

如果你想从别的 revision 切分支，也可以显式传 ``revision=...``。这在切发布
分支或保留旧 checkpoint 时很有用。

步骤 3：推进功能分支
--------------------

现在在 ``feature`` 上独立提交：

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"feature-notes",
        path_in_repo="notes/feature.txt",
        revision="feature",
        commit_message="add feature note",
    )

此时：

* ``main`` 仍指向基础模型提交
* ``feature`` 已经前进到包含 ``notes/feature.txt`` 的新 tip

步骤 4：给关键节点打标签
------------------------

如果你希望给一个已验证的功能 tip 一个稳定的公开名字，就创建 tag：

.. code-block:: python

    tag_ref = api.create_tag(
        tag="v0.1.0",
        revision="feature",
        tag_message="feature preview",
    )
    print(tag_ref.ref)
    # refs/tags/v0.1.0

tag 适合标记 release candidate、验证通过的 checkpoint，或任何你想长期引用的
节点，而不必依赖分支名本身。

步骤 5：让 ``main`` 也继续前进
------------------------------

为了演示真正的 merge commit，而不是简单 fast-forward，让 ``main`` 也前进：

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"main-doc",
        path_in_repo="docs/main.txt",
        revision="main",
        commit_message="add main doc",
    )

现在两条线已经分叉：

* ``feature`` 有 ``notes/feature.txt``
* ``main`` 有 ``docs/main.txt``

步骤 6：合并功能分支
--------------------

把功能分支合并回 ``main``：

.. code-block:: python

    result = api.merge(
        "feature",
        target_revision="main",
        commit_message="merge feature branch",
    )

    print(result.status)
    # merged

    print(result.fast_forward)
    # False

    print(result.created_commit)
    # True

    print(result.conflicts)
    # []

返回值是 :class:`hubvault.models.MergeResult`。根据历史形状不同，结果可能是：

* ``fast-forward``：目标分支可以直接前移到来源 tip
* ``merged``：创建新的 merge commit
* ``already-up-to-date``：没有可做的事情
* ``conflict``：检测到不兼容修改，因此拒绝发布

步骤 7：检查 refs 和历史
------------------------

合并后，通过公开表面检查仓库状态：

.. code-block:: python

    print(api.list_repo_files(revision="main"))
    # ['docs/main.txt', 'notes/feature.txt', 'weights/model.bin']

    refs = api.list_repo_refs()
    print(sorted(ref.name for ref in refs.branches))
    # ['feature', 'main']

    print(sorted(ref.name for ref in refs.tags))
    # ['v0.1.0']

    print([item.title for item in api.list_repo_commits(revision="main", formatted=True)[:4]])
    # ['merge feature branch', 'add main doc', 'add feature note', 'seed main']

    print([item.message for item in api.list_repo_reflog("main")[:3]])
    # ['merge feature branch', 'add main doc', 'seed main']

这些 API 分别适合回答：

* ``list_repo_refs()``：当前有哪些 branch 和 tag？
* ``list_repo_commits()``：某个 revision 的用户视角历史是什么？
* ``list_repo_reflog()``：某个分支头是怎么一步步移动到现在的？

步骤 8：理解冲突处理
--------------------

如果 merge 不能干净应用，``hubvault`` **不会** 留下半成品仓库。相反：

* 目标分支 head 保持原样
* merge 返回 ``status == "conflict"``
* ``result.conflicts`` 里给出结构化冲突描述

这正是原子性承诺的一部分：失败的 merge 在外部观察上等价于从未发生过。

可选后续操作
------------

功能分支合并完以后，常见后续动作包括：

* 如果后续还要继续开发，就保留分支
* 如果 tag 和已合并历史已经足够，就删除分支
* 如果你需要显式移动分支头，就使用 ``reset_ref()``

示例：

.. code-block:: python

    earlier = api.list_repo_commits(revision="main")[1].commit_id
    api.reset_ref("main", to_revision=earlier)

这类操作会显式移动 ref，应像其它 ref 更新一样谨慎对待。

完整示例
--------

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("workflow-repo")
    api.create_repo()
    api.upload_file(
        path_or_fileobj=b"base-model",
        path_in_repo="weights/model.bin",
        commit_message="seed main",
    )

    feature_ref = api.create_branch(branch="feature")
    print(feature_ref.ref)              # refs/heads/feature

    api.upload_file(
        path_or_fileobj=b"feature-notes",
        path_in_repo="notes/feature.txt",
        revision="feature",
        commit_message="add feature note",
    )

    tag_ref = api.create_tag(
        tag="v0.1.0",
        revision="feature",
        tag_message="feature preview",
    )
    print(tag_ref.ref)                  # refs/tags/v0.1.0

    api.upload_file(
        path_or_fileobj=b"main-doc",
        path_in_repo="docs/main.txt",
        revision="main",
        commit_message="add main doc",
    )

    result = api.merge(
        "feature",
        target_revision="main",
        commit_message="merge feature branch",
    )
    print(result.status)                # merged
    print(result.fast_forward)          # False
    print(result.created_commit)        # True
    print(result.conflicts)             # []

    print(api.list_repo_files(revision="main"))
    # ['docs/main.txt', 'notes/feature.txt', 'weights/model.bin']

    refs = api.list_repo_refs()
    print(sorted(ref.name for ref in refs.branches))
    # ['feature', 'main']
    print(sorted(ref.name for ref in refs.tags))
    # ['v0.1.0']

    print([item.title for item in api.list_repo_commits(revision="main", formatted=True)[:4]])
    # ['merge feature branch', 'add main doc', 'add feature note', 'seed main']

    print([item.message for item in api.list_repo_reflog("main")[:3]])
    # ['merge feature branch', 'add main doc', 'seed main']

.. note::

   每次运行的 commit ID 都会变化；稳定的是历史形状、merge 结果类型，以及
   公开返回字段的含义。
