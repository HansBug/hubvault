Branch, Tag, and Merge Workflow
===============================

This guide covers the normal repository-history workflow after the quick start:
branching from an existing tip, making independent commits, creating tags,
merging back, inspecting refs, and understanding conflict behavior.

.. contents:: On this page
    :local:

Workflow mindset
----------------

``hubvault`` borrows the history model from Git, but it keeps its own local
repository semantics:

* refs point to immutable commits
* commits are created explicitly through public APIs
* merges are just another transactional repository update
* conflicts return structured data instead of leaving the repository half-merged

Step 1: create a mainline
-------------------------

Create a repository and seed ``main`` with one real content commit:

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("workflow-repo")
    api.create_repo()
    api.upload_file(
        path_or_fileobj=b"base-model",
        path_in_repo="weights/model.bin",
        commit_message="seed main",
    )

At this point, the repository already has:

* the automatic ``Initial commit``
* one real content commit on ``main``

Step 2: create a feature branch
-------------------------------

Branch from the current main tip:

.. code-block:: python

    feature_ref = api.create_branch(branch="feature")
    print(feature_ref.ref)
    # refs/heads/feature

You can also branch from another revision by passing ``revision=...``. That is
useful when you want to cut a release branch or preserve an older checkpoint.

Step 3: advance the feature branch
----------------------------------

Now make an independent commit on ``feature``:

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"feature-notes",
        path_in_repo="notes/feature.txt",
        revision="feature",
        commit_message="add feature note",
    )

At this point:

* ``main`` still points to the base model commit
* ``feature`` points to a newer tip containing ``notes/feature.txt``

Step 4: create a tag for a meaningful point
-------------------------------------------

If you want a stable public name for a known-good feature tip, create a tag:

.. code-block:: python

    tag_ref = api.create_tag(
        tag="v0.1.0",
        revision="feature",
        tag_message="feature preview",
    )
    print(tag_ref.ref)
    # refs/tags/v0.1.0

Tags are especially useful for release candidates, validated checkpoints, or
points you want to reference later without keeping a whole branch alive.

Step 5: let ``main`` diverge
----------------------------

To demonstrate a true merge commit instead of a trivial fast-forward, move
``main`` as well:

.. code-block:: python

    api.upload_file(
        path_or_fileobj=b"main-doc",
        path_in_repo="docs/main.txt",
        revision="main",
        commit_message="add main doc",
    )

Now the branches have diverged:

* ``feature`` contains ``notes/feature.txt``
* ``main`` contains ``docs/main.txt``

Step 6: merge the feature branch
--------------------------------

Merge the feature branch back into ``main``:

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

The returned object is :class:`hubvault.models.MergeResult`. Depending on the
history shape, merge results resolve as:

* ``fast-forward``: the target branch can move directly to the source tip
* ``merged``: a new merge commit is created
* ``already-up-to-date``: there is nothing to do
* ``conflict``: incompatible changes were detected and nothing was published

Step 7: inspect refs and history
--------------------------------

After the merge, inspect repository state through public surfaces:

.. code-block:: python

    print(api.list_repo_files(revision="main"))
    # ['docs/main.txt', 'notes/feature.txt', 'weights/model.bin']

    refs = api.list_repo_refs()
    print(sorted(ref.name for ref in refs.branches))
    # ['feature', 'main']

    print(sorted(ref.name for ref in refs.tags))
    # ['v0.1.0']

    print([item.title for item in api.list_repo_commits(revision="main", formatted=True)[:4]])
    # ['merge feature branch', 'add main doc', 'add feature note', 'seed main']

    print([item.message for item in api.list_repo_reflog("main")[:3]])
    # ['merge feature branch', 'add main doc', 'seed main']

These APIs answer different questions:

* ``list_repo_refs()``: which branches and tags currently exist?
* ``list_repo_commits()``: what is the user-facing history of a revision?
* ``list_repo_reflog()``: how did a branch head move over time?

Step 8: understand conflict handling
------------------------------------

When a merge cannot be applied cleanly, ``hubvault`` does **not** leave the
repository in a partially merged state. Instead:

* the target head stays where it was
* the merge returns ``status == "conflict"``
* ``result.conflicts`` contains structured conflict descriptions

That behavior preserves the atomic rule that a failed merge is equivalent to no
merge having happened.

Optional follow-up operations
-----------------------------

Once you are done with a feature branch, a common follow-up is:

* keep the branch if more work will continue there
* delete the branch if the tag and merged history are enough
* use ``reset_ref()`` when you need to move a branch head explicitly

Example branch reset:

.. code-block:: python

    earlier = api.list_repo_commits(revision="main")[1].commit_id
    api.reset_ref("main", to_revision=earlier)

That operation is explicit and should be treated like any other ref-moving
write: verify that you actually want the branch head to move.

Complete example
----------------

.. code-block:: python

    from hubvault import HubVaultApi

    api = HubVaultApi("workflow-repo")
    api.create_repo()
    api.upload_file(
        path_or_fileobj=b"base-model",
        path_in_repo="weights/model.bin",
        commit_message="seed main",
    )

    feature_ref = api.create_branch(branch="feature")
    print(feature_ref.ref)              # refs/heads/feature

    api.upload_file(
        path_or_fileobj=b"feature-notes",
        path_in_repo="notes/feature.txt",
        revision="feature",
        commit_message="add feature note",
    )

    tag_ref = api.create_tag(
        tag="v0.1.0",
        revision="feature",
        tag_message="feature preview",
    )
    print(tag_ref.ref)                  # refs/tags/v0.1.0

    api.upload_file(
        path_or_fileobj=b"main-doc",
        path_in_repo="docs/main.txt",
        revision="main",
        commit_message="add main doc",
    )

    result = api.merge(
        "feature",
        target_revision="main",
        commit_message="merge feature branch",
    )
    print(result.status)                # merged
    print(result.fast_forward)          # False
    print(result.created_commit)        # True
    print(result.conflicts)             # []

    print(api.list_repo_files(revision="main"))
    # ['docs/main.txt', 'notes/feature.txt', 'weights/model.bin']

    refs = api.list_repo_refs()
    print(sorted(ref.name for ref in refs.branches))
    # ['feature', 'main']
    print(sorted(ref.name for ref in refs.tags))
    # ['v0.1.0']

    print([item.title for item in api.list_repo_commits(revision="main", formatted=True)[:4]])
    # ['merge feature branch', 'add main doc', 'add feature note', 'seed main']

    print([item.message for item in api.list_repo_reflog("main")[:3]])
    # ['merge feature branch', 'add main doc', 'seed main']

.. note::

   Commit IDs vary between runs. Focus on the history shape, merge status, and
   public result fields rather than on exact identifiers.
