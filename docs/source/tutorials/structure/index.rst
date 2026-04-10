Repository Structure and How It Works
=====================================

This guide explains the current on-disk repository layout and why that layout
matters for portability, detached views, large-file storage, maintenance, and
crash safety.

.. contents:: On this page
    :local:

Why the layout matters
----------------------

``hubvault`` is intentionally a self-contained local repository format. The
directory tree is not an implementation accident; it is part of the portability
and safety story.

A valid repository is expected to keep working after it is:

* moved to another absolute path
* packed into an archive and restored later
* reopened by another process on the same or another machine

Current top-level layout
------------------------

A typical repository root now looks like this:

.. code-block:: text

    FORMAT
    metadata.sqlite3
    cache/
    chunks/
    locks/
    objects/
    quarantine/
    txn/

The important responsibilities are:

* ``FORMAT``: repository format marker
* ``metadata.sqlite3``: steady-state metadata and object truth-store
* ``locks/``: repository-wide shared / exclusive lock file
* ``objects/blobs/*.data``: published blob payload bytes
* ``chunks/packs/*.pack``: published packed chunk payload bytes
* ``cache/``: detached file and snapshot views
* ``txn/``: in-progress staging and residue cleanup area
* ``quarantine/``: isolated recovery or maintenance leftovers when needed

What lives in SQLite versus the filesystem
------------------------------------------

The current repository model intentionally splits metadata truth from payload
bytes.

SQLite stores the repository's steady-state metadata and object records,
including:

* repository metadata
* refs
* reflog
* transaction journal state
* chunk visibility metadata
* commit / tree / file / blob metadata

The filesystem still stores large or immutable payload bytes:

* blob data files under ``objects/blobs/``
* packed chunk payload under ``chunks/packs/``
* detached user views under ``cache/``

This design gives the repository one repo-local metadata truth store while
keeping payload storage simple, portable, and easy to move with the repository.

What you should and should not treat as truth
---------------------------------------------

The key operational rule is:

* ``metadata.sqlite3`` is the steady-state metadata truth source
* detached caches are rebuildable views, not truth
* ``txn/`` and ``quarantine/`` are maintenance / recovery areas, not user data

Some directories from older layouts can still appear in a repository tree for
migration or compatibility reasons, but they should not be treated as the
primary truth source in current repositories.

Public file metadata versus private storage
-------------------------------------------

``hubvault`` intentionally separates public file identity from private storage
addressing.

For a public :class:`hubvault.models.RepoFile`, the important user-facing fields
are:

* ``path``: the repo-relative path
* ``oid`` / ``blob_id``: file identity in Git/HF style
* ``sha256``: the bare 64-hex content digest
* ``lfs``: extra large-file metadata when the file is stored through chunked mode

These public values are not simply a dump of internal storage records. That
separation is deliberate so public callers can reason about files without
depending on private engine details.

Small files and large files
---------------------------

``hubvault`` uses two storage modes:

* small files stay in ordinary object storage
* files at or above ``large_file_threshold`` switch to chunked storage

From the public caller's point of view, the repo path stays the same:

.. code-block:: python

    small, large = api.get_paths_info(["artifacts/small.bin", "artifacts/large.bin"])

    print(small.lfs is None)
    # True

    print(large.lfs is not None)
    # True

    print(large.sha256)
    # 64-hex digest, value varies

Even when the file is chunked internally, ``hf_hub_download()`` still returns a
path ending with the original repo-relative suffix such as
``artifacts/large.bin``.

Detached views are part of the design
-------------------------------------

The ``cache/`` area is not accidental clutter. It is the user-view layer that
allows ``hubvault`` to return real paths on disk without exposing writable
aliases of committed truth.

That supports an important guarantee:

* deleting or editing a downloaded file does not corrupt committed data
* the next read can rebuild the detached view from repository truth

This is why download and snapshot paths are safe to hand to other local tools.

How a write works at a high level
---------------------------------

A public write operation follows this broad pattern:

1. acquire the repository writer lock
2. stage payload and metadata changes under transaction-local state
3. publish immutable payload bytes
4. commit metadata truth atomically
5. clean residue and release the lock

The intended observable rule is simple:

    If a write does not complete successfully, the repository should look as if
    that write never happened.

That rollback-oriented behavior is one of the reasons ``hubvault`` keeps
explicit transaction and recovery areas instead of mutating committed truth in
place.

Why the structure supports portability
--------------------------------------

Because the repository keeps its durable state inside one root directory:

* there is no repo-external sidecar database to carry around
* there is no absolute-path binding in repository truth
* archive / restore workflows do not need a rebuild step just to reopen

This is the practical reason ``hubvault`` can act like a portable local
artifact repository rather than a cache that depends on host-local state.

Complete structure example
--------------------------

.. code-block:: python

    from pathlib import Path

    from hubvault import HubVaultApi

    repo_dir = Path("structure-repo")
    api = HubVaultApi(repo_dir)
    api.create_repo(large_file_threshold=32)

    api.upload_file(
        path_or_fileobj=b"small-file",
        path_in_repo="artifacts/small.bin",
        commit_message="add small file",
    )
    api.upload_file(
        path_or_fileobj=b"A" * 64,
        path_in_repo="artifacts/large.bin",
        commit_message="add large file",
    )

    print((repo_dir / "FORMAT").exists())               # True
    print((repo_dir / "metadata.sqlite3").exists())     # True
    print((repo_dir / "locks" / "repo.lock").exists())  # True

    small, large = api.get_paths_info(
        ["artifacts/small.bin", "artifacts/large.bin"]
    )
    print(small.lfs is None)            # True
    print(large.lfs is not None)        # True

    download_path = api.hf_hub_download("artifacts/large.bin")
    print(Path(download_path).as_posix().endswith("artifacts/large.bin"))
    # True

    overview = api.get_storage_overview()
    print(overview.total_size > 0)      # True

.. note::

   Exact IDs, file counts, and pack counts vary by repository state. The stable
   part is the role of each area, the split between metadata truth and payload
   bytes, and the detached-view semantics.
