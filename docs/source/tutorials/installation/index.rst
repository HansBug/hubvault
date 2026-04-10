Installation
============

This guide gets you from a clean Python environment to a verified ``hubvault``
installation. It also explains what is installed, what does **not** need to be
installed, and how to confirm that the Python API and CLI are both available.

.. contents:: On this page
    :local:

What gets installed
-------------------

Installing ``hubvault`` gives you two public entry points:

* the Python package, centered around :class:`hubvault.api.HubVaultApi`
* the command-line interface, exposed as both ``hubvault`` and ``hv``

The local repository format is self-contained. A repository is a directory on
disk; it does not require a server, daemon, external database service, or
global registry.

Runtime requirements
--------------------

The package supports Python ``>= 3.7`` and is intended to work across CPython
``3.7`` through ``3.14``. The repository format is designed for Windows,
mainstream Linux distributions, and macOS.

Internally, ``hubvault`` uses the Python standard-library ``sqlite3`` module for
repo-local metadata storage. You do not need to install or run a separate
SQLite server. Payload bytes remain normal files under the repository root.

Install from PyPI
-----------------

For normal usage, install the latest published release:

.. code-block:: shell

    pip install hubvault

When you manage multiple Python installations, prefer the explicit interpreter
form so you know exactly where the package is installed:

.. code-block:: shell

    python -m pip install hubvault

Install from the development branch
-----------------------------------

Use the development branch only when you intentionally need unreleased changes:

.. code-block:: shell

    python -m pip install -U git+https://github.com/hansbug/hubvault@main

Most users should start from PyPI. The development branch is useful for testing
fixes before a release, but it can change faster than the published package.

Verify the Python API
---------------------

First verify that Python can import the package and see the main public class:

.. code-block:: python

    from hubvault import HubVaultApi
    from hubvault.config.meta import __VERSION__

    print(HubVaultApi.__name__)
    # HubVaultApi

    print(__VERSION__)
    # 0.0.1  # value changes across releases

If this fails, fix the Python environment before debugging the CLI. The most
common cause is installing into one interpreter and running another one.

Verify the CLI
--------------

``hubvault`` installs two equivalent command names:

* ``hubvault``
* ``hv``

Check both names:

.. code-block:: shell

    hubvault -v
    hv -v

Expected output shape:

.. code-block:: text

    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).
    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).

The exact version changes by release, but both commands should exit
successfully and report the same version.

Inspect the top-level help once:

.. code-block:: shell

    hubvault --help

The command list should include the user-facing operations such as ``init``,
``commit``, ``branch``, ``tag``, ``merge``, ``log``, ``ls-tree``, ``download``,
``snapshot``, ``verify``, ``reset``, and ``status``.

Run a minimal repository check
------------------------------

After import and CLI checks pass, create a throwaway repository to verify the
full local stack:

.. code-block:: shell

    hubvault init /tmp/hubvault-install-check
    printf 'hello' > /tmp/hubvault-install-check.txt
    hubvault -C /tmp/hubvault-install-check commit \
        -m "seed" \
        --add demo.txt=/tmp/hubvault-install-check.txt
    hubvault -C /tmp/hubvault-install-check verify

That sequence verifies that repository creation, explicit commit, metadata
storage, and verification can all run in your environment.

Troubleshooting
---------------

If import works but the CLI does not:

* verify that the ``pip`` environment matches the active ``PATH``
* try ``python -m pip install hubvault`` instead of a bare ``pip``
* confirm that the environment's script directory is on ``PATH``

If the CLI works but Python import fails:

* check ``python -c "import sys; print(sys.executable)"``
* reinstall using that exact interpreter
* remove stale virtual environments from your shell path

If repository creation fails:

* ensure the target directory is writable
* avoid paths blocked by platform-specific reserved names
* retry in a short local path when testing on older Windows systems

Inline verification examples
----------------------------

Python-side verification:

.. code-block:: python

    from hubvault import HubVaultApi
    from hubvault.config.meta import __VERSION__

    print(HubVaultApi.__name__)   # HubVaultApi
    print(__VERSION__)            # 0.0.1  # actual value varies by release

CLI-side verification:

.. code-block:: shell

    hubvault -v                   # Hubvault, version 0.0.1.
    hv -v                         # Hubvault, version 0.0.1.
    hubvault --help               # lists init/commit/branch/tag/log/download/snapshot/verify/...
    hubvault init install-check   # Initialized empty HubVault repository in install-check
    hubvault -C install-check verify
    # Quick verification OK

Next step
---------

Continue with :doc:`../quick_start/index` to create a real repository, make
commits, read files, and materialize detached download views.

Online documentation is available at
`https://hansbug.github.io/hubvault/main/index_en.html <https://hansbug.github.io/hubvault/main/index_en.html>`_.
