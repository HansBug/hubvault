Welcome to hubvault
===================

Overview
--------

**hubvault** is an early-stage Python project for a local, embedded, API-first versioned repository for large machine learning artifacts such as model weights, datasets, and training outputs. The intended user experience is close to ``huggingface_hub.HfApi``, but without requiring an external service, database, or daemon.

Status
------

.. note::

   hubvault is still in the bootstrap stage. The current repository provides packaging, CI, documentation scaffolding, and a small CLI shell. The storage engine and public repository API described in the design notes are still under active implementation.

Design Goals
------------

hubvault is designed around a few strict goals:

* **Local-first storage**: keep repositories on a single machine with no external dependency
* **Versioned artifacts**: support immutable commits, trees, refs, and large-file content storage
* **Strong consistency**: prefer transactional correctness and crash safety over convenience shortcuts
* **Python API focus**: expose repository operations through a stable Python interface rather than a large CLI surface
* **Cross-platform support**: keep Linux, macOS, and Windows as first-class targets

What Exists Today
-----------------

The repository currently contains:

* ``hubvault.config`` for project metadata
* ``hubvault.entry`` for the Click-based CLI bootstrap and command wiring
* ``plan/init/`` for the initial scope, architecture, storage, consistency, and GC design baseline
* ``docs/`` for installation notes and generated API reference pages

The command line is intentionally minimal at this stage. The long-term product surface is the Python API for repository management.

Documentation
-------------

.. toctree::
    :maxdepth: 2
    :caption: Guides
    :hidden:

    tutorials/installation/index

* :doc:`tutorials/installation/index`

API Reference
-------------

.. include:: api_doc_en.rst

Design Notes
------------

The implementation roadmap lives in ``plan/init/`` in the repository. Those documents define the intended repo model, transactional write path, storage format, verification strategy, and garbage-collection plan.

Community and Support
---------------------

* **GitHub Repository**: https://github.com/HansBug/hubvault
* **Issue Tracker**: https://github.com/HansBug/hubvault/issues
* **PyPI Package**: https://pypi.org/project/hubvault/

License
-------

hubvault is released under the GNU General Public License v3.0. See the LICENSE file for details.
