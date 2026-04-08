"""
Reference-management CLI commands for :mod:`hubvault.entry`.

This module exposes git-like branch and tag commands on top of the public
``hubvault`` API.

The module contains:

* :func:`register_ref_commands` - Register branch and tag commands on a Click group
"""

from typing import Dict, Optional

import click

from ..models import GitCommitInfo
from .base import ClickErrorException, command_wrap
from .context import load_cli_repo_context
from .formatters import format_branch_output, short_oid
from .style import echo, style_text


def register_ref_commands(group: click.Group) -> click.Group:
    """
    Register branch and tag commands on a Click command group.

    :param group: Click group receiving the registered commands
    :type group: click.Group
    :return: The same Click group for decorator chaining
    :rtype: click.Group

    Example::

        >>> import click
        >>> group = click.Group()
        >>> register_ref_commands(group) is group
        True
    """

    @group.command("branch")
    @click.option("-v", "--verbose", is_flag=True, help="Show commit and subject for each branch.")
    @click.option("--show-current", is_flag=True, help="Show the current branch name.")
    @click.option("-d", "delete_mode", is_flag=True, help="Delete a branch.")
    @click.option("-D", "force_delete", is_flag=True, help="Force-delete a branch.")
    @click.argument("branch", required=False)
    @click.argument("start_point", required=False)
    @click.pass_context
    @command_wrap()
    def branch_command(
        ctx: click.Context,
        verbose: bool,
        show_current: bool,
        delete_mode: bool,
        force_delete: bool,
        branch: Optional[str],
        start_point: Optional[str],
    ) -> None:
        """
        List, create, or delete branches.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param verbose: Whether verbose listing is requested
        :type verbose: bool
        :param show_current: Whether the current branch name should be printed
        :type show_current: bool
        :param delete_mode: Whether branch deletion is requested
        :type delete_mode: bool
        :param force_delete: Whether forced branch deletion is requested
        :type force_delete: bool
        :param branch: Branch name to create/delete
        :type branch: Optional[str]
        :param start_point: Optional revision used as the new branch base
        :type start_point: Optional[str]
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        api = repo_context.create_api()
        refs = api.list_repo_refs()

        if show_current:
            echo(repo_context.default_branch)
            return

        if delete_mode or force_delete:
            if not branch:
                raise ClickErrorException("branch -d/-D requires a branch name.")
            target_oid = None
            for ref in refs.branches:
                if ref.name == branch:
                    target_oid = ref.target_commit
                    break
            api.delete_branch(branch=branch)
            if target_oid is None:
                echo("Deleted branch {branch}.".format(branch=branch), tone="success")
            else:
                echo(
                    "Deleted branch {branch} (was {oid}).".format(
                        branch=branch,
                        oid=style_text(short_oid(target_oid), tone="accent"),
                    )
                )
            return

        if branch:
            api.create_branch(branch=branch, revision=start_point or repo_context.default_branch)
            return

        branch_names = [ref.name for ref in refs.branches]
        commit_map = {}  # type: Dict[str, Optional[GitCommitInfo]]
        if verbose:
            for ref in refs.branches:
                if ref.target_commit is None:
                    commit_map[ref.name] = None
                else:
                    commit_map[ref.name] = api.list_repo_commits(revision=ref.name)[:1][0]
        echo(
            format_branch_output(
                branch_names=branch_names,
                current_branch=repo_context.default_branch,
                commit_map=commit_map,
                verbose=verbose,
            )
        )

    @group.command("tag")
    @click.option("-l", "--list", "list_mode", is_flag=True, help="List tags.")
    @click.option("-d", "delete_mode", is_flag=True, help="Delete a tag.")
    @click.option("-m", "--message", "message", default=None, help="Optional tag message.")
    @click.argument("tag", required=False)
    @click.argument("revision", required=False)
    @click.pass_context
    @command_wrap()
    def tag_command(
        ctx: click.Context,
        list_mode: bool,
        delete_mode: bool,
        message: Optional[str],
        tag: Optional[str],
        revision: Optional[str],
    ) -> None:
        """
        List, create, or delete tags.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param list_mode: Whether tag listing is requested
        :type list_mode: bool
        :param delete_mode: Whether tag deletion is requested
        :type delete_mode: bool
        :param message: Optional tag message
        :type message: Optional[str]
        :param tag: Tag name to create/delete
        :type tag: Optional[str]
        :param revision: Optional revision used for tag creation
        :type revision: Optional[str]
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        api = repo_context.create_api()
        refs = api.list_repo_refs()

        if delete_mode:
            if not tag:
                raise ClickErrorException("tag -d requires a tag name.")
            target_oid = None
            for ref in refs.tags:
                if ref.name == tag:
                    target_oid = ref.target_commit
                    break
            api.delete_tag(tag=tag)
            if target_oid is None:
                echo("Deleted tag '{tag}'.".format(tag=tag), tone="success")
            else:
                echo(
                    "Deleted tag '{tag}' (was {oid}).".format(
                        tag=tag,
                        oid=style_text(short_oid(target_oid), tone="accent"),
                    )
                )
            return

        if tag and not list_mode:
            api.create_tag(
                tag=tag,
                revision=revision or repo_context.default_branch,
                tag_message=message,
            )
            return

        lines = [ref.name for ref in refs.tags]
        if lines:
            echo("\n".join(lines))

    return group
