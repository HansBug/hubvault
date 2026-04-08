Branch, Tag, and Merge Workflow
===============================

This guide shows the normal "real work" path after the quick start:

* branch from an existing revision
* make independent commits on ``main`` and on a feature branch
* create a tag for a known-good point
* merge the feature branch back
* inspect refs, history, and reflog through public models

.. contents:: On this page
    :local:

Workflow mindset
----------------

hubvault borrows the history model from Git, but it still keeps hubvault's
explicit local semantics:

* refs point to commits
* commits are immutable
* merges update refs through the same transactional write path as normal commits
* conflict information is returned as structured public data rather than as a half-written repository state

Step 1: create the mainline history
-----------------------------------

Start with a normal repository and one seed commit on ``main``:

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("workflow-repo")
    api.create_repo()
    api.upload_file(
        path_or_fileobj=b"base-model",
        path_in_repo="weights/model.bin",
        commit_message="seed main",
    )

At this point, ``main`` contains a base model and the repository already has a
valid commit graph.

Step 2: branch and tag intentionally
------------------------------------

Create a feature branch from the current main tip:

.. code-block:: python

    api.create_branch(branch="feature")

Then advance that branch independently and tag a meaningful point:

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"feature-notes",
        path_in_repo="notes/feature.txt",
        revision="feature",
        commit_message="add feature note",
    )
    api.create_tag(tag="v0.1.0", revision="feature", tag_message="feature preview")

Tags are useful when you want a stable public label for an important feature tip
before it is merged.

Step 3: let ``main`` diverge
----------------------------

To demonstrate a real merge commit rather than a trivial fast-forward, move
``main`` as well:

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"main-doc",
        path_in_repo="docs/main.txt",
        revision="main",
        commit_message="add main doc",
    )

Now the two branches have diverged:

* ``feature`` contains ``notes/feature.txt``
* ``main`` contains ``docs/main.txt``

Step 4: merge the feature branch
--------------------------------

Run the merge:

.. code-block:: python

    result = api.merge(
        "feature",
        target_revision="main",
        commit_message="merge feature branch",
    )

    print(result.status)
    # merged

    print(result.fast_forward)
    # False

    print(result.created_commit)
    # True

    print(result.conflicts)
    # []

The returned object is a public :class:`hubvault.models.MergeResult`. Depending
on history shape, the merge can resolve as:

* ``fast-forward`` when the target can move directly to the source tip
* ``merged`` when a new merge commit is created
* ``conflict`` when hubvault detects incompatible changes and refuses to publish a partial result

Step 5: inspect files, refs, and history
----------------------------------------

After a successful merge, inspect the public surfaces instead of guessing:

.. code-block:: python

    print(api.list_repo_files(revision="main"))
    # ['docs/main.txt', 'notes/feature.txt', 'weights/model.bin']

    refs = api.list_repo_refs()
    print(sorted(ref.name for ref in refs.branches))
    # ['feature', 'main']

    print([item.title for item in api.list_repo_commits(revision="main", formatted=True)[:4]])
    # ['merge feature branch', 'add main doc', 'add feature note', 'seed main']

    print([item.message for item in api.list_repo_reflog("main")[:3]])
    # ['merge feature branch', 'add main doc', 'seed main']

This is the normal inspection set:

* ``list_repo_refs()`` tells you what refs exist
* ``list_repo_commits()`` shows user-facing history
* ``list_repo_reflog()`` explains how a branch head moved over time

How to think about conflicts
----------------------------

When a merge cannot be applied cleanly, hubvault does not leave the repository
in a partially merged state. Instead, it returns a ``MergeResult`` whose status
is ``conflict`` and whose ``conflicts`` field contains structured conflict
descriptions. The branch head remains unchanged.

That behavior is important because it preserves the repository's atomicity
guarantee: a failed merge is equivalent to no merge having happened.

Companion runnable example
--------------------------

Full runnable script:

.. literalinclude:: workflow.demo.py
    :language: python
    :linenos:

Observed output:

.. literalinclude:: workflow.demo.py.txt
    :language: text
    :linenos:

.. note::

   Commit IDs differ between runs. Focus on the history shape, merge status, and
   public fields rather than on the exact identifiers.
