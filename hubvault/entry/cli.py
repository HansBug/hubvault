"""
Command-line interface assembly for the hubvault entry points.

This module composes the top-level CLI command group by applying a sequence
of subcommand decorators. In the current repository state there are no extra
subcommands yet, so the exported group is the same top-level command defined in
:mod:`hubvault.entry.dispatch`.

The module contains the following main component:

* :data:`cli` - Preconfigured Click command group with registered subcommands

Example::

    >>> from hubvault.entry.cli import cli
    >>> # ``cli`` is a click.Group and can be invoked by Click's command runner.
    >>> isinstance(cli.name, str)
    True

.. note::
   Subcommands are added by decorator functions that mutate the Click group in
   place and return it for chaining. Phase 2 and later work may append
   decorators here while keeping the exported object stable.
"""

from typing import Callable, List

import click

from .dispatch import hubvaultcli

_DECORATORS: List[Callable[[click.Group], click.Group]] = [
]

cli: click.Group = hubvaultcli
for deco in _DECORATORS:
    cli = deco(cli)
