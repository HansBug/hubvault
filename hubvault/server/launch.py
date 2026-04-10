"""Quick-start launcher for the embedded server."""

import argparse
import sys
import webbrowser
from typing import Optional, Sequence

from ..errors import HubVaultError
from .._optional import MissingOptionalDependencyError, import_optional_dependency
from .app import create_app
from .config import DEFAULT_SERVER_PORT, SERVER_MODE_API, SERVER_MODE_FRONTEND, ServerConfig


def launch(config: Optional[ServerConfig] = None, **kwargs):
    """Create and run the embedded ASGI server."""

    uvicorn = import_optional_dependency(
        "uvicorn",
        extra="api",
        feature="hubvault server quick-start launcher",
        missing_names={"click", "h11", "httptools"},
    )
    config = config or (ServerConfig(**kwargs) if kwargs else ServerConfig.from_env())
    app = create_app(config=config)
    if config.open_browser:
        webbrowser.open(config.browser_url)
    uvicorn.run(app, host=config.host, port=config.port)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for ``python -m hubvault.server``."""

    parser = argparse.ArgumentParser(description="Run the embedded hubvault HTTP server.")
    parser.add_argument("repo_path", help="Path to the repository root.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT, help="TCP port to bind.")
    parser.add_argument(
        "--mode",
        choices=[SERVER_MODE_API, SERVER_MODE_FRONTEND],
        default=SERVER_MODE_FRONTEND,
        help="Serve only the API or the API plus static frontend.",
    )
    parser.add_argument("--token-ro", action="append", default=[], help="Read-only API token. May be repeated.")
    parser.add_argument("--token-rw", action="append", default=[], help="Read-write API token. May be repeated.")
    parser.add_argument("--open-browser", action="store_true", help="Open the frontend URL in a browser after start.")
    parser.add_argument("--init", action="store_true", help="Initialize the repository if it does not exist yet.")
    parser.add_argument("--initial-branch", default="main", help="Initial branch name used with --init.")
    parser.add_argument(
        "--large-file-threshold",
        type=int,
        default=None,
        help="Large file threshold used when initializing a repository.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the module-level quick-start entry point."""

    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        launch(
            repo_path=args.repo_path,
            host=args.host,
            port=args.port,
            mode=args.mode,
            token_ro=args.token_ro,
            token_rw=args.token_rw,
            open_browser=args.open_browser,
            init=args.init,
            initial_branch=args.initial_branch,
            large_file_threshold=args.large_file_threshold,
        )
    except (HubVaultError, MissingOptionalDependencyError, ValueError) as err:
        print(str(err), file=sys.stderr)
        return 2
    return 0
