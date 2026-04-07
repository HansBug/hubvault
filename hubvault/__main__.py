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

"""
from .entry import hubvaultcli

if __name__ == '__main__':
    hubvaultcli()
