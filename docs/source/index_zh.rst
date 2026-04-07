欢迎来到 hubvault（Python Finite Control State Machine Framework）的文档
==========================================================================

概述
-------------

\ **hubvault**\ （Python Finite Control State Machine Framework）是一个强大的 Python 框架，用于解析
\ **FCSTM（Finite Control State Machine）**\ 领域特定语言（DSL）并生成多种目标语言的可执行代码。它专注于使用
灵活的 Jinja2 模板系统建模\ **层次状态机（Harel 状态图）**\ 。

核心特性
~~~~~~~~~~~~~

* **表达性 DSL 语法**：直观的领域特定语言，用于定义状态、转换、事件和生命周期动作
* **层次状态机**：完全支持嵌套状态的父子关系和面向切面编程
* **多语言代码生成**：基于模板的渲染系统，支持 C、C++、Python 和自定义目标语言
* **PlantUML 可视化**：自动生成状态机图表用于文档
* **基于 ANTLR4 的解析器**：强大的语法解析，提供详细的错误报告
* **灵活的事件系统**：本地、链式和全局事件作用域，用于复杂的状态机协调
* **生命周期动作**：进入、期间和退出动作，支持前后切面
* **抽象和引用动作**：声明抽象函数并在状态间重用动作

应用场景
~~~~~~~~~~~~~

hubvault 适用于：

* **嵌入式系统**：为微控制器和物联网设备生成高效的状态机代码
* **协议实现**：使用复杂状态转换建模通信协议
* **游戏 AI**：使用层次状态机设计角色行为和游戏逻辑
* **工作流引擎**：使用清晰的状态定义实现业务流程工作流
* **控制系统**：构建具有安全关键状态管理的工业控制逻辑

快速开始
-------------

安装
~~~~~~~~~~~~~

.. code-block:: bash

   pip install hubvault

基本用法
~~~~~~~~~~~~~

**1. 使用 DSL 定义状态机**

创建文件 ``traffic_light.fcstm``：

.. code-block:: fcstm

   def int timer = 0;

   state TrafficLight {
       [*] -> Red;

       state Red {
           enter { timer = 0; }
           during { timer = timer + 1; }
       }

       state Yellow {
           enter { timer = 0; }
           during { timer = timer + 1; }
       }

       state Green {
           enter { timer = 0; }
           during { timer = timer + 1; }
       }

       Red -> Green : if [timer >= 30];
       Green -> Yellow : if [timer >= 25];
       Yellow -> Red : if [timer >= 5];
   }

**2. 生成代码**

.. code-block:: bash

   hubvault generate -i traffic_light.fcstm -t templates/c/ -o output/

**3. 使用 PlantUML 可视化**

.. code-block:: bash

   hubvault plantuml -i traffic_light.fcstm -o traffic_light.puml

架构
-------------

hubvault 遵循三阶段流水线：

1. **DSL 解析**：基于 ANTLR4 的解析器将 DSL 文本转换为抽象语法树（AST）
2. **模型构建**：AST 节点转换为可查询的状态机模型
3. **代码生成**：Jinja2 模板将模型渲染为目标语言代码

框架提供：

* **DSL 层** (``hubvault.dsl``)：语法定义、解析器和 AST 节点
* **模型层** (``hubvault.model``)：带验证的状态机模型类
* **渲染引擎** (``hubvault.render``)：基于模板的代码生成，支持表达式样式
* **CLI 工具** (``hubvault.entry``)：常用操作的命令行界面

教程
-------------------------

.. toctree::
    :maxdepth: 2
    :caption: 教程
    :hidden:

    tutorials/installation/index_zh
    tutorials/structure/index_zh
    tutorials/dsl/index_zh
    tutorials/render/index_zh
    tutorials/simulation/index_zh
    tutorials/visualization/index_zh
    tutorials/cli/index_zh
    tutorials/grammar/index_zh

* :doc:`tutorials/installation/index_zh`
* :doc:`tutorials/structure/index_zh`
* :doc:`tutorials/dsl/index_zh`
* :doc:`tutorials/render/index_zh`
* :doc:`tutorials/simulation/index_zh`
* :doc:`tutorials/visualization/index_zh`
* :doc:`tutorials/cli/index_zh`
* :doc:`tutorials/grammar/index_zh`

最佳实践
-------------------------

.. toctree::
    :maxdepth: 2
    :caption: 最佳实践

.. include:: api_doc_zh.rst

社区和支持
-----------------------

* **GitHub 仓库**：https://github.com/HansBug/hubvault
* **问题跟踪**：https://github.com/HansBug/hubvault/issues
* **PyPI 包**：https://pypi.org/project/hubvault/

许可证
---------

hubvault 在 Apache License 2.0 下发布。详情请参阅 LICENSE 文件。
