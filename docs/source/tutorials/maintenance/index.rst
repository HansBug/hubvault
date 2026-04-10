Verification, GC, and History Squashing
=======================================

This guide explains how to keep a repository healthy after it has accumulated
real history, detached caches, and multiple generations of artifacts. The
maintenance APIs are public on purpose: they are part of normal operation, not
hidden implementation details.

.. contents:: On this page
    :local:

When to use this guide
----------------------

Use the maintenance APIs when one or more of these becomes true:

* you have written multiple generations of large files
* detached downloads or snapshots have consumed noticeable cache space
* you want a health check before archiving or handing off a repository
* you need to reclaim bytes without guessing which internal directories are safe to delete

The maintenance flow has four distinct questions:

1. Is the repository healthy?
2. Where is the space going?
3. What is already safe to reclaim?
4. Is old reachable history the real blocker?

Step 1: start with verification
-------------------------------

``hubvault`` exposes two public verification levels:

.. code-block:: python

    quick = api.quick_verify()
    print(quick.ok)
    # True

    full = api.full_verify()
    print(full.ok)
    # True

Use them differently:

* ``quick_verify()`` is the cheap integrity check after ordinary writes
* ``full_verify()`` is the deeper pass for maintenance windows, suspicious
  states, migration checks, or archival handoff

The usual pattern is simple: quick after normal mutation, full before major
cleanup or handoff.

Step 2: inspect storage before deleting anything
------------------------------------------------

Before deleting files manually, ask the repository for a structured storage
overview:

.. code-block:: python

    overview = api.get_storage_overview()

    print(overview.total_size > 0)
    # True

    print(overview.reachable_size >= 0)
    # True

    print(overview.historical_retained_size >= 0)
    # True

    print(overview.reclaimable_gc_size >= 0)
    # True

    print(overview.reclaimable_cache_size >= 0)
    # True

These fields answer different questions:

* ``total_size``: how large is the repository footprint overall?
* ``reachable_size``: how much data is required to preserve current live refs?
* ``historical_retained_size``: how much space is still kept by old reachable
  history?
* ``reclaimable_gc_size``: how much can plain GC reclaim right now?
* ``reclaimable_cache_size``: how much detached-view cache can be dropped safely?
* ``reclaimable_temporary_size``: how much temporary or quarantine residue can
  be cleaned?

You also get:

* ``sections``: per-area storage breakdown
* ``recommendations``: ordered maintenance suggestions based on the current state

That is the basis for deciding whether a simple GC is enough or whether history
rewriting is required.

Step 3: preview GC first
------------------------

Run GC in dry-run mode before mutating anything:

.. code-block:: python

    dry_gc = api.gc(dry_run=True, prune_cache=True)

    print(dry_gc.dry_run)
    # True

    print(dry_gc.reclaimed_size >= 0)
    # True

    print(dry_gc.notes[:2])
    # ['dry-run: ...', '...']  # exact notes vary by repository state

Dry-run mode tells you what ``hubvault`` would reclaim without changing
repository state. That is especially useful when deciding whether cache pruning
alone is enough.

Step 4: run GC for already reclaimable data
-------------------------------------------

If the dry run looks correct, execute the real pass:

.. code-block:: python

    gc_report = api.gc(dry_run=False, prune_cache=True)

    print(gc_report.reclaimed_size >= 0)
    # True

    print(gc_report.removed_file_count >= 0)
    # True

    print(gc_report.reclaimed_cache_size >= 0)
    # True

Plain GC only reclaims data that is already safe to remove:

* unreachable object data
* unreachable chunk / pack data
* rebuildable detached cache data
* temporary or quarantine residue that no longer needs to be kept

If old history is still reachable from a branch, GC intentionally keeps it.

Step 5: use history squashing when old history is the blocker
-------------------------------------------------------------

Large repositories often retain most of their space in still-reachable branch
history. When that becomes the dominant storage cost, use
``squash_history()`` explicitly:

.. code-block:: python

    squash = api.squash_history(
        "main",
        commit_message="squash main history",
        run_gc=True,
        prune_cache=True,
    )

    print(squash.rewritten_commit_count >= 1)
    # True

    print(squash.dropped_ancestor_count >= 0)
    # True

    print(squash.blocking_refs)
    # []  # or other refs that still retain old lineage

``squash_history()`` keeps the branch tip's visible file state while making
older branch lineage unreachable from that branch. When ``run_gc=True``, the
method follows up with GC immediately so newly unreachable data can be reclaimed.

How to choose the right action
------------------------------

A practical order is:

1. run ``quick_verify()`` after normal writes
2. run ``full_verify()`` before serious maintenance or archival handoff
3. inspect ``get_storage_overview()``
4. preview ``gc(dry_run=True)``
5. run real ``gc()``
6. use ``squash_history()`` only when old reachable history is the real space consumer

That order prevents both under-cleaning and unsafe manual cleanup.

What not to do
--------------

Avoid these habits:

* deleting internal directories because they "look temporary"
* deleting cache, chunk, or object files by hand without checking overview/GC
* assuming GC rewrites reachable history
* assuming squashing is just an optimization with no history consequences

Use the public maintenance APIs. They already know how to preserve repository
truth while cleaning safe-to-remove state.

Complete maintenance example
----------------------------

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("maintenance-repo")
    api.create_repo(large_file_threshold=32)
    api.upload_file(
        path_or_fileobj=b"A" * 64,
        path_in_repo="model.bin",
        commit_message="seed v1",
    )
    api.upload_file(
        path_or_fileobj=b"B" * 64,
        path_in_repo="model.bin",
        commit_message="seed v2",
    )
    api.hf_hub_download("model.bin")    # populate one detached view

    quick = api.quick_verify()
    print(quick.ok)                     # True

    full = api.full_verify()
    print(full.ok)                      # True

    overview = api.get_storage_overview()
    print(overview.total_size > 0)      # True
    print(overview.reclaimable_cache_size >= 0)     # True
    print(overview.reclaimable_gc_size >= 0)        # True

    dry_gc = api.gc(dry_run=True, prune_cache=True)
    print(dry_gc.dry_run)               # True
    print(dry_gc.reclaimed_size >= 0)   # True

    gc_report = api.gc(dry_run=False, prune_cache=True)
    print(gc_report.reclaimed_size >= 0)        # True
    print(gc_report.removed_file_count >= 0)    # True

    squash = api.squash_history(
        "main",
        commit_message="squash main history",
        run_gc=True,
        prune_cache=True,
    )
    print(squash.rewritten_commit_count >= 1)   # True
    print(squash.dropped_ancestor_count >= 0)   # True

.. note::

   Exact byte counts differ across platforms, Python versions, and filesystems.
   The stable part is the meaning of each field and the ordering of the
   maintenance actions.
