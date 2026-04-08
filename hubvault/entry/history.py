"""
History-oriented CLI commands for :mod:`hubvault.entry`.

This module exposes git-like history browsing commands such as ``log`` on top
of the public ``hubvault`` API.

The module contains:

* :func:`register_history_commands` - Register history commands on a Click group
"""

from typing import Optional

import click

from .base import ClickErrorException, command_wrap
from .context import load_cli_repo_context
from .formatters import format_log_output
from .style import echo


def register_history_commands(group: click.Group) -> click.Group:
    """
    Register history commands on a Click command group.

    :param group: Click group receiving the registered commands
    :type group: click.Group
    :return: The same Click group for decorator chaining
    :rtype: click.Group

    Example::

        >>> import click
        >>> group = click.Group()
        >>> register_history_commands(group) is group
        True
    """

    @group.command("log")
    @click.argument("revision", required=False)
    @click.option("-n", "--max-count", default=None, type=int, help="Limit the number of commits to output.")
    @click.option("--oneline", is_flag=True, help="Show each commit on a single line.")
    @click.pass_context
    @command_wrap()
    def log_command(
        ctx: click.Context,
        revision: Optional[str],
        max_count: Optional[int],
        oneline: bool,
    ) -> None:
        """
        Show commit history for a revision.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param revision: Optional revision to inspect
        :type revision: Optional[str]
        :param max_count: Optional maximum number of commits to show
        :type max_count: Optional[int]
        :param oneline: Whether to use one-line output
        :type oneline: bool
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        selected_revision = revision or repo_context.default_branch
        api = repo_context.create_api(selected_revision)
        info = api.repo_info(revision=selected_revision)
        if info.head is None:
            raise ClickErrorException(
                "your current branch '{branch}' does not have any commits yet".format(
                    branch=selected_revision,
                )
            )

        commits = list(api.list_repo_commits(revision=selected_revision))
        if max_count is not None:
            commits = commits[:max_count]
        echo(format_log_output(commits, oneline=oneline))

    return group
