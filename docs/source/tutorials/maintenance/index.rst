Verification, GC, and History Squashing
=======================================

This guide explains how to keep a repository healthy after it has accumulated
real history and real data. The maintenance APIs are public on purpose: they are
part of normal operations, not hidden implementation details.

.. contents:: On this page
    :local:

When to use this guide
----------------------

Use these APIs when one of the following becomes true:

* you have written multiple generations of large files
* detached downloads or snapshots have filled the managed cache
* you need a health check before archiving or handing off a repository
* you want to reclaim bytes without guessing which directories are safe to delete

The maintenance workflow has four distinct parts: verify, analyze, reclaim, and
rewrite history when needed.

Step 1: start with verification
-------------------------------

hubvault exposes two public verification levels:

.. code-block:: python

    quick = api.quick_verify()
    print(quick.ok)
    # True

    full = api.full_verify()
    print(full.ok)
    # True

Use them differently:

* ``quick_verify()`` is the normal cheap integrity check after ordinary writes
* ``full_verify()`` is the deeper pass for maintenance windows, suspicious states, or before archival handoff

Step 2: inspect where space is going
------------------------------------

Before deleting anything, ask the repository for a storage breakdown:

.. code-block:: python

    overview = api.get_storage_overview()

    print(overview.total_size > 0)
    # True

    print(overview.historical_retained_size >= 0)
    # True

    print(overview.reclaimable_cache_size >= 0)
    # True

    print(overview.recommendations[:2])
    # ['...', '...']  # exact text varies by repository state

The important fields answer different questions:

* ``total_size``: how large is the repository footprint overall?
* ``historical_retained_size``: how many bytes are still retained by old history?
* ``reclaimable_cache_size``: how much detached-view cache can be dropped safely?
* ``reclaimable_gc_size``: how much space is already safe for GC to reclaim?
* ``recommendations``: what maintenance action does hubvault recommend next?

This gives you a basis for deciding whether cache pruning alone is enough or
whether history rewriting is required.

Step 3: preview garbage collection first
----------------------------------------

Do not guess. Run GC in dry-run mode first:

.. code-block:: python

    dry_gc = api.gc(dry_run=True, prune_cache=True)

    print(dry_gc.dry_run)
    # True

    print(dry_gc.notes[:2])
    # ['dry-run: ...', '...']  # exact notes vary

This tells you what hubvault would reclaim without mutating repository state.
That preview is especially useful when you are deciding whether to proceed with
cache pruning immediately.

Step 4: run GC for already reclaimable data
-------------------------------------------

If the dry run looks correct, execute it for real:

.. code-block:: python

    gc_report = api.gc(dry_run=False, prune_cache=True)

    print(gc_report.reclaimed_size >= 0)
    # True

    print(gc_report.removed_file_count >= 0)
    # True

Plain GC only reclaims data that is already safe to remove. If old history is
still reachable, those bytes remain retained on purpose.

Step 5: squash history when retention is the blocker
----------------------------------------------------

Large repositories often retain most of their space in old branch history. When
that happens, use ``squash_history()`` explicitly:

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

This operation rewrites the selected branch so old retained history becomes
unreachable and can then be reclaimed safely. It is the public, explicit answer
to "I need the current repository state, but I no longer need the full old
lineage on this branch."

How to decide what to run
-------------------------

A good practical order is:

1. run ``quick_verify()`` after normal writes
2. run ``full_verify()`` when doing serious maintenance or archival checks
3. inspect ``get_storage_overview()`` before deleting anything
4. run ``gc(dry_run=True)`` before real cleanup
5. use ``squash_history()`` only when old reachable history is the real space consumer

This avoids both under-cleaning and unsafe manual cleanup.

Companion runnable example
--------------------------

Full runnable script:

.. literalinclude:: maintenance.demo.py
    :language: python
    :linenos:

Observed output:

.. literalinclude:: maintenance.demo.py.txt
    :language: text
    :linenos:

.. note::

   Exact byte counts vary across platforms, Python versions, and filesystems.
   Focus on the meaning of each field and on the ordering of the maintenance
   actions.
