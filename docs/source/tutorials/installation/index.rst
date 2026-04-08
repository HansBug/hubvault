Installation
============

This guide explains what gets installed, how to verify that both the Python API
and CLI are available, and what to check before moving on to the real workflow
guides.

.. contents:: On this page
    :local:

What you install
----------------

``hubvault`` ships two public entry points:

* the Python package, centered around :class:`hubvault.api.HubVaultApi`
* the CLI, exposed as both ``hubvault`` and ``hv``

The project currently supports Python >= 3.7 and is tested across CPython 3.7
through 3.14. The same repository format is intended to remain portable across
Windows, mainstream Linux distributions, and macOS.

Install from PyPI
-----------------

For normal usage, install the latest published release:

.. code-block:: shell

    pip install hubvault

If you need the current development branch instead, install from GitHub:

.. code-block:: shell

    pip install -U git+https://github.com/hansbug/hubvault@main

Choose one of these paths. Most users should start from PyPI unless they are
testing an unreleased change.

Verify the Python API
---------------------

The first check is simply that the package imports and exposes the expected
public surface.

.. code-block:: python

    from hubvault import HubVaultApi
    from hubvault.config.meta import __VERSION__

    print(HubVaultApi.__name__)
    # HubVaultApi

    print(__VERSION__)
    # 0.0.1  # value changes across releases

That confirms the package can be imported and the main public API is available.
If this step fails, fix the Python environment before looking at the CLI.

Verify the CLI names
--------------------

hubvault installs two equivalent command names:

* ``hubvault``
* ``hv``

You should verify both names resolve correctly:

.. code-block:: shell

    hubvault -v
    hv -v

Expected output shape:

.. code-block:: text

    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).
    Hubvault, version 0.0.1.
    Developed by HansBug (...), narugo1992 (...).

The exact version will vary, but both commands should print the same version and
exit successfully.

You should also inspect the top-level help once:

.. code-block:: shell

    hubvault --help

The command list should include at least the currently supported public
subcommands such as ``init``, ``commit``, ``log``, ``download``, ``snapshot``,
``merge``, and ``verify``.

What to do if verification fails
--------------------------------

If import works but the CLI does not:

* verify that the Python environment used by ``pip`` matches the one on your ``PATH``
* try ``python -m pip install hubvault`` instead of a bare ``pip``
* confirm that the environment's script directory is on ``PATH``

If the CLI works but import fails:

* check that you are running the same interpreter you installed into
* inspect ``python -c "import sys; print(sys.executable)"``
* reinstall into the intended environment

Minimal automated checks
------------------------

The repository keeps runnable companion checks so the docs stay tied to real
behavior.

Python import check:

.. literalinclude:: install_check.demo.py
    :language: python
    :linenos:

Observed output:

.. literalinclude:: install_check.demo.py.txt
    :language: text
    :linenos:

CLI check:

.. literalinclude:: cli_check.demo.sh
    :language: shell
    :linenos:

Observed output:

.. literalinclude:: cli_check.demo.sh.txt
    :language: text
    :linenos:

Next step
---------

Once installation is verified, continue with :doc:`../quick_start/index`. That
guide builds a real repository, creates commits, reads committed files, and
shows how detached download/snapshot views behave.

Online documentation is available at
`https://hansbug.github.io/hubvault/main/index_en.html <https://hansbug.github.io/hubvault/main/index_en.html>`_.
