"""
Command-line interface assembly for the hubvault entry points.

This module composes the top-level CLI command group by applying a sequence
of subcommand decorators. It exposes a ready-to-use Click group that includes
the available subcommands registered by :mod:`hubvault.entry.generate`,
:mod:`hubvault.entry.plantuml`, and :mod:`hubvault.entry.simulate`.

The module contains the following main component:

* :data:`cli` - Preconfigured Click command group with registered subcommands

Example::

    >>> from hubvault.entry.cli import cli
    >>> # ``cli`` is a click.Group and can be invoked by Click's command runner.
    >>> isinstance(cli.name, str)
    True

.. note::
   Subcommands are added by decorator functions that mutate the Click group in
   place and return it for chaining.
"""

from typing import Callable, List

import click

from .dispatch import hubvaultcli

_DECORATORS: List[Callable[[click.Group], click.Group]] = [
]

cli: click.Group = hubvaultcli
for deco in _DECORATORS:
    cli = deco(cli)
