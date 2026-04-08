CLI Workflow
============

This guide explains how to use the public CLI as a practical day-to-day
interface. The command names and general hand-feel are intentionally close to
Git, but the CLI still represents hubvault's own repository model.

.. contents:: On this page
    :local:

The most important CLI rule
---------------------------

hubvault does **not** provide a mutable workspace. That means:

* there is no staging area
* there is no ``git add`` equivalent that merely prepares state
* a ``commit`` command directly describes the repository mutation you want

This is the single biggest difference to keep in mind when reading the command
examples below.

Command names and targeting a repo
----------------------------------

The CLI is installed under two equivalent names:

* ``hubvault``
* ``hv``

This guide uses ``hubvault`` for readability. Use ``-C`` to target a repository
from outside its root:

.. code-block:: shell

    hubvault -C demo-repo status

That pattern is recommended for scripts because it makes the target repo
explicit in every command.

Step 1: initialize and create the first real commit
---------------------------------------------------

Create a repository:

.. code-block:: shell

    hubvault init demo-repo
    # Initialized empty HubVault repository in demo-repo

The repository already contains an ``Initial commit`` at this point. Next,
create a normal content commit:

.. code-block:: shell

    printf 'weights-v1' > model.bin
    hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
    # [main <commit>] add weights

The ``commit`` command accepts explicit operations instead of scanning a mutable
workspace:

* ``--add <repo_path>=<local_path>``
* ``--delete <repo_path>``
* ``--copy <src>=<dest>``

Step 2: branch and commit on another ref
----------------------------------------

Create a feature branch and commit to it explicitly:

.. code-block:: shell

    hubvault -C demo-repo branch feature
    printf '# CLI demo\n' > README.md
    hubvault -C demo-repo commit -r feature -m "add readme" --add README.md=./README.md
    # [feature <commit>] add readme

Using ``-r`` or ``--revision`` is the CLI equivalent of choosing a target branch
for the commit API.

Step 3: merge, inspect history, and list trees
----------------------------------------------

Merge the feature branch back:

.. code-block:: shell

    hubvault -C demo-repo merge feature --target main
    # Updating <old>..<new>
    # Fast-forward

Then inspect the result:

.. code-block:: shell

    hubvault -C demo-repo log --oneline
    # <commit> add readme
    # <commit> add weights
    # <commit> Initial commit

    hubvault -C demo-repo ls-tree -r
    # 100644 blob <oid>  README.md
    # 040000 tree <oid>  artifacts
    # 100644 blob <oid>  artifacts/model.bin

The exact IDs differ per run, but the output shape is stable and intentionally
Git-like.

Step 4: use read-facing commands safely
---------------------------------------

When you need a real path on disk, use ``download`` or ``snapshot``:

.. code-block:: shell

    hubvault -C demo-repo download README.md
    # .../README.md

    hubvault -C demo-repo snapshot
    # .../snapshot/<id>/...

Just like the Python API, these are detached user views. They are meant for
reading, exporting, or handing off to another tool, not for mutating committed
repository truth in place.

Step 5: verify the repository
-----------------------------

Run verification after meaningful write operations:

.. code-block:: shell

    hubvault -C demo-repo verify
    # Quick verification OK

    hubvault -C demo-repo verify --full
    # Full verification OK

Use the quick mode for a cheap normal post-write check, and the full mode when
you want deeper object/store validation.

What this CLI deliberately does not do
--------------------------------------

The CLI looks similar to Git, but hubvault intentionally avoids fake parity:

* no workspace status for unstaged file edits
* no ``checkout`` into a mutable tree
* no remote/push/pull commands
* no hidden mutation through download paths

That keeps the CLI honest about the underlying storage model.

Companion runnable example
--------------------------

Full runnable shell script:

.. literalinclude:: cli_workflow.demo.sh
    :language: shell
    :linenos:

Observed output:

.. literalinclude:: cli_workflow.demo.sh.txt
    :language: text
    :linenos:

.. note::

   The companion script demonstrates a fast-forward merge path. A divergent
   history can instead produce a merge commit or a structured conflict result,
   as shown in the Python workflow tutorial.
