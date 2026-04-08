CLI 工作流
==========

这个教程说明公开 CLI 在日常使用中应该怎样理解和使用。命令名字和输出手感
会尽量靠近 Git，但它表达的仍然是 hubvault 自己的仓库模型，而不是 Git 的
workspace 模型。

.. contents:: 本页内容
    :local:

CLI 最重要的一条规则
--------------------

hubvault **没有** mutable workspace，因此：

* 没有 staging area
* 没有只做“暂存”而不真正提交的 ``git add`` 式步骤
* ``commit`` 命令本身就直接描述你要施加到仓库上的修改

只要先接受这个差异，CLI 的其他行为会非常自然。

命令名与目标仓库
----------------

CLI 安装后会提供两个等价名字：

* ``hubvault``
* ``hv``

本教程统一使用 ``hubvault`` 叙述。建议在脚本里总是用 ``-C`` 显式指定目标
仓库：

.. code-block:: shell

    hubvault -C demo-repo status

这和 Git 的手感接近，但目标更明确，也更适合自动化。

步骤 1：初始化并创建第一条真实提交
----------------------------------

先初始化仓库：

.. code-block:: shell

    hubvault init demo-repo
    # Initialized empty HubVault repository in demo-repo

初始化完成后仓库里已经有 ``Initial commit``。然后创建真正包含内容的提交：

.. code-block:: shell

    printf 'weights-v1' > model.bin
    hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
    # [main <commit>] add weights

``commit`` 命令接收显式操作，而不是去扫描本地工作区：

* ``--add <repo_path>=<local_path>``
* ``--delete <repo_path>``
* ``--copy <src>=<dest>``

步骤 2：在其他分支上继续提交
----------------------------

创建功能分支，并明确往该分支提交：

.. code-block:: shell

    hubvault -C demo-repo branch feature
    printf '# CLI demo\n' > README.md
    hubvault -C demo-repo commit -r feature -m "add readme" --add README.md=./README.md
    # [feature <commit>] add readme

其中 ``-r`` 或 ``--revision`` 的语义，就是指定本次提交更新哪个分支。

步骤 3：合并、看日志、列树
--------------------------

把功能分支合并回主线：

.. code-block:: shell

    hubvault -C demo-repo merge feature --target main
    # Updating <old>..<new>
    # Fast-forward

然后检查结果：

.. code-block:: shell

    hubvault -C demo-repo log --oneline
    # <commit> add readme
    # <commit> add weights
    # <commit> Initial commit

    hubvault -C demo-repo ls-tree -r
    # 100644 blob <oid>  README.md
    # 040000 tree <oid>  artifacts
    # 100644 blob <oid>  artifacts/model.bin

具体 ID 每次运行都会不同，但输出结构和含义是稳定的，而且故意做成接近
Git 的样子。

步骤 4：安全地拿到读取路径
--------------------------

当你需要真实文件路径或真实目录时，使用 ``download`` 和 ``snapshot``：

.. code-block:: shell

    hubvault -C demo-repo download README.md
    # .../README.md

    hubvault -C demo-repo snapshot
    # .../snapshot/<id>/...

和 Python API 一样，它们返回的是 detached 用户视图。它们适合读取、导出、
传给其他工具，但不应被当作仓库真值的可写别名。

步骤 5：校验仓库
----------------

写操作后建议立刻校验：

.. code-block:: shell

    hubvault -C demo-repo verify
    # Quick verification OK

    hubvault -C demo-repo verify --full
    # Full verification OK

通常情况下，quick 模式适合作为普通写入后的低成本检查；full 模式适合更重
的维护或归档前检查。

这个 CLI 刻意不去做什么
-----------------------

虽然这个 CLI 看起来像 Git，但它不会为了“像”而硬模拟 Git 的一切：

* 没有未暂存工作区编辑的状态展示
* 没有把某个 revision checkout 成可变树的语义
* 没有 remote / push / pull 相关命令
* 没有通过下载路径进行隐藏修改的能力

这样反而更能保持 CLI 和底层存储模型的一致性。

配套可执行示例
--------------

完整 shell 脚本：

.. literalinclude:: cli_workflow.demo.sh
    :language: shell
    :linenos:

实际输出：

.. literalinclude:: cli_workflow.demo.sh.txt
    :language: text
    :linenos:

.. note::

   配套脚本展示的是 fast-forward merge 路径。历史真正分叉后，也可能得到
   merge commit 或结构化冲突结果；对应情形见 Python 工作流教程。
