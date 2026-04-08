"""
Command-line interface assembly for the hubvault entry points.

This module composes the top-level CLI command group by applying a sequence
of subcommand decorators. Each decorator registers one command family while
keeping the exported top-level group stable.

The module contains the following main component:

* :data:`cli` - Preconfigured Click command group with registered subcommands

Example::

    >>> from hubvault.entry.cli import cli
    >>> # ``cli`` is a click.Group and can be invoked by Click's command runner.
    >>> isinstance(cli.name, str)
    True

.. note::
   Subcommands are added by decorator functions that mutate the Click group in
   place and return it for chaining. The CLI stays on top of the public API
   and does not add a git workspace/index layer of its own.
"""

from typing import Callable, List

import click

from .content import register_content_commands
from .dispatch import hubvaultcli
from .history import register_history_commands
from .refs import register_ref_commands
from .repo import register_repo_commands

_DECORATORS: List[Callable[[click.Group], click.Group]] = [
    register_repo_commands,
    register_ref_commands,
    register_history_commands,
    register_content_commands,
]

cli: click.Group = hubvaultcli
for deco in _DECORATORS:
    cli = deco(cli)
