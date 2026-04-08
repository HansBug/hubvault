"""
Content-oriented CLI commands for :mod:`hubvault.entry`.

This module exposes tree listing, detached download, snapshot export, and
verification commands on top of the public ``hubvault`` API.

The module contains:

* :func:`register_content_commands` - Register content and verification commands
"""

from typing import Optional

import click

from .base import ClickErrorException, command_wrap
from .context import load_cli_repo_context
from .formatters import format_ls_tree_output, format_verify_output


def register_content_commands(group: click.Group) -> click.Group:
    """
    Register content and verification commands on a Click command group.

    :param group: Click group receiving the registered commands
    :type group: click.Group
    :return: The same Click group for decorator chaining
    :rtype: click.Group

    Example::

        >>> import click
        >>> group = click.Group()
        >>> register_content_commands(group) is group
        True
    """

    @group.command("ls-tree")
    @click.argument("revision", required=False)
    @click.argument("path_in_repo", required=False)
    @click.option("-r", "--recursive", is_flag=True, help="Recurse into subtrees.")
    @click.pass_context
    @command_wrap()
    def ls_tree_command(
        ctx: click.Context,
        revision: Optional[str],
        path_in_repo: Optional[str],
        recursive: bool,
    ) -> None:
        """
        List a repository tree in a git-like format.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param revision: Optional revision to inspect
        :type revision: Optional[str]
        :param path_in_repo: Optional repo-relative directory path
        :type path_in_repo: Optional[str]
        :param recursive: Whether recursion is enabled
        :type recursive: bool
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        selected_revision = revision or repo_context.default_branch
        entries = repo_context.create_api(selected_revision).list_repo_tree(
            path_in_repo=path_in_repo,
            recursive=recursive,
            revision=selected_revision,
        )
        if entries:
            click.echo(format_ls_tree_output(entries))

    @group.command("download")
    @click.argument("path_in_repo")
    @click.option("-r", "--revision", default=None, help="Revision to inspect.")
    @click.option("--local-dir", default=None, type=click.Path(file_okay=False, dir_okay=True), help="Optional export directory.")
    @click.pass_context
    @command_wrap()
    def download_command(
        ctx: click.Context,
        path_in_repo: str,
        revision: Optional[str],
        local_dir: Optional[str],
    ) -> None:
        """
        Materialize a detached user-view path for one file.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Optional revision to inspect
        :type revision: Optional[str]
        :param local_dir: Optional export directory
        :type local_dir: Optional[str]
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        selected_revision = revision or repo_context.default_branch
        path = repo_context.create_api(selected_revision).hf_hub_download(
            path_in_repo,
            revision=selected_revision,
            local_dir=local_dir,
        )
        click.echo(path)

    @group.command("snapshot")
    @click.option("-r", "--revision", default=None, help="Revision to export.")
    @click.option("--local-dir", default=None, type=click.Path(file_okay=False, dir_okay=True), help="Optional export directory.")
    @click.pass_context
    @command_wrap()
    def snapshot_command(ctx: click.Context, revision: Optional[str], local_dir: Optional[str]) -> None:
        """
        Materialize a detached snapshot directory for one revision.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param revision: Optional revision to export
        :type revision: Optional[str]
        :param local_dir: Optional export directory
        :type local_dir: Optional[str]
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        selected_revision = revision or repo_context.default_branch
        path = repo_context.create_api(selected_revision).snapshot_download(
            revision=selected_revision,
            local_dir=local_dir,
        )
        click.echo(path)

    @group.command("verify")
    @click.option("--full", "full_mode", is_flag=True, help="Run the full verification pass.")
    @click.pass_context
    @command_wrap()
    def verify_command(ctx: click.Context, full_mode: bool) -> None:
        """
        Verify repository integrity.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param full_mode: Whether full verification is requested
        :type full_mode: bool
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        api = repo_context.create_api()
        report = api.full_verify() if full_mode else api.quick_verify()
        output = format_verify_output(report, full=full_mode)
        if not report.ok:
            raise ClickErrorException(output)
        click.echo(output)

    return group
