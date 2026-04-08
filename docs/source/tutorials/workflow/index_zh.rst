分支、标签与合并工作流
======================

这个教程说明 quick start 之后最常见的“真实工作流”应该怎么走：

* 从已有历史切出分支
* 在 ``main`` 和功能分支上各自提交
* 给关键节点打 tag
* 把功能分支合并回主线
* 通过公开模型查看 refs、提交历史和 reflog

.. contents:: 本页内容
    :local:

工作流视角下的 hubvault
-------------------------

hubvault 借用了 Git 的历史模型，但仍保留自己的本地显式语义：

* ref 指向 commit
* commit 是不可变对象
* merge 和普通 commit 一样，最终都走事务化发布路径
* 冲突不会留下半成品仓库状态，而是以结构化公开结果返回

步骤 1：先建立主线历史
----------------------

先创建仓库，并在 ``main`` 上放一个基础提交：

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("workflow-repo")
    api.create_repo()
    api.upload_file(
        path_or_fileobj=b"base-model",
        path_in_repo="weights/model.bin",
        commit_message="seed main",
    )

这样仓库已经有了一条可继续演化的主线。

步骤 2：显式创建 branch 和 tag
------------------------------

从当前主线切一个功能分支：

.. code-block:: python

    api.create_branch(branch="feature")

然后在这个分支上继续推进，并给一个关键点打标签：

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"feature-notes",
        path_in_repo="notes/feature.txt",
        revision="feature",
        commit_message="add feature note",
    )
    api.create_tag(tag="v0.1.0", revision="feature", tag_message="feature preview")

tag 的意义在于：当某个功能分支节点值得被长期引用时，不需要只依赖分支名。

步骤 3：让主线也继续前进
------------------------

为了演示真正的 merge commit，而不是简单 fast-forward，需要让 ``main`` 也前进：

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"main-doc",
        path_in_repo="docs/main.txt",
        revision="main",
        commit_message="add main doc",
    )

此时两条线已经分叉：

* ``feature`` 有 ``notes/feature.txt``
* ``main`` 有 ``docs/main.txt``

步骤 4：执行 merge
------------------

发起合并：

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

返回值是公开的 :class:`hubvault.models.MergeResult`。根据历史形状不同，结果会是：

* ``fast-forward``：目标分支直接前移到来源分支
* ``merged``：创建一个新的 merge commit
* ``conflict``：检测到冲突，拒绝发布任何半成品结果

步骤 5：检查文件、refs 和历史
-----------------------------

合并成功后，不要靠猜，直接检查公开表面：

.. code-block:: python

    print(api.list_repo_files(revision="main"))
    # ['docs/main.txt', 'notes/feature.txt', 'weights/model.bin']

    refs = api.list_repo_refs()
    print(sorted(ref.name for ref in refs.branches))
    # ['feature', 'main']

    print([item.title for item in api.list_repo_commits(revision="main", formatted=True)[:4]])
    # ['merge feature branch', 'add main doc', 'add feature note', 'seed main']

    print([item.message for item in api.list_repo_reflog("main")[:3]])
    # ['merge feature branch', 'add main doc', 'seed main']

这几组 API 分别适合做：

* ``list_repo_refs()``：看当前有哪些 ref
* ``list_repo_commits()``：看用户视角下的提交历史
* ``list_repo_reflog()``：审计某个分支头是怎么一步步移动到现在的

应该如何理解冲突
----------------

如果 merge 无法干净应用，hubvault 不会留下“合到一半”的仓库状态。它会返回
一个 ``status == "conflict"`` 的 ``MergeResult``，并在 ``conflicts`` 字段里给出
结构化冲突信息，而目标分支 head 保持不变。

这正是原子性承诺的一部分：失败的 merge 在外部观察上等价于“从未发生过”。

配套可执行示例
--------------

完整脚本：

.. literalinclude:: workflow.demo.py
    :language: python
    :linenos:

实际输出：

.. literalinclude:: workflow.demo.py.txt
    :language: text
    :linenos:

.. note::

   每次运行时 commit ID 都会变化；真正稳定的是历史形状、merge 结果类型以及
   公开字段含义。
