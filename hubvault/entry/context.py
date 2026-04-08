"""
CLI repository-context helpers for :mod:`hubvault.entry`.

This module centralizes repository-path resolution for CLI commands and keeps
repo discovery on top of the public :class:`hubvault.api.HubVaultApi`
surface. The CLI deliberately does not inspect private storage files directly
just to discover the default branch or other repository metadata.

The module contains:

* :class:`CliRepoContext` - Resolved CLI view of one local repository
* :func:`set_cli_repo_path` - Persist the global ``-C`` repo path in Click context
* :func:`get_cli_repo_path` - Resolve the repo path configured for the current CLI run
* :func:`load_cli_repo_context` - Build and cache repository metadata for CLI commands

Example::

    >>> import click
    >>> ctx = click.Context(click.Command("demo"))
    >>> with ctx:
    ...     set_cli_repo_path(ctx, None)
    ...     str(get_cli_repo_path(ctx)).endswith(str(get_cli_repo_path(ctx).name))
    True
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from .. import HubVaultApi


@dataclass(frozen=True)
class CliRepoContext:
    """
    Describe the repository selection used by CLI commands.

    :param repo_path: Filesystem path to the local repository root
    :type repo_path: pathlib.Path
    :param default_branch: Repository default branch resolved through the
        public API
    :type default_branch: str

    Example::

        >>> context = CliRepoContext(repo_path=Path("/tmp/repo"), default_branch="main")
        >>> context.default_branch
        'main'
    """

    repo_path: Path
    default_branch: str

    @classmethod
    def from_repo_path(cls, repo_path: Path) -> "CliRepoContext":
        """
        Build CLI repository metadata from a local repository path.

        :param repo_path: Filesystem path to the local repository root
        :type repo_path: pathlib.Path
        :return: Resolved CLI repository context
        :rtype: CliRepoContext

        Example::

            >>> context = CliRepoContext.from_repo_path  # doctest: +SKIP
        """

        probe_api = HubVaultApi(repo_path)
        refs = probe_api.list_repo_refs()
        if not refs.branches:
            raise click.ClickException("Repository does not expose any branches.")

        candidate_branch = None
        for ref in refs.branches:
            if ref.name == "main":
                candidate_branch = ref.name
                break
        if candidate_branch is None:
            candidate_branch = refs.branches[0].name

        info = probe_api.repo_info(revision=candidate_branch)
        return cls(repo_path=repo_path, default_branch=info.default_branch)

    def create_api(self, revision: Optional[str] = None) -> HubVaultApi:
        """
        Build a public API wrapper scoped to this repository context.

        :param revision: Optional default revision for subsequent API calls.
            When omitted, the repository default branch is used.
        :type revision: Optional[str]
        :return: Public repository API wrapper
        :rtype: hubvault.api.HubVaultApi

        Example::

            >>> context = CliRepoContext(repo_path=Path("/tmp/repo"), default_branch="main")
            >>> context.create_api("main").__class__.__name__
            'HubVaultApi'
        """

        return HubVaultApi(self.repo_path, revision=revision or self.default_branch)


def set_cli_repo_path(ctx: click.Context, repo_path: Optional[str]) -> None:
    """
    Persist the global CLI repo path in the current Click context.

    :param ctx: Click context for the current CLI invocation
    :type ctx: click.Context
    :param repo_path: Repo path from the global ``-C`` option, or ``None`` to
        use the current working directory
    :type repo_path: Optional[str]
    :return: ``None``.
    :rtype: None

    Example::

        >>> ctx = click.Context(click.Command("demo"))
        >>> with ctx:
        ...     set_cli_repo_path(ctx, None)
        ...     "repo_path" in ctx.obj
        True
    """

    ctx.ensure_object(dict)
    resolved = Path(repo_path or ".").expanduser().resolve()
    ctx.obj["repo_path"] = str(resolved)


def get_cli_repo_path(ctx: click.Context) -> Path:
    """
    Return the repo path configured for the current CLI invocation.

    :param ctx: Click context for the current CLI invocation
    :type ctx: click.Context
    :return: Resolved repository path
    :rtype: pathlib.Path

    Example::

        >>> ctx = click.Context(click.Command("demo"))
        >>> with ctx:
        ...     set_cli_repo_path(ctx, None)
        ...     isinstance(get_cli_repo_path(ctx), Path)
        True
    """

    ctx.ensure_object(dict)
    return Path(ctx.obj.get("repo_path", str(Path.cwd()))).expanduser().resolve()


def load_cli_repo_context(ctx: click.Context) -> CliRepoContext:
    """
    Build and cache repository metadata for CLI commands.

    :param ctx: Click context for the current CLI invocation
    :type ctx: click.Context
    :return: Cached repository context
    :rtype: CliRepoContext

    Example::

        >>> context_loader = load_cli_repo_context  # doctest: +SKIP
    """

    ctx.ensure_object(dict)
    cached = ctx.obj.get("repo_context")
    if isinstance(cached, CliRepoContext):
        return cached

    repo_context = CliRepoContext.from_repo_path(get_cli_repo_path(ctx))
    ctx.obj["repo_context"] = repo_context
    return repo_context
