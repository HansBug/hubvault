欢迎来到 hubvault 文档
======================

概述
----

\ **hubvault**\ 是一个本地、嵌入式、API 优先的版本化仓库系统，用来保存模型权重、数据集、训练产物等大体积机器学习资产。它在公开 API 命名和返回模型上尽量靠近 ``huggingface_hub``，但仓库本体完全驻留在本地目录里，不依赖外部服务、数据库或守护进程。

如果要用一句最短的话概括，可以理解成：

* Git 风格历史与 refs
* Hugging Face 风格文件 API
* 整个仓库根目录本身就是可搬迁、可归档的完整产物
* 显式写入、detached 读取视图

hubvault 当前提供的能力
-----------------------

hubvault 当前已经包含可直接使用的本地仓库表面：

* Git 风格的 commit、tree、ref、tag、reflog 和 merge
* HF 风格的上传、下载、列表和元数据读取 API
* 只读 detached 下载视图与快照视图，避免误改仓库真值
* 大文件 chunked 存储，以及公开的 ``oid`` / ``sha256`` / LFS 风格元数据
* 校验、空间分析、垃圾回收和历史压缩能力
* 以 ``hubvault`` 和 ``hv`` 暴露的 git-like CLI

它最适合什么
------------

hubvault 面向的是“不想先运行一整套重型基础设施，但又需要长期维护深度学习
artifacts”的场景。模型权重、数据集、评测结果、实验产物都可以进入一个本地
持久化仓库；当远端 Hub、Docker / Kubernetes 栈、外部对象存储（例如 OSS /
S3）成本过高、离线不可用，或者受免费资源额度限制时，它提供的是一个
repo-local 的替代路径。

在这个定位下，hubvault 提供的是原子写入、稳定已提交数据、rollback-oriented
恢复、detached 读取视图、校验、GC、空间画像和历史压缩。它不是要替代所有
远端协作服务，而是让一个普通目录具备足够的仓库语义，从而可预测地维护本地
大规模 ML 数据。

这个项目最值得先记住的差异
--------------------------

hubvault 对几个点是明确坚持的：

* **仓库根目录就是完整真相。** 没有外部 sidecar 数据库，也没有隐藏服务端元数据。
* **读路径是 detached 视图。** ``hf_hub_download()`` 返回的文件可以读，但改它不会去修改已提交真值。
* **写入必须显式。** 不会伪装出一个可变工作区。
* **维护能力是公开 API。** 校验、空间分析、GC、历史压缩都应由用户显式调用。
* **基础设施要求很低。** 你不需要 Docker、Kubernetes、守护进程、外部对象存储或托管服务，也能维护一个持久 artifact 仓库。

设计约束
--------

hubvault 的核心约束包括：

* **仓库根目录可搬运**：移动目录、打包 zip、异地恢复后仍然有效
* **写入原子性**：中断写入后应等价于“本次操作从未发生过”
* **跨进程锁语义**：写入期间阻塞其他读写，避免看到中间态
* **公开 API 优先**：示例、教程和集成都走公开类、方法和命令
* **跨平台**：Linux、macOS、Windows 都是第一等支持目标

兼容性说明
----------

hubvault 在这些地方对齐 Git / Hugging Face：

* commit/tree/blob ID 使用 Git 风格 40 位十六进制 OID
* 文件级公开 ``sha256`` 使用裸 64 位十六进制摘要
* 下载出来的路径保留原始 repo 相对后缀

hubvault 也保留了自身的本地语义：

* 没有远端服务、PR 系统或后台守护进程
* CLI 命令形态接近 Git，但不引入 workspace 语义
* 下载和快照得到的是 detached 视图，而不是可写的仓库别名

建议阅读顺序
------------

如果你是第一次接触这个项目，建议按下面顺序阅读：

1. :doc:`tutorials/installation/index_zh`
2. :doc:`tutorials/quick_start/index_zh`
3. :doc:`tutorials/workflow/index_zh`
4. :doc:`tutorials/cli/index_zh`
5. :doc:`tutorials/maintenance/index_zh`
6. :doc:`tutorials/structure/index_zh`

文档导航
--------

.. toctree::
    :maxdepth: 2
    :caption: 教程
    :hidden:

    tutorials/installation/index_zh
    tutorials/quick_start/index_zh
    tutorials/workflow/index_zh
    tutorials/cli/index_zh
    tutorials/maintenance/index_zh
    tutorials/structure/index_zh

* :doc:`tutorials/installation/index_zh`
  先安装并确认 Python API、``hubvault``、``hv`` 三者都可用。
* :doc:`tutorials/quick_start/index_zh`
  通过一条最短真实路径创建仓库、写 commit、读取文件、理解 detached 下载视图。
* :doc:`tutorials/workflow/index_zh`
  理解 branch、tag、merge、提交历史以及 reflog 的公开用法。
* :doc:`tutorials/cli/index_zh`
  用 git-like CLI 工作，但不误以为它具备 Git 的 mutable workspace。
* :doc:`tutorials/maintenance/index_zh`
  学会在长期运行仓库上做校验、空间分析、GC 和历史压缩。
* :doc:`tutorials/structure/index_zh`
  理解磁盘布局、对象语义、大文件 chunk 规则和事务安全模型。

API 参考
--------

.. include:: api_doc_zh.rst

设计文档
--------

项目当前的实现路线主要记录在仓库的 ``plan/init/`` 目录中，里面定义了 repo 模型、事务写入路径、磁盘格式、兼容性决策、原子语义以及垃圾回收方案。

如果你想理解 hubvault 为什么有些地方对齐 HF/Git、有些地方又刻意保持差异，
这些设计文档会非常有帮助，尤其是 detached 视图、显式写 API、跨进程锁和
rollback-only 恢复相关部分。

社区和支持
----------

* **GitHub 仓库**：https://github.com/HansBug/hubvault
* **问题跟踪**：https://github.com/HansBug/hubvault/issues
* **PyPI 包**：https://pypi.org/project/hubvault/

许可证
-------

hubvault 在 GNU General Public License v3.0 下发布。详情请参阅 LICENSE 文件。
