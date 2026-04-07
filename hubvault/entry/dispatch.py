"""
Command-line interface entry point for the :mod:`hubvault` package.

This module defines the main Click command group used to expose the CLI for
the project, including version reporting and help configuration. It builds
user-facing metadata from the project configuration and provides a top-level
command entry point.

The module contains the following main components:

* :func:`hubvaultcli` - Main Click command group for the CLI

Example::

    >>> from hubvault.entry.dispatch import hubvaultcli
    >>> # Typically invoked via a Click entry point:
    >>> # python -m hubvault --help

.. note::
   The version display is implemented via a Click option callback, which
   prints version information and exits the process.

"""

import click
from click.core import Context, Option

from .base import CONTEXT_SETTINGS
from ..config.meta import __TITLE__, __VERSION__, __AUTHOR__, __AUTHOR_EMAIL__, __DESCRIPTION__

_raw_authors = [item.strip() for item in __AUTHOR__.split(',') if item.strip()]
_raw_emails = [item.strip() for item in __AUTHOR_EMAIL__.split(',')]
if len(_raw_emails) < len(_raw_authors):  # pragma: no cover
    _raw_emails += [None] * (len(_raw_authors) - len(_raw_emails))
elif len(_raw_emails) > len(_raw_authors):  # pragma: no cover
    _raw_emails[len(_raw_authors) - 1] = tuple(_raw_emails[len(_raw_authors) - 1:])
    del _raw_emails[len(_raw_authors):]

_author_tuples = [
    (author, tuple([item for item in (email if isinstance(email, tuple) else ((email,) if email else ())) if item]))
    for author, email in zip(_raw_authors, _raw_emails)
]
_authors = [
    author if not emails else '{author} ({emails})'.format(author=author, emails=', '.join(emails))
    for author, emails in _author_tuples
]


# noinspection PyUnusedLocal
def print_version(ctx: Context, param: Option, value: bool) -> None:
    """
    Print the version information for the CLI and exit.

    This callback is invoked by Click when the ``--version`` flag is provided.
    It prints the project title, version, and author list (if available), then
    exits the Click context.

    :param ctx: Click context for the current command invocation.
    :type ctx: :class:`click.core.Context`
    :param param: Current Click option metadata.
    :type param: :class:`click.core.Option`
    :param value: Boolean flag indicating whether the option was provided.
    :type value: bool
    :return: ``None``.
    :rtype: None
    :raises click.exceptions.Exit: Raised implicitly when :meth:`click.Context.exit`
        is invoked after printing version information.

    Example::

        >>> import click
        >>> from hubvault.entry.dispatch import print_version
        >>> ctx = click.Context(click.Command('demo'))
        >>> print_version(ctx, click.Option(['--version']), True)  # doctest: +SKIP

    """
    if not value or ctx.resilient_parsing:
        return  # pragma: no cover
    click.echo('{title}, version {version}.'.format(title=__TITLE__.capitalize(), version=__VERSION__))
    if _authors:
        click.echo('Developed by {authors}.'.format(authors=', '.join(_authors)))
    ctx.exit()


@click.group(context_settings=CONTEXT_SETTINGS, help=__DESCRIPTION__)
@click.option('-v', '--version', is_flag=True,
              callback=print_version, expose_value=False, is_eager=True,
              help="Show hubvault's version information.")
def hubvaultcli() -> None:
    """
    Main Click command group for the :mod:`hubvault` CLI.

    This command group provides a common entry point for subcommands and
    integrates global options such as ``--version`` and help flags.

    :return: ``None``.
    :rtype: None

    Example::

        >>> # Typically invoked via a console entry point:
        >>> # $ hubvault --help

    """
    pass  # pragma: no cover
