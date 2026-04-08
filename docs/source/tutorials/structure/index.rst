Repository Structure and How It Works
=====================================

This guide explains the repository layout on disk and the design decisions
behind it. It is useful when you need to reason about portability, detached
views, large-file storage, or maintenance behavior.

.. contents:: On this page
    :local:

Why the on-disk layout matters
------------------------------

hubvault is intentionally a self-contained local repository format. That means
the directory structure is not an implementation accident; it is part of the
portability and safety story. The repository must continue to work after being:

* moved to another absolute path
* packed into an archive and restored later
* reopened by another process on the same or another machine

The top-level layout
--------------------

A repository root typically contains directories such as:

.. code-block:: text

    cache/
    chunks/
    locks/
    logs/
    objects/
    quarantine/
    refs/
    txn/

Each area has a distinct responsibility:

* ``objects/`` stores durable immutable objects such as commits, trees, files, and blobs
* ``refs/`` stores public branch and tag heads
* ``logs/refs/`` stores reflog history for ref updates
* ``chunks/`` stores pack/index data used by chunked large-file storage
* ``cache/`` stores detached user-view materializations
* ``locks/`` stores cross-process lock state
* ``txn/`` stores in-progress transactional staging state
* ``quarantine/`` stores isolated maintenance or recovery artifacts when needed

Keeping these roles separate makes verification, recovery, and garbage
collection easier to reason about.

Public file metadata versus internal storage
--------------------------------------------

hubvault intentionally distinguishes public file metadata from internal object
addressing.

For a public :class:`hubvault.models.RepoFile`, the important fields are:

* ``oid`` / ``blob_id``: the user-facing file identity aligned with Git/HF expectations
* ``sha256``: the user-facing content hash as a bare 64-hex digest
* ``lfs``: extra large-file metadata when the file is stored through the chunked path

These are not the same thing as every internal object identifier stored under
``objects/``. That separation is deliberate because public callers should be
able to reason about a file without depending on the engine's private storage
shape.

Small files and large files
---------------------------

hubvault uses two storage modes:

* small files stay in normal whole-file object storage
* files at or above ``large_file_threshold`` switch to chunked storage

From the public caller's perspective, the path stays the same either way:

.. code-block:: python

    small, large = api.get_paths_info(["artifacts/small.bin", "artifacts/large.bin"])

    print(small.lfs is None)
    # True

    print(large.lfs is not None)
    # True

    print(large.sha256)
    # 64-hex digest, value varies

Even when the file is chunked internally, ``hf_hub_download()`` still returns a
path ending with the original repo-relative suffix, such as
``artifacts/large.bin``.

Detached views are part of the structure
----------------------------------------

The ``cache/`` directory is not accidental clutter. It is where detached user
views live. This is how hubvault can return real file paths while still keeping
committed repository truth protected from in-place edits by user code.

That behavior supports an important guarantee:

* deleting or editing a downloaded file does not corrupt committed data
* the next read can rebuild the user view from repository truth

How a write works
-----------------

At a high level, a public write operation follows this pattern:

1. acquire the cross-process writer lock
2. stage objects and metadata under transaction-local state
3. publish immutable objects
4. update refs and reflogs atomically
5. clean temporary state and release the lock

If a process stops before completion, recovery rolls the repository back to the
last committed safe state. The intended observable rule is:

    If the write did not complete successfully, this operation is treated as if
    it never happened.

That rule is the reason the structure contains explicit transaction and recovery
areas instead of mutating committed data in place.

Companion runnable example
--------------------------

Full runnable script:

.. literalinclude:: structure.demo.py
    :language: python
    :linenos:

Observed output:

.. literalinclude:: structure.demo.py.txt
    :language: text
    :linenos:

.. note::

   Exact object IDs, file IDs, and pack/index counts vary with repository state.
   The stable points are the directory roles, chunk threshold behavior, and
   detached-view semantics.
