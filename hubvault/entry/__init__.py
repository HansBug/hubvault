"""
Entry points for the :mod:`hubvault.entry` package.

This package exposes the command-line interface (CLI) entry point for the
``hubvault`` application. The primary public object is the CLI group imported
as :data:`hubvaultcli`, which can be used to invoke CLI commands programmatically
or to register it with external tooling.

The package contains the following main components:

* :data:`hubvaultcli` - CLI group object for the ``hubvault`` command-line tool

Example::

    >>> from hubvault.entry import hubvaultcli
    >>> # The object is typically used by CLI frameworks.
    >>> # Actual invocation is usually handled by the CLI framework itself.

.. note::
   The underlying CLI implementation is defined in :mod:`hubvault.entry.cli`.
   This package module merely re-exports the CLI group for convenience.

"""

from .cli import cli as hubvaultcli

__all__ = ["hubvaultcli"]
