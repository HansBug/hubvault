Remote Client Usage
===================

This guide shows how to talk to a running ``hubvault`` server from another
Python process through :class:`hubvault.remote.HubVaultRemoteApi`.

.. contents:: On this page
    :local:

Install the remote extra
------------------------

The remote client is optional:

.. code-block:: shell

    pip install 'hubvault[remote]'

The delayed-import rule still applies. Base installations can import
``hubvault`` normally; a missing extra is reported only when the client tries
to build an HTTP transport.

Connect to a server
-------------------

Point the client at the server API root, usually ``/api/v1``:

.. code-block:: python

    from hubvault.remote import HubVaultRemoteApi

    api = HubVaultRemoteApi(
        "http://127.0.0.1:9472/api/v1",
        token="dev-token",
        revision="main",
    )

    repo = api.repo_info()
    print(repo.default_branch)

The naming intentionally mirrors :class:`hubvault.api.HubVaultApi`, so moving
between local and remote usage does not require a different mental model.

Read-side examples
------------------

List files and read one blob:

.. code-block:: python

    print(api.list_repo_tree(recursive=True))
    print(api.read_bytes("README.md").decode("utf-8"))

Materialize a detached local download:

.. code-block:: python

    local_path = api.hf_hub_download("artifacts/model.safetensors")
    print(local_path)

Create a full detached snapshot:

.. code-block:: python

    snapshot_dir = api.snapshot_download()
    print(snapshot_dir)

Write-side examples
-------------------

Upload one file:

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.bin",
        commit_message="upload model through remote api",
    )

Upload a folder with a local progress bar:

.. code-block:: python

    api.upload_folder(
        folder_path="artifacts/",
        path_in_repo="exports",
        commit_message="sync export folder",
        show_progress=True,
    )

If you want to integrate progress into your own UI, pass a callback that
receives ``(sent_bytes, total_bytes)``:

.. code-block:: python

    def on_progress(sent, total):
        print("upload", sent, total)

    api.upload_file(
        path_or_fileobj="model.bin",
        path_in_repo="artifacts/model.bin",
        progress_callback=on_progress,
    )

History and refs
----------------

Remote history and refs use the same public models as local reads:

.. code-block:: python

    print(api.list_repo_commits())
    print(api.list_repo_refs())
    print(api.get_commit_detail("main"))

Authentication
--------------

The server uses bearer tokens. A read-write token can perform both read and
write calls; a read-only token is limited to read paths.

When the server rejects authentication, the client raises the public remote
error types under :mod:`hubvault.remote.errors`.

Next step
---------

Continue with :doc:`../webui/index` when you want the same repository surface
through the bundled browser frontend.
