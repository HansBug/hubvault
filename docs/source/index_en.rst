Welcome to hubvault
===================

Overview
--------

**hubvault** is a local, embedded, API-first repository system for versioning
large machine learning artifacts such as weights, datasets, and generated
outputs. The public API intentionally feels close to ``huggingface_hub`` where
that alignment improves usability, while the repository remains completely
self-contained on disk.

The shortest accurate description is:

* Git-like history and refs
* Hugging Face style file APIs
* a repository root that remains valid after moving, zipping, or restoring it
* explicit write operations and detached read views

What hubvault provides
----------------------

hubvault currently ships a working local repository surface with:

* Git-like commits, trees, refs, tags, reflogs, and merges
* Hugging Face style upload/download/list APIs on top of a local repo root
* Detached download and snapshot views that cannot corrupt committed data
* Chunked large-file storage together with public ``oid`` and ``sha256`` metadata
* Verification, storage analysis, garbage collection, and history squashing
* A git-like CLI exposed as both ``hubvault`` and ``hv``

What makes the project different
--------------------------------

hubvault is intentionally opinionated about a few things:

* **The repo root is the artifact.** There is no hidden sidecar database or external metadata service.
* **Read paths are detached views.** A file returned by ``hf_hub_download()`` is safe to read, but editing it must not mutate committed truth.
* **Writes are explicit.** The system does not pretend there is a mutable working tree.
* **Maintenance is public.** Verification, storage analysis, GC, and history squashing are first-class APIs.

Design constraints
------------------

hubvault is built around a few non-negotiable constraints:

* **Portable repository root**: moving or archiving a repo directory must not break it
* **Atomic writes**: interrupted writes are treated as if they never happened
* **Cross-process locking**: writers exclude other readers and writers during publication
* **Public API first**: examples and integrations should go through public models and commands
* **Cross-platform support**: Linux, macOS, and Windows remain first-class targets

Compatibility
-------------

hubvault aligns with Git / Hugging Face where that alignment is user-visible:

* commit/tree/blob IDs are Git-style 40-hex OIDs
* public file ``sha256`` values are bare 64-hex digests
* download paths preserve the original repo-relative suffix

hubvault intentionally differs where local embedded semantics matter:

* no remote service or pull request system
* no mutable workspace abstraction
* read-facing paths are detached views, not writable repository aliases

How to read this documentation
------------------------------

If you are new to the project, the best order is:

1. read :doc:`tutorials/installation/index`
2. work through :doc:`tutorials/quick_start/index`
3. continue with :doc:`tutorials/workflow/index` for branches, tags, and merge behavior
4. use :doc:`tutorials/cli/index` if you prefer a command-line workflow
5. study :doc:`tutorials/maintenance/index` before operating large long-lived repositories
6. read :doc:`tutorials/structure/index` when you need to understand storage layout and safety design

Tutorials
---------

.. toctree::
    :maxdepth: 2
    :caption: Tutorials
    :hidden:

    tutorials/installation/index
    tutorials/quick_start/index
    tutorials/workflow/index
    tutorials/cli/index
    tutorials/maintenance/index
    tutorials/structure/index

* :doc:`tutorials/installation/index`
  Install the package, verify both the Python API and the ``hubvault`` / ``hv`` CLI, and confirm the environment is usable.
* :doc:`tutorials/quick_start/index`
  Create a repo, make commits, read files, and understand detached download/snapshot views.
* :doc:`tutorials/workflow/index`
  Work with branches, tags, merge results, commit history, and reflog inspection.
* :doc:`tutorials/cli/index`
  Use the git-like CLI without assuming Git's mutable workspace model.
* :doc:`tutorials/maintenance/index`
  Decide when to use quick/full verification, GC, and history squashing.
* :doc:`tutorials/structure/index`
  Understand the on-disk layout, object semantics, chunked storage, and atomic transaction model.

API Reference
-------------

.. include:: api_doc_en.rst

Design Notes
------------

The implementation roadmap lives in ``plan/init/`` in the repository. Those
documents capture the design baseline, compatibility decisions, storage format,
atomicity model, and execution phases behind the current implementation.

Those design notes are useful if you need to understand why hubvault differs
from HF or Git in certain places, especially around detached views, explicit
write operations, cross-process locking, and rollback-only recovery.

Community and Support
---------------------

* **GitHub Repository**: https://github.com/HansBug/hubvault
* **Issue Tracker**: https://github.com/HansBug/hubvault/issues
* **PyPI Package**: https://pypi.org/project/hubvault/

License
-------

hubvault is released under the GNU General Public License v3.0. See the LICENSE file for details.
