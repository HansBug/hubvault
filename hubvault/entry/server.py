"""CLI adapter for the embedded HTTP server."""

import click

from ..errors import HubVaultError
from .._optional import MissingOptionalDependencyError
from ..server.config import DEFAULT_SERVER_PORT
from .base import ClickErrorException, command_wrap


def register_server_commands(group: click.Group) -> click.Group:
    """Register the ``serve`` command on one CLI group."""

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
