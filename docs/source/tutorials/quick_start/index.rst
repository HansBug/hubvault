Quick Start
===========

This guide walks through the shortest useful Python API lifecycle. You will
create a repository, commit files, inspect history, read committed content, and
materialize detached views for downstream tools.

.. contents:: On this page
    :local:

The model in one minute
-----------------------

``hubvault`` is not a mutable workspace. Keep three rules in mind:

* writes are explicit commits
* reads resolve a revision, usually ``main``
* download APIs return detached user views, not writable repository internals

That model is what makes the repository safe to move, archive, and reopen as a
single directory.

Step 1: create a repository
---------------------------

Start from an empty directory:

.. code-block:: python

    from pathlib import Path

    from hubvault import HubVaultApi

    repo_dir = Path("demo-repo")
    api = HubVaultApi(repo_dir)
    info = api.create_repo()

    print(info.default_branch)
    # main

    print(info.head is not None)
    # True

``create_repo()`` creates the repository layout and an empty ``Initial commit``.
The repository starts with a valid history root, so normal history APIs work
immediately.

Step 2: add a single file
-------------------------

Use :meth:`hubvault.api.HubVaultApi.upload_file` for the common one-file path:

.. code-block:: python

    weights_commit = api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.safetensors",
        commit_message="add model weights",
    )

    print(weights_commit.commit_message)
    # add model weights

The method writes a real commit. It does not copy into a staging area and wait
for a later action.

Step 3: make an explicit multi-operation commit
-----------------------------------------------

Use :meth:`hubvault.api.HubVaultApi.create_commit` when you want a commit made
from explicit operations:

.. code-block:: python

    from hubvault import CommitOperationAdd

    readme_commit = api.create_commit(
        operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
        commit_message="add readme",
    )

    print(len(readme_commit.oid))
    # 40

Commit IDs are Git-compatible 40-hex identifiers. The public result is
:class:`hubvault.models.CommitInfo`, aligned with commit-creation style APIs.

Step 4: inspect files and history
---------------------------------

Now inspect the repository through read APIs:

.. code-block:: python

    print(api.list_repo_files())
    # ['README.md', 'artifacts/model.safetensors']

    commits = api.list_repo_commits(formatted=True)
    print([item.title for item in commits])
    # ['add readme', 'add model weights', 'Initial commit']

    print(api.read_bytes("README.md").decode("utf-8").strip())
    # # Demo repo

Use these APIs for day-to-day questions:

* ``list_repo_files()``: what exists at this revision?
* ``list_repo_commits()``: what history produced this state?
* ``read_bytes()``: what are the exact committed bytes for one file?

Step 5: inspect metadata for paths
----------------------------------

Use ``get_paths_info()`` when you need public metadata rather than file bytes:

.. code-block:: python

    readme_info, model_info = api.get_paths_info(
        ["README.md", "artifacts/model.safetensors"]
    )

    print(readme_info.path)
    # README.md

    print(model_info.sha256 is not None)
    # True

The public file model exposes user-facing ``oid`` / ``blob_id`` / ``sha256``
values without requiring callers to understand the private storage layout.

Step 6: materialize detached views
----------------------------------

Some tools need a real path. Use ``hf_hub_download()`` for one file:

.. code-block:: python

    download_path = api.hf_hub_download("artifacts/model.safetensors")

    print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))
    # True

Use ``snapshot_download()`` for a whole tree:

.. code-block:: python

    snapshot_dir = Path(api.snapshot_download())
    files = sorted(
        str(path.relative_to(snapshot_dir)).replace("\\\\", "/")
        for path in snapshot_dir.rglob("*")
        if path.is_file()
    )
    print(files)
    # ['README.md', 'artifacts/model.safetensors']

These paths are detached views. Editing or deleting them does not corrupt
committed repository data, and the views can be regenerated later.

Step 7: verify the repository
-----------------------------

After meaningful writes, run the cheap integrity pass:

.. code-block:: python

    report = api.quick_verify()
    print(report.ok)
    # True

Use ``quick_verify()`` after normal operations. Use ``full_verify()`` for
maintenance windows, archival handoff, or suspicious repository states.

What this example demonstrates
------------------------------

The quick start covers the most important public guarantees:

* repositories are usable immediately after creation
* mutations happen only through explicit public write APIs
* commit IDs are Git-compatible
* read APIs resolve repository revisions
* download and snapshot paths preserve repo-relative suffixes
* detached views cannot mutate committed truth

Common mistakes
---------------

Avoid these assumptions:

* editing a downloaded file changes the repository
* there is a hidden mutable workspace
* cache paths are permanent public storage
* repository internals need to be edited manually

If you want a durable repository change, create a commit.

Complete example
----------------

.. code-block:: python

    from pathlib import Path

    from hubvault import CommitOperationAdd, HubVaultApi

    repo_dir = Path("demo-repo")
    api = HubVaultApi(repo_dir)

    info = api.create_repo()
    print(info.default_branch)          # main
    print(info.head is not None)        # True

    weights_commit = api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.safetensors",
        commit_message="add model weights",
    )
    print(weights_commit.commit_message)    # add model weights

    readme_commit = api.create_commit(
        operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
        commit_message="add readme",
    )
    print(len(readme_commit.oid))       # 40

    print(api.list_repo_files())
    # ['README.md', 'artifacts/model.safetensors']

    commits = api.list_repo_commits(formatted=True)
    print([item.title for item in commits])
    # ['add readme', 'add model weights', 'Initial commit']

    print(api.read_bytes("README.md").decode("utf-8").strip())
    # # Demo repo

    readme_info, model_info = api.get_paths_info(
        ["README.md", "artifacts/model.safetensors"]
    )
    print(readme_info.path)             # README.md
    print(model_info.sha256 is not None)    # True

    download_path = api.hf_hub_download("artifacts/model.safetensors")
    print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))
    # True

    snapshot_dir = Path(api.snapshot_download())
    files = sorted(
        str(path.relative_to(snapshot_dir)).replace("\\\\", "/")
        for path in snapshot_dir.rglob("*")
        if path.is_file()
    )
    print(files)
    # ['README.md', 'artifacts/model.safetensors']

    report = api.quick_verify()
    print(report.ok)                    # True

.. note::

   Commit IDs and cache paths vary between runs. The stable part is the public
   behavior: explicit commits, revision-based reads, and detached views.
