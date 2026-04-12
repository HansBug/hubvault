"""
Server configuration helpers for :mod:`hubvault.server`.

This module normalizes all startup surfaces onto the same immutable
configuration object so CLI startup, import startup, and ASGI startup behave
consistently.

The module contains:

* :class:`ServerConfig` - Normalized embedded-server configuration
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple


SERVER_MODE_API = "api"
SERVER_MODE_FRONTEND = "frontend"
DEFAULT_SERVER_PORT = 9472
_VALID_SERVER_MODES = {SERVER_MODE_API, SERVER_MODE_FRONTEND}
_TOKEN_SPLIT_PATTERN = re.compile(r"[\s,%s]+" % re.escape(os.pathsep))


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    """
    Parse one environment-style boolean string.

    :param value: Raw environment value
    :type value: Optional[str]
    :param default: Fallback used when ``value`` is missing
    :type default: bool
    :return: Parsed boolean value
    :rtype: bool
    """

    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: Optional[str]) -> Optional[int]:
    """
    Parse one optional integer environment value.

    :param value: Raw environment value
    :type value: Optional[str]
    :return: Parsed integer or ``None`` when the input is empty
    :rtype: Optional[int]
    """

    if value is None or value == "":
        return None
    return int(value)


def _normalize_tokens(values: Iterable[str]) -> Tuple[str, ...]:
    """
    Deduplicate token inputs while preserving first-seen order.

    :param values: Raw token values
    :type values: Iterable[str]
    :return: Normalized token tuple without blanks or duplicates
    :rtype: Tuple[str, ...]
    """

    seen = set()
    items = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return tuple(items)


def _parse_token_env(value: Optional[str]) -> Tuple[str, ...]:
    """
    Parse token values from one environment variable.

    :param value: Raw token environment string
    :type value: Optional[str]
    :return: Normalized token tuple
    :rtype: Tuple[str, ...]
    """

    if not value:
        return ()
    return _normalize_tokens(item for item in _TOKEN_SPLIT_PATTERN.split(value) if item)


@dataclass(frozen=True)
class ServerConfig:
    """
    Normalized runtime configuration for the embedded server.

    :param repo_path: Repository root served by the app
    :type repo_path: pathlib.Path
    :param mode: Server mode, either ``"api"`` or ``"frontend"``
    :type mode: str
    :param host: Host interface to bind
    :type host: str
    :param port: TCP port to bind
    :type port: int
    :param token_ro: Read-only bearer tokens
    :type token_ro: Tuple[str, ...]
    :param token_rw: Read-write bearer tokens
    :type token_rw: Tuple[str, ...]
    :param open_browser: Whether to open the local browser URL after startup
    :type open_browser: bool
    :param init: Whether to create the repository automatically when missing
    :type init: bool
    :param initial_branch: Initial branch name used with ``init``
    :type initial_branch: str
    :param large_file_threshold: Optional chunking threshold used during
        repository creation
    :type large_file_threshold: Optional[int]
    """

    repo_path: Path
    mode: str = SERVER_MODE_FRONTEND
    host: str = "127.0.0.1"
    port: int = DEFAULT_SERVER_PORT
    token_ro: Tuple[str, ...] = ()
    token_rw: Tuple[str, ...] = ()
    open_browser: bool = False
    init: bool = False
    initial_branch: str = "main"
    large_file_threshold: Optional[int] = None

    def __post_init__(self) -> None:
        """
        Validate and normalize the dataclass fields after construction.

        :return: ``None``.
        :rtype: None
        :raises ValueError: Raised when mode, port, token, or threshold values
            are invalid.
        """

        repo_path = Path(self.repo_path).expanduser()
        mode = str(self.mode).strip().lower()
        host = str(self.host).strip() or "127.0.0.1"
        port = int(self.port)
        token_rw = _normalize_tokens(self.token_rw)
        token_ro = tuple(item for item in _normalize_tokens(self.token_ro) if item not in token_rw)
        initial_branch = str(self.initial_branch).strip() or "main"
        large_file_threshold = self.large_file_threshold

        if mode not in _VALID_SERVER_MODES:
            raise ValueError("Unsupported server mode: %r." % (self.mode,))
        if port <= 0 or port > 65535:
            raise ValueError("Server port must be between 1 and 65535.")
        if not token_ro and not token_rw:
            raise ValueError("At least one --token-ro or --token-rw value is required.")
        if large_file_threshold is not None and int(large_file_threshold) <= 0:
            raise ValueError("Large file threshold must be a positive integer.")

        object.__setattr__(self, "repo_path", repo_path)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", port)
        object.__setattr__(self, "token_ro", token_ro)
        object.__setattr__(self, "token_rw", token_rw)
        object.__setattr__(self, "initial_branch", initial_branch)
        object.__setattr__(self, "large_file_threshold", None if large_file_threshold is None else int(large_file_threshold))

    @property
    def ui_enabled(self) -> bool:
        """
        Whether the frontend static UI should be served.

        :return: ``True`` when the frontend assets should be mounted
        :rtype: bool
        """

        return self.mode == SERVER_MODE_FRONTEND

    @property
    def browser_url(self) -> str:
        """
        Return the browser-friendly local URL for the bound server.

        :return: Browser URL using a loopback-safe host when bound to all
            interfaces
        :rtype: str
        """

        host = self.host
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1"
        return "http://{host}:{port}/".format(host=host, port=self.port)

    @classmethod
    def from_env(cls, **overrides) -> "ServerConfig":
        """
        Build a config object from ``HUBVAULT_*`` environment variables.

        :param overrides: Explicit field overrides applied on top of the
            environment
        :type overrides: dict
        :return: Normalized server configuration
        :rtype: ServerConfig
        :raises TypeError: Raised when unsupported override keys are provided.
        :raises ValueError: Raised when required values such as ``repo_path``
            are missing.
        """

        values = {
            "repo_path": overrides.pop("repo_path", None) or os.environ.get("HUBVAULT_REPO_PATH"),
            "mode": overrides.pop("mode", None) or os.environ.get("HUBVAULT_SERVE_MODE", SERVER_MODE_FRONTEND),
            "host": overrides.pop("host", None) or os.environ.get("HUBVAULT_HOST", "127.0.0.1"),
            "port": overrides.pop("port", None) or os.environ.get("HUBVAULT_PORT", DEFAULT_SERVER_PORT),
            "token_ro": overrides.pop("token_ro", None) or _parse_token_env(os.environ.get("HUBVAULT_TOKEN_RO")),
            "token_rw": overrides.pop("token_rw", None) or _parse_token_env(os.environ.get("HUBVAULT_TOKEN_RW")),
            "open_browser": overrides.pop("open_browser", None),
            "init": overrides.pop("init", None),
            "initial_branch": overrides.pop("initial_branch", None) or os.environ.get("HUBVAULT_INITIAL_BRANCH", "main"),
            "large_file_threshold": overrides.pop("large_file_threshold", None),
        }
        if overrides:
            raise TypeError("Unexpected config overrides: %s." % ", ".join(sorted(overrides)))

        if values["repo_path"] is None:
            raise ValueError("Server repo path must be provided explicitly or via HUBVAULT_REPO_PATH.")
        if values["open_browser"] is None:
            values["open_browser"] = _parse_bool(os.environ.get("HUBVAULT_OPEN_BROWSER"), default=False)
        if values["init"] is None:
            values["init"] = _parse_bool(os.environ.get("HUBVAULT_INIT"), default=False)
        if values["large_file_threshold"] is None:
            values["large_file_threshold"] = _parse_int(os.environ.get("HUBVAULT_LARGE_FILE_THRESHOLD"))

        return cls(**values)
