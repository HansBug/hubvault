"""
Embedded-server CLI adapter for :mod:`hubvault.entry`.

This module keeps the ``hubvault serve`` command thin. It translates Click
arguments into :class:`hubvault.server.config.ServerConfig` and delegates all
runtime behavior to :mod:`hubvault.server`.

The module contains:

* :func:`register_server_commands` - Register the ``serve`` command
"""

import click

from ..errors import HubVaultError
from ..optional import MissingOptionalDependencyError
from ..server.config import DEFAULT_SERVER_PORT
from .base import ClickErrorException, command_wrap


def register_server_commands(group: click.Group) -> click.Group:
    """
    Register the ``serve`` command on one CLI group.

    :param group: Click group receiving the registered command
    :type group: click.Group
    :return: The same Click group for decorator chaining
    :rtype: click.Group

    Example::

        >>> import click
        >>> group = click.Group()
        >>> register_server_commands(group) is group
        True
    """

    @group.command("serve")
    @click.argument("path", type=click.Path(file_okay=False, dir_okay=True))
    @click.option("--host", default="127.0.0.1", show_default=True, help="Host interface to bind.")
    @click.option("--port", default=DEFAULT_SERVER_PORT, type=int, show_default=True, help="TCP port to bind.")
    @click.option(
        "--mode",
        type=click.Choice(["api", "frontend"]),
        default="frontend",
        show_default=True,
        help="Serve only the API or the API plus the built-in frontend.",
    )
    @click.option("--token-ro", "token_ro", multiple=True, help="Read-only API token. May be repeated.")
    @click.option("--token-rw", "token_rw", multiple=True, help="Read-write API token. May be repeated.")
    @click.option("--open-browser", is_flag=True, help="Open the frontend URL in a browser after start.")
    @click.option("--init", "init_repo", is_flag=True, help="Initialize the repository if it does not exist yet.")
    @click.option("--initial-branch", default="main", show_default=True, help="Initial branch used with --init.")
    @click.option(
        "--large-file-threshold",
        type=int,
        default=None,
        help="Large-file threshold used when initializing a repository.",
    )
    @command_wrap()
    def _serve(path, host, port, mode, token_ro, token_rw, open_browser, init_repo, initial_branch, large_file_threshold):
        """
        Execute the ``hubvault serve`` command.

        :param path: Repository root path
        :type path: str
        :param host: Host interface to bind
        :type host: str
        :param port: TCP port to bind
        :type port: int
        :param mode: Server mode name
        :type mode: str
        :param token_ro: Read-only token values
        :type token_ro: Sequence[str]
        :param token_rw: Read-write token values
        :type token_rw: Sequence[str]
        :param open_browser: Whether to open the browser after startup
        :type open_browser: bool
        :param init_repo: Whether to create the repository automatically
        :type init_repo: bool
        :param initial_branch: Initial branch used with ``--init``
        :type initial_branch: str
        :param large_file_threshold: Optional repository initialization
            threshold
        :type large_file_threshold: Optional[int]
        :return: ``None``.
        :rtype: None
        """

        from ..server import ServerConfig, launch

        try:
            config = ServerConfig(
                repo_path=path,
                host=host,
                port=port,
                mode=mode,
                token_ro=token_ro,
                token_rw=token_rw,
                open_browser=open_browser,
                init=init_repo,
                initial_branch=initial_branch,
                large_file_threshold=large_file_threshold,
            )
            launch(config)
        except (HubVaultError, MissingOptionalDependencyError, ValueError) as err:
            raise ClickErrorException(str(err))

    return group
