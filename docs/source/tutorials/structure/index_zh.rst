仓库结构与工作原理
==================

这个教程解释 hubvault 仓库在磁盘上的组织方式，以及这些结构为什么和可搬迁
性、detached 读取视图、大文件存储和原子性设计直接相关。

.. contents:: 本页内容
    :local:

为什么磁盘布局本身值得讲清楚
----------------------------

hubvault 从一开始就不是“某个本地缓存目录”，而是一个完整的、自包含的本地
仓库格式。所以目录结构本身就是协议的一部分，而不是偶然的实现细节。

仓库必须能在这些场景下继续工作：

* 被移动到另一个绝对路径
* 被整体打包归档后再恢复
* 被其他进程在同机或另一台机器上重新打开

顶层目录结构
------------

一个典型的仓库根目录通常会包含这些区域：

.. code-block:: text

    cache/
    chunks/
    locks/
    logs/
    objects/
    quarantine/
    refs/
    txn/

每个区域职责不同：

* ``objects/``：提交、树、文件、blob 等不可变对象的持久化区域
* ``refs/``：branch 和 tag 等公开 ref 的当前头指针
* ``logs/refs/``：ref 更新的 reflog 审计轨迹
* ``chunks/``：大文件 chunk/pack/index 存储区域
* ``cache/``：detached 用户视图缓存
* ``locks/``：跨进程读写锁相关状态
* ``txn/``：事务临时 staging 区
* ``quarantine/``：必要时用于隔离恢复/维护对象的区域

正是这种职责拆分，让校验、恢复和垃圾回收都更容易做对。

公开文件元数据和内部存储寻址不是一回事
--------------------------------------

hubvault 会刻意区分“给用户看的文件元数据”和“引擎内部如何寻址对象”。

对于公开的 :class:`hubvault.models.RepoFile`，最重要的是：

* ``oid`` / ``blob_id``：对齐 Git/HF 习惯的公开文件标识
* ``sha256``：给用户看的裸 64 位十六进制内容摘要
* ``lfs``：大文件时额外附带的 LFS 风格元数据

它们并不等价于 ``objects/`` 下面每一种内部对象的地址。这样做的目的，就是让
公开 API 使用者可以理解文件，而不必依赖底层实现细节。

小文件和大文件分别怎么走
------------------------

hubvault 当前有两条存储路径：

* 小文件走普通 whole-file object 存储
* 大于等于 ``large_file_threshold`` 的文件走 chunked 存储

从公开 API 视角看，路径并不会变化：

.. code-block:: python

    small, large = api.get_paths_info(["artifacts/small.bin", "artifacts/large.bin"])

    print(small.lfs is None)
    # True

    print(large.lfs is not None)
    # True

    print(large.sha256)
    # 64 位十六进制摘要，具体值每次不同

即便内部已经 chunk 化，``hf_hub_download()`` 返回的路径仍会保留原始 repo
相对后缀，例如 ``artifacts/large.bin``。

detached 视图其实就是结构设计的一部分
----------------------------------------

``cache/`` 不是偶然出现的临时目录，而是 detached 用户视图语义的一部分。正是
因为有这层隔离，hubvault 才能：

* 给用户返回真实可读的文件路径
* 同时又不暴露仓库真值的可写别名

因此有一个非常关键的承诺：

* 改写或删除下载出来的文件，不会损坏已提交数据
* 之后再次读取时，可以从仓库真值重新构建用户视图

一次写操作在内部大致怎么完成
----------------------------

从高层看，一次公开写操作的过程是：

1. 获取跨进程 writer 锁
2. 把对象和元数据先放到事务临时区域
3. 发布不可变对象
4. 原子更新 refs 和 reflog
5. 清理临时状态并释放锁

如果进程在中途停止，恢复逻辑会把仓库退回到最近一次安全提交状态。外部应该
观察到的规则只有一条：

    如果这次写入没有成功完成，那么它就等价于从未发生过。

这也是为什么仓库结构里必须显式存在事务区和恢复相关区域，而不能直接就地改
写仓库真值。

配套可执行示例
--------------

完整脚本：

.. literalinclude:: structure.demo.py
    :language: python
    :linenos:

实际输出：

.. literalinclude:: structure.demo.py.txt
    :language: text
    :linenos:

.. note::

   具体对象 ID、文件 ID、pack/index 数量会随仓库状态变化；稳定的是各目录
   的职责、chunk 阈值行为，以及 detached 视图语义。
