Remote Client 使用说明
======================

这个教程展示如何在另一个 Python 进程里，通过
:class:`hubvault.remote.HubVaultRemoteApi` 访问正在运行的 ``hubvault``
服务端。

.. contents:: 本页内容
    :local:

安装 remote extra
-----------------

Remote client 是可选能力：

.. code-block:: shell

    pip install 'hubvault[remote]'

这里同样遵循 delayed import 规则。基础安装环境可以正常 ``import hubvault``；
只有当 remote client 真正尝试建立 HTTP transport 时，才会报告缺失 extra。

连接到服务端
------------

把 client 指到服务端 API 根路径，通常是 ``/api/v1``：

.. code-block:: python

    from hubvault.remote import HubVaultRemoteApi

    api = HubVaultRemoteApi(
        "http://127.0.0.1:9472/api/v1",
        token="dev-token",
        revision="main",
    )

    repo = api.repo_info()
    print(repo.default_branch)

它的命名会尽量镜像 :class:`hubvault.api.HubVaultApi`，因此在本地和 remote 两种
使用方式之间切换时，不需要重新建立一套完全不同的心智模型。

读取侧示例
----------

列出文件并读取一个 blob：

.. code-block:: python

    print(api.list_repo_tree(recursive=True))
    print(api.read_bytes("README.md").decode("utf-8"))

生成一个 detached 本地下载路径：

.. code-block:: python

    local_path = api.hf_hub_download("artifacts/model.safetensors")
    print(local_path)

生成完整 detached snapshot：

.. code-block:: python

    snapshot_dir = api.snapshot_download()
    print(snapshot_dir)

写入侧示例
----------

上传单个文件：

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.bin",
        commit_message="upload model through remote api",
    )

上传目录并显示本地进度条：

.. code-block:: python

    api.upload_folder(
        folder_path="artifacts/",
        path_in_repo="exports",
        commit_message="sync export folder",
        show_progress=True,
    )

如果你要把进度集成进自己的 UI，可以传入一个接收 ``(sent_bytes,
total_bytes)`` 的回调：

.. code-block:: python

    def on_progress(sent, total):
        print("upload", sent, total)

    api.upload_file(
        path_or_fileobj="model.bin",
        path_in_repo="artifacts/model.bin",
        progress_callback=on_progress,
    )

历史与 refs
-----------

远端历史和 refs 仍然返回与本地读路径一致的公开模型：

.. code-block:: python

    print(api.list_repo_commits())
    print(api.list_repo_refs())
    print(api.get_commit_detail("main"))

认证说明
--------

服务端使用 bearer token。读写 token 可以执行读写请求；只读 token 只能访问只读
路径。

当服务端拒绝认证时，client 会抛出 :mod:`hubvault.remote.errors` 里的公开错误
类型。

下一步
------

如果你还想通过浏览器界面访问同一套仓库表面，继续阅读
:doc:`../webui/index_zh`。
