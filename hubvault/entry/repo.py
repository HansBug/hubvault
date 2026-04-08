"""
Repository-oriented CLI commands for :mod:`hubvault.entry`.

This module registers git-like local repository commands such as ``init``,
``status``, ``commit``, ``merge``, and ``reset``. The commands deliberately
stay on top of the public :class:`hubvault.api.HubVaultApi` surface and do not
invent git workspace semantics that the local repository does not support.

The module contains:

* :func:`register_repo_commands` - Register repository commands on a Click group
"""

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import click

from .. import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete, HubVaultApi
from ..errors import RepositoryNotFoundError
from .base import ClickErrorException, command_wrap
from .context import get_cli_repo_path, load_cli_repo_context
from .formatters import format_merge_output, format_status_output, short_oid
from .style import echo, style_text


def _split_mapping_spec(value: str, option_name: str) -> Tuple[str, str]:
    if "=" not in value:
        raise click.BadParameter(
            "{option} expects <repo_path>=<value>.".format(option=option_name)
        )
    left, right = value.split("=", 1)
    if not left or not right:
        raise click.BadParameter(
            "{option} expects non-empty <repo_path>=<value>.".format(option=option_name)
        )
    return left, right


def _build_commit_operations(
    add_specs: Sequence[str],
    delete_paths: Sequence[str],
    copy_specs: Sequence[str],
) -> List[object]:
    operations = []  # type: List[object]
    for add_spec in add_specs:
        path_in_repo, source_path = _split_mapping_spec(add_spec, "--add")
        operations.append(CommitOperationAdd(path_in_repo, source_path))
    for delete_path in delete_paths:
        operations.append(CommitOperationDelete(delete_path))
    for copy_spec in copy_specs:
        source_path, destination_path = _split_mapping_spec(copy_spec, "--copy")
        operations.append(CommitOperationCopy(source_path, destination_path))
    return operations


def register_repo_commands(group: click.Group) -> click.Group:
    """
    Register repository commands on a Click command group.

    :param group: Click group receiving the registered commands
    :type group: click.Group
    :return: The same Click group for decorator chaining
    :rtype: click.Group

    Example::

        >>> import click
        >>> group = click.Group()
        >>> register_repo_commands(group) is group
        True
    """

    @group.command("init")
    @click.argument("path", required=False, type=click.Path(file_okay=False, dir_okay=True))
    @click.option("-b", "--initial-branch", default="main", show_default=True, help="Set the initial branch name.")
    @click.option(
        "--large-file-threshold",
        default=None,
        type=int,
        help="Chunk files at or above this size in bytes.",
    )
    @click.pass_context
    @command_wrap()
    def init_command(
        ctx: click.Context,
        path: Optional[str],
        initial_branch: str,
        large_file_threshold: Optional[int],
    ) -> None:
        """
        Initialize a local repository.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param path: Optional target directory
        :type path: Optional[str]
        :param initial_branch: Initial branch name
        :type initial_branch: str
        :param large_file_threshold: Optional chunking threshold
        :type large_file_threshold: Optional[int]
        :return: ``None``.
        :rtype: None
        """

        repo_path = Path(path).expanduser().resolve() if path is not None else get_cli_repo_path(ctx)
        existing_repo = True
        try:
            HubVaultApi(repo_path).list_repo_refs()
        except RepositoryNotFoundError:
            existing_repo = False

        api = HubVaultApi(repo_path)
        kwargs = {"default_branch": initial_branch, "exist_ok": True}
        if large_file_threshold is not None:
            kwargs["large_file_threshold"] = large_file_threshold
        api.create_repo(**kwargs)

        template = "Reinitialized existing HubVault repository in {path}"
        if not existing_repo:
            template = "Initialized empty HubVault repository in {path}"
        echo(template.format(path=str(repo_path)), tone="success")

    @group.command("status")
    @click.option("-s", "--short", "short_mode", is_flag=True, help="Give the output in the short format.")
    @click.option("-b", "--branch", "show_branch", is_flag=True, help="Show branch information in the short format.")
    @click.pass_context
    @command_wrap()
    def status_command(ctx: click.Context, short_mode: bool, show_branch: bool) -> None:
        """
        Show repository status.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param short_mode: Whether short output is requested
        :type short_mode: bool
        :param show_branch: Whether branch output is included in short mode
        :type show_branch: bool
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        info = repo_context.create_api().repo_info()
        output = format_status_output(
            branch=repo_context.default_branch,
            head=info.head,
            short=short_mode,
            show_branch=show_branch,
        )
        if output:
            echo(output)

    @group.command("commit")
    @click.option("-m", "--message", "message", required=True, help="Commit message.")
    @click.option("--description", default=None, help="Optional commit description/body.")
    @click.option("-r", "--revision", default=None, help="Branch to update.")
    @click.option("--add", "add_specs", multiple=True, help="Add a file as <repo_path>=<local_path>.")
    @click.option("--delete", "delete_paths", multiple=True, help="Delete a repo path.")
    @click.option("--copy", "copy_specs", multiple=True, help="Copy a repo path as <src>=<dest>.")
    @click.pass_context
    @command_wrap()
    def commit_command(
        ctx: click.Context,
        message: str,
        description: Optional[str],
        revision: Optional[str],
        add_specs: Sequence[str],
        delete_paths: Sequence[str],
        copy_specs: Sequence[str],
    ) -> None:
        """
        Create a commit from explicit repository operations.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param message: Commit summary
        :type message: str
        :param description: Optional commit body
        :type description: Optional[str]
        :param revision: Optional target branch
        :type revision: Optional[str]
        :param add_specs: Add-operation specifications
        :type add_specs: Sequence[str]
        :param delete_paths: Delete-operation paths
        :type delete_paths: Sequence[str]
        :param copy_specs: Copy-operation specifications
        :type copy_specs: Sequence[str]
        :return: ``None``.
        :rtype: None
        """

        operations = _build_commit_operations(add_specs, delete_paths, copy_specs)
        if not operations:
            raise ClickErrorException("No operations provided. Use --add, --delete, or --copy.")

        repo_context = load_cli_repo_context(ctx)
        selected_revision = revision or repo_context.default_branch
        commit = repo_context.create_api(selected_revision).create_commit(
            operations=operations,
            revision=selected_revision,
            commit_message=message,
            commit_description=description,
        )
        echo(
            "[{revision} {oid}] {message}".format(
                revision=style_text(selected_revision, tone="accent"),
                oid=style_text(short_oid(commit.oid), tone="accent"),
                message=commit.commit_message,
            )
        )

    @group.command("merge")
    @click.argument("source_revision")
    @click.option("--target", "target_revision", default=None, help="Target branch to update.")
    @click.option("-m", "--message", "message", default=None, help="Merge commit message.")
    @click.option("--description", default=None, help="Optional merge commit body.")
    @click.pass_context
    @command_wrap()
    def merge_command(
        ctx: click.Context,
        source_revision: str,
        target_revision: Optional[str],
        message: Optional[str],
        description: Optional[str],
    ) -> None:
        """
        Merge one revision into a target branch.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param source_revision: Source revision to merge
        :type source_revision: str
        :param target_revision: Optional target branch
        :type target_revision: Optional[str]
        :param message: Optional merge commit message
        :type message: Optional[str]
        :param description: Optional merge commit body
        :type description: Optional[str]
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        selected_target = target_revision or repo_context.default_branch
        result = repo_context.create_api(selected_target).merge(
            source_revision=source_revision,
            target_revision=selected_target,
            commit_message=message,
            commit_description=description,
        )
        output = format_merge_output(result)
        if result.status == "conflict":
            raise ClickErrorException(output)
        echo(output, tone="success")

    @group.command("reset")
    @click.argument("to_revision")
    @click.option("-r", "--revision", default=None, help="Branch to move.")
    @click.pass_context
    @command_wrap()
    def reset_command(ctx: click.Context, to_revision: str, revision: Optional[str]) -> None:
        """
        Move a branch ref to another revision.

        :param ctx: Click context for the current command
        :type ctx: click.Context
        :param to_revision: Commit or revision to reset to
        :type to_revision: str
        :param revision: Optional branch to move
        :type revision: Optional[str]
        :return: ``None``.
        :rtype: None
        """

        repo_context = load_cli_repo_context(ctx)
        selected_revision = revision or repo_context.default_branch
        commit = repo_context.create_api(selected_revision).reset_ref(
            selected_revision,
            to_revision=to_revision,
        )
        echo(
            "HEAD is now at {oid} {message}".format(
                oid=style_text(short_oid(commit.oid), tone="accent"),
                message=commit.commit_message,
            )
        )

    return group
