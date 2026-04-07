"""
Command-line entry point for the :mod:`hubvault` package.

This module exposes the console entry point that launches the CLI
implementation provided by :func:`hubvault.entry.hubvaultcli`. When the module
is executed as a script, it invokes the CLI handler.

The module contains the following main components:

* :func:`hubvault.entry.hubvaultcli` - CLI handler invoked on script execution

Example::

    >>> # Execute via Python module invocation
    >>> # python -m hubvault

.. note::
   The module intentionally stays minimal. The real CLI implementation lives in
   :mod:`hubvault.entry`, while this module only delegates execution when run as
   ``python -m hubvault``.
"""
from .entry import hubvaultcli

if __name__ == '__main__':
    hubvaultcli()
