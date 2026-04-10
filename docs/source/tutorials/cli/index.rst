CLI Workflow
============

This guide explains how to use the public CLI as a practical day-to-day
interface. The commands intentionally feel Git-like, but they still reflect
``hubvault``'s own repository model rather than a mutable Git workspace.

.. contents:: On this page
    :local:

The one CLI rule to remember
----------------------------

``hubvault`` has **no mutable workspace**. That means:

* there is no staging area
* there is no "prepare now, commit later" ``git add`` step
* the ``commit`` command itself directly describes the repository mutation

If you keep that in mind, the CLI becomes much easier to reason about.

Targeting a repository
----------------------

The CLI is installed under two equivalent names:

* ``hubvault``
* ``hv``

This guide uses ``hubvault`` for readability. Use ``-C`` to target a
repository explicitly:

.. code-block:: shell

    hubvault -C demo-repo status

That pattern is recommended for scripts because the target repository is always
visible in the command itself.

Step 1: initialize the repository
---------------------------------

Create a repository:

.. code-block:: shell

    hubvault init demo-repo
    # Initialized empty HubVault repository in demo-repo

``init`` creates the repository and its initial empty history root. You can
also change the default branch name with ``-b`` or set a custom
``--large-file-threshold`` when needed.

Step 2: make your first real content commit
-------------------------------------------

Create a file locally and commit it explicitly:

.. code-block:: shell

    printf 'weights-v1' > model.bin
    hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
    # [main <commit>] add weights

The ``commit`` command accepts explicit operations:

* ``--add <repo_path>=<local_path>``
* ``--delete <repo_path>``
* ``--copy <src>=<dest>``

There is no hidden workspace scan. What you specify is what the commit does.

Step 3: inspect status, history, and tree state
-----------------------------------------------

Use the read-only commands to inspect current state:

.. code-block:: shell

    hubvault -C demo-repo status

    hubvault -C demo-repo log --oneline
    # <commit> add weights
    # <commit> Initial commit

    hubvault -C demo-repo ls-tree -r
    # 040000 tree <oid>  artifacts
    # 100644 blob <oid>  artifacts/model.bin

The exact IDs differ per run, but the output shape is stable and intentionally
Git-like.

Step 4: branch and commit elsewhere
-----------------------------------

Create a feature branch:

.. code-block:: shell

    hubvault -C demo-repo branch feature

List branches:

.. code-block:: shell

    hubvault -C demo-repo branch

Show the current branch:

.. code-block:: shell

    hubvault -C demo-repo branch --show-current

Now commit directly to ``feature``:

.. code-block:: shell

    printf '# CLI demo\n' > README.md
    hubvault -C demo-repo commit -r feature -m "add readme" --add README.md=./README.md
    # [feature <commit>] add readme

Using ``-r`` or ``--revision`` is the CLI way to choose which branch receives
the commit.

Step 5: create and inspect tags
-------------------------------

Create a tag at a chosen revision:

.. code-block:: shell

    hubvault -C demo-repo tag v0.1.0 feature -m "feature preview"

List tags:

.. code-block:: shell

    hubvault -C demo-repo tag -l

Delete a tag when you no longer need it:

.. code-block:: shell

    hubvault -C demo-repo tag -d v0.1.0

Tags are useful for stable release-like labels, validated checkpoints, or
important review points.

Step 6: merge back into main
----------------------------

Merge the feature branch into ``main``:

.. code-block:: shell

    hubvault -C demo-repo merge feature --target main

Depending on history shape, the command may:

* fast-forward ``main``
* create a merge commit
* report a structured conflict and leave ``main`` unchanged

Inspect the post-merge history:

.. code-block:: shell

    hubvault -C demo-repo log main --oneline -n 5

Step 7: use download and snapshot safely
----------------------------------------

When you need a real path on disk, use the read-facing commands:

.. code-block:: shell

    hubvault -C demo-repo download README.md
    # .../README.md

    hubvault -C demo-repo snapshot
    # .../snapshot/<id>/...

These are detached user views, just like the Python API. They are safe for
reading, exporting, or handing to another tool. They are not writable aliases
of committed repository truth.

Step 8: verify the repository
-----------------------------

Run verification after meaningful write operations:

.. code-block:: shell

    hubvault -C demo-repo verify
    # Quick verification OK

    hubvault -C demo-repo verify --full
    # Full verification OK

Use quick mode for routine post-write checks. Use full mode for deeper
maintenance or before archival handoff.

What the CLI deliberately does not do
-------------------------------------

The CLI looks similar to Git, but it intentionally avoids fake parity:

* no mutable checkout tree
* no staging area
* no remote / pull / push workflow
* no hidden mutation through download paths

That keeps the CLI honest about the repository model it is actually driving.

Complete CLI session
--------------------

.. code-block:: shell

    hubvault init demo-repo
    # Initialized empty HubVault repository in demo-repo

    printf 'weights-v1' > model.bin
    hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
    # [main <commit>] add weights

    hubvault -C demo-repo branch feature

    printf '# CLI demo\n' > README.md
    hubvault -C demo-repo commit -r feature -m "add readme" --add README.md=./README.md
    # [feature <commit>] add readme

    hubvault -C demo-repo tag v0.1.0 feature -m "feature preview"

    hubvault -C demo-repo merge feature --target main
    # Either fast-forward or merge-commit output, depending on history shape

    hubvault -C demo-repo log --oneline -n 5
    # <commit> ...

    hubvault -C demo-repo ls-tree -r
    # 100644 blob <oid>  README.md
    # 040000 tree <oid>  artifacts
    # 100644 blob <oid>  artifacts/model.bin

    hubvault -C demo-repo download README.md
    # .../README.md

    hubvault -C demo-repo snapshot
    # .../snapshot/<id>/...

    hubvault -C demo-repo verify
    # Quick verification OK

.. note::

   Exact commit IDs and materialized cache paths vary between runs. The stable
   part is the command shape and the repository semantics.
