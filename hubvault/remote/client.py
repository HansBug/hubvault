"""
HTTP transport helpers for :mod:`hubvault.remote`.

This module delays ``httpx`` imports until the remote client is actually used,
so the base ``hubvault`` installation can still import the remote surface
without the remote extra installed.

The module contains:

* :func:`build_http_client` - Construct the underlying ``httpx`` client lazily
"""

from typing import Any

from ..optional import import_optional_dependency


def build_http_client(**kwargs: Any):
    """
    Build the underlying HTTP client lazily when remote extras are installed.

    :param kwargs: Keyword arguments forwarded to :class:`httpx.Client`
    :type kwargs: Any
    :return: Configured synchronous HTTP client
    :rtype: httpx.Client
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        remote extra is not installed.
    """

    httpx = import_optional_dependency(
        "httpx",
        extra="remote",
        feature="hubvault remote HTTP transport",
        missing_names={"httpx", "httpcore", "anyio"},
    )
    return httpx.Client(**kwargs)
