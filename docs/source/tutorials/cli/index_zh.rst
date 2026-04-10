CLI 工作流
==========

这个教程说明怎样把公开 CLI 当作日常操作界面来用。命令名字和手感尽量接近
Git，但它表达的仍然是 ``hubvault`` 自己的仓库模型，而不是 Git 的 mutable
workspace。

.. contents:: 本页内容
    :local:

CLI 最重要的一条规则
--------------------

``hubvault`` **没有 mutable workspace**。这意味着：

* 没有 staging area
* 没有“先暂存、以后再提交”的 ``git add`` 步骤
* ``commit`` 命令本身就直接描述要发生的仓库修改

只要先接受这一点，CLI 的行为就会很自然。

如何指定目标仓库
----------------

CLI 安装后会提供两个等价名字：

* ``hubvault``
* ``hv``

本教程统一用 ``hubvault``。建议使用 ``-C`` 显式指定目标仓库：

.. code-block:: shell

    hubvault -C demo-repo status

这对于脚本尤其有用，因为目标仓库在命令本身里就写得很清楚。

步骤 1：初始化仓库
------------------

创建仓库：

.. code-block:: shell

    hubvault init demo-repo
    # Initialized empty HubVault repository in demo-repo

``init`` 会创建仓库，并生成初始空历史根。如果需要，也可以通过 ``-b`` 修改
默认分支名，或通过 ``--large-file-threshold`` 调整大文件阈值。

步骤 2：创建第一条真实内容提交
------------------------------

先在本地创建文件，再显式提交：

.. code-block:: shell

    printf 'weights-v1' > model.bin
    hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
    # [main <commit>] add weights

``commit`` 命令接受显式操作：

* ``--add <repo_path>=<local_path>``
* ``--delete <repo_path>``
* ``--copy <src>=<dest>``

它不会去扫描隐藏工作区；你写什么操作，它就做什么操作。

步骤 3：查看状态、历史和目录树
------------------------------

使用只读命令查看当前状态：

.. code-block:: shell

    hubvault -C demo-repo status

    hubvault -C demo-repo log --oneline
    # <commit> add weights
    # <commit> Initial commit

    hubvault -C demo-repo ls-tree -r
    # 040000 tree <oid>  artifacts
    # 100644 blob <oid>  artifacts/model.bin

具体 ID 每次都可能不同，但输出结构是稳定的，并且刻意保持 Git 风格。

步骤 4：切分支并继续提交
------------------------

创建功能分支：

.. code-block:: shell

    hubvault -C demo-repo branch feature

列出分支：

.. code-block:: shell

    hubvault -C demo-repo branch

显示当前分支：

.. code-block:: shell

    hubvault -C demo-repo branch --show-current

然后直接往 ``feature`` 提交：

.. code-block:: shell

    printf '# CLI demo\n' > README.md
    hubvault -C demo-repo commit -r feature -m "add readme" --add README.md=./README.md
    # [feature <commit>] add readme

``-r`` 或 ``--revision`` 的语义，就是本次提交更新哪个分支。

步骤 5：创建和管理 tag
----------------------

给某个 revision 打 tag：

.. code-block:: shell

    hubvault -C demo-repo tag v0.1.0 feature -m "feature preview"

列出 tag：

.. code-block:: shell

    hubvault -C demo-repo tag -l

不再需要时删除 tag：

.. code-block:: shell

    hubvault -C demo-repo tag -d v0.1.0

tag 适合稳定的 release 标签、已验证 checkpoint，或重要审查节点。

步骤 6：合并回 main
-------------------

把功能分支合并回 ``main``：

.. code-block:: shell

    hubvault -C demo-repo merge feature --target main

根据历史形状不同，命令可能会：

* 直接 fast-forward ``main``
* 创建 merge commit
* 返回结构化冲突结果，并保持 ``main`` 不变

再检查合并后的历史：

.. code-block:: shell

    hubvault -C demo-repo log main --oneline -n 5

步骤 7：安全地拿到下载路径
--------------------------

当你需要磁盘上的真实路径时，使用这些只读命令：

.. code-block:: shell

    hubvault -C demo-repo download README.md
    # .../README.md

    hubvault -C demo-repo snapshot
    # .../snapshot/<id>/...

和 Python API 一样，这些返回的是 detached 用户视图。它们适合读取、导出、交给
别的工具，但不是仓库真值的可写别名。

步骤 8：校验仓库
----------------

每次完成重要写入后，建议跑一次校验：

.. code-block:: shell

    hubvault -C demo-repo verify
    # Quick verification OK

    hubvault -C demo-repo verify --full
    # Full verification OK

quick 模式适合普通写入后的日常检查；full 模式适合更深入的维护或归档前检查。

这个 CLI 刻意不做什么
---------------------

这个 CLI 虽然看起来像 Git，但不会为了“像”而硬模拟 Git 的一切：

* 没有 mutable checkout tree
* 没有 staging area
* 没有 remote / pull / push 工作流
* 没有通过 download 路径进行隐藏修改的能力

这样可以让 CLI 和它实际驱动的仓库模型保持一致。

完整 CLI 会话示例
-----------------

.. code-block:: shell

    hubvault init demo-repo
    # Initialized empty HubVault repository in demo-repo

    printf 'weights-v1' > model.bin
    hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
    # [main <commit>] add weights

    hubvault -C demo-repo branch feature

    printf '# CLI demo\n' > README.md
    hubvault -C demo-repo commit -r feature -m "add readme" --add README.md=./README.md
    # [feature <commit>] add readme

    hubvault -C demo-repo tag v0.1.0 feature -m "feature preview"

    hubvault -C demo-repo merge feature --target main
    # 可能是 fast-forward，也可能是 merge commit，取决于历史形状

    hubvault -C demo-repo log --oneline -n 5
    # <commit> ...

    hubvault -C demo-repo ls-tree -r
    # 100644 blob <oid>  README.md
    # 040000 tree <oid>  artifacts
    # 100644 blob <oid>  artifacts/model.bin

    hubvault -C demo-repo download README.md
    # .../README.md

    hubvault -C demo-repo snapshot
    # .../snapshot/<id>/...

    hubvault -C demo-repo verify
    # Quick verification OK

.. note::

   具体 commit ID 和 materialized cache 路径每次都会变化；稳定的是命令形状
   和仓库语义。
