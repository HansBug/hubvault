# 01. 总体架构

## 1. 总体思路

系统整体采用如下组合：

- Git 风格的不可变元数据 DAG
- 面向大文件的内容寻址 chunk 存储
- append-only pack 文件
- 基于文件的 LSM 风格索引
- 基于事务暂存目录的原子提交协议

这意味着系统本质上是一个嵌入式事务化对象仓库，而不是 git 工作区包装器。

## 2. 分层结构

建议将实现拆分为五层：

### 2.1 API 层

提供给用户的 Python API，整体风格尽量接近 `huggingface_hub.HfApi`。

职责：

- 参数校验
- 路径规范化
- 事务入口封装
- 错误类型定义
- 向后兼容包装

### 2.2 仓库服务层

负责协调写事务、读取对象、解析 refs、执行 merge、rollback、gc。

职责：

- 仓库打开与初始化
- 读写锁管理
- branch/tag/commit 逻辑
- 冲突检测
- 历史查询

### 2.3 元数据层

负责管理 commit/tree/file/ref 等不可变对象。

职责：

- 对象序列化与反序列化
- 对象哈希计算
- 对象落盘与查找
- ref log 管理

### 2.4 数据存储层

负责大文件切块、pack 写入、pack 查找、内容缓存。

职责：

- whole-file 与 chunked 两种存储模式
- chunk dedupe 查找
- pack 追加写
- 文件重组与 range read

### 2.5 维护层

负责验证、回收与仓库体检。

职责：

- quick verify
- full verify
- mark-sweep GC
- pack compaction
- 索引段合并

## 3. 对象关系

对象关系固定如下：

- `Ref -> Commit`
- `Commit -> Tree`
- `Tree -> Tree | File`
- `File -> Chunk[]`

所有对象都不可变，因此：

- branch 创建和切换只改 ref
- rollback 只改 ref 或增加 revert commit
- merge 的核心工作是构造新的 tree 和 commit

## 4. 写路径与读路径分离

### 4.1 写路径

写路径必须严格走事务协议：

- 获取写锁
- 校验 head
- 写入事务目录
- 刷盘
- 发布对象
- 原子更新 ref

### 4.2 读路径

读路径永远只读取“已发布对象”：

- 按 ref 找到 commit
- 递归解析 tree
- 定位 file 对象
- 读取 chunk 或缓存文件

这可以保证读者不会看到半写状态。

## 5. 关键设计决策

### 5.1 无 workspace

仓库主路径不是工作区，而是引擎私有存储区。用户不能直接修改仓库内部文件结构，所有操作必须经过 API。

### 5.2 单写者、多读者

首版推荐单 repo 同时只允许一个写事务。读操作不需要全局互斥。

### 5.3 历史回滚与历史回收分离

- rollback 负责切换逻辑版本
- GC 负责释放物理空间

这两步绝不能混在同一个动作里。

### 5.4 原生扩展可选

纯 Python 实现必须保证协议正确性；原生扩展只负责性能加速，例如：

- BLAKE3
- Zstd
- FastCDC
- 大索引扫描优化
