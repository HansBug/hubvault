欢迎来到 hubvault 文档
======================

概述
--------

\ **hubvault**\ 是一个仍在早期阶段的 Python 项目，目标是提供一个本地、嵌入式、API 优先的版本化仓库系统，用来保存模型权重、数据集、训练产物等大体积机器学习资产。它期望在使用体验上接近 ``huggingface_hub.HfApi``，但不依赖外部服务、数据库或守护进程。

当前状态
--------

.. note::

   hubvault 目前还处在项目引导和基础搭建阶段。这个仓库当前主要提供打包、CI、文档脚手架和一个很小的 CLI 外壳；设计文档里描述的存储引擎与公开仓库 API 仍在实现中。

设计目标
--------

hubvault 的核心设计约束包括：

* **本地优先**：单机本地即可运行，不要求额外服务
* **版本化资产**：围绕 commit、tree、ref 和大文件内容存储组织仓库
* **一致性优先**：优先保证事务正确性、崩溃恢复和数据校验
* **Python API 优先**：核心使用方式是 Python 接口，而不是庞杂的 CLI
* **跨平台**：默认面向 Linux、macOS 和 Windows

当前仓库里已有的内容
--------------------

当前仓库已经包含：

* ``hubvault.config``：项目元信息
* ``hubvault.entry``：基于 Click 的 CLI 引导层和命令装配
* ``plan/init/``：初始范围、总体架构、存储格式、一致性和 GC 设计文档
* ``docs/``：安装说明和当前代码的 API 参考页

现阶段 CLI 只承担很轻量的引导和校验职责，未来真正稳定的产品表面仍然会是 Python API。

文档导航
--------

.. toctree::
    :maxdepth: 2
    :caption: 教程
    :hidden:

    tutorials/installation/index_zh

* :doc:`tutorials/installation/index_zh`

API 参考
--------

.. include:: api_doc_zh.rst

设计文档
--------

项目当前的实现路线主要记录在仓库的 ``plan/init/`` 目录中，里面定义了 repo 模型、事务写入路径、磁盘格式、校验策略以及垃圾回收方案。

社区和支持
----------

* **GitHub 仓库**：https://github.com/HansBug/hubvault
* **问题跟踪**：https://github.com/HansBug/hubvault/issues
* **PyPI 包**：https://pypi.org/project/hubvault/

许可证
-------

hubvault 在 GNU General Public License v3.0 下发布。详情请参阅 LICENSE 文件。
