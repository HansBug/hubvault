Quick Start
===========

This guide walks through the shortest useful Python API lifecycle:

* create a local repository
* make a couple of commits through public APIs
* inspect files and commit history
* materialize detached single-file and snapshot views
* run a verification pass

It is intentionally written as an explanation-first guide. The runnable demo is
kept as a companion at the end, not as the entire tutorial.

.. contents:: On this page
    :local:

The mental model
----------------

The most important thing to understand before using hubvault is that it does
not expose a mutable workspace. Instead:

* writes happen through explicit public commit operations
* reads happen from a chosen revision, usually ``main``
* download APIs return detached user views when a filesystem path is required

If you keep that model in mind, the rest of the API should feel straightforward.

Step 1: create a repository
---------------------------

Start from an empty directory and initialize a repository:

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

The second line matters. ``create_repo()`` immediately creates an empty
``Initial commit`` so the repository begins life with a valid history root
instead of a special "not yet committed" state.

Step 2: write data through public commit APIs
---------------------------------------------

There are two common public write paths:

* convenience helpers such as :meth:`hubvault.api.HubVaultApi.upload_file`
* explicit operation lists passed to :meth:`hubvault.api.HubVaultApi.create_commit`

Use ``upload_file()`` when you want to add or replace one file directly:

.. code-block:: python

    weights_commit = api.upload_file(
        path_or_fileobj=b"weights-v1",
        path_in_repo="artifacts/model.safetensors",
        commit_message="add model weights",
    )

    print(weights_commit.commit_message)
    # add model weights

Then use ``create_commit()`` when you want to build a multi-operation commit
explicitly:

.. code-block:: python

    from hubvault import CommitOperationAdd

    readme_commit = api.create_commit(
        operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
        commit_message="add readme",
    )

    print(len(readme_commit.oid))
    # 40

You now have three commits in history:

* the automatic ``Initial commit``
* ``add model weights``
* ``add readme``

Step 3: inspect repository state
--------------------------------

Once the commits exist, use read/list APIs to confirm repository state:

.. code-block:: python

    print(api.list_repo_files())
    # ['README.md', 'artifacts/model.safetensors']

    print([item.title for item in api.list_repo_commits(formatted=True)])
    # ['add readme', 'add model weights', 'Initial commit']

    print(api.read_bytes("README.md").decode("utf-8").strip())
    # # Demo repo

This is the core day-to-day read path:

* ``list_repo_files()`` answers "what exists at this revision?"
* ``list_repo_commits()`` answers "how did we get here?"
* ``read_bytes()`` answers "what is the exact committed content?"

Step 4: materialize detached views
----------------------------------

Some workflows need an actual file path or a real directory tree. That is where
the download APIs come in.

Single-file download:

.. code-block:: python

    download_path = api.hf_hub_download("artifacts/model.safetensors")

    print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))
    # True

Snapshot download:

.. code-block:: python

    snapshot_dir = Path(api.snapshot_download())
    files = sorted(
        str(path.relative_to(snapshot_dir)).replace("\\\\", "/")
        for path in snapshot_dir.rglob("*")
        if path.is_file()
    )
    print(files)
    # ['README.md', 'artifacts/model.safetensors']

The key safety rule is that both outputs are detached views. They are usable as
normal files and directories, but they are not writable aliases of repository
truth. If a caller edits or deletes them, the committed repository data remains
safe and the view can be regenerated later.

Step 5: verify the repository
-----------------------------

After writes, the cheapest integrity pass is ``quick_verify()``:

.. code-block:: python

    report = api.quick_verify()
    print(report.ok)
    # True

Use this as the normal "did the repository still look healthy after my change?"
check. The deeper maintenance guide covers when to escalate to ``full_verify()``.

What to pay attention to
------------------------

This short example already demonstrates several important public guarantees:

* the repo is usable immediately after ``create_repo()``
* commits are explicit and return public models
* commit IDs are real 40-hex identifiers
* download paths preserve repo-relative suffixes
* downloads and snapshots are detached from committed truth

Common mistakes to avoid
------------------------

Do not treat hubvault like a mutable working tree:

* do not edit a downloaded file and expect that to mutate the repo
* do not expect an uncommitted workspace to exist
* do not depend on temporary cache paths remaining stable forever

If you want a repository change to persist, create a commit through the public
API.

Companion runnable example
--------------------------

Full runnable script:

.. literalinclude:: quick_start.demo.py
    :language: python
    :linenos:

Observed output:

.. literalinclude:: quick_start.demo.py.txt
    :language: text
    :linenos:

.. note::

   Commit IDs and temporary cache paths vary from run to run. The stable parts
   are the output shape and the repository semantics.
