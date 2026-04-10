"""HTTP transport skeleton for the remote client."""

from .._optional import import_optional_dependency


def build_http_client(**kwargs):
    """Build the underlying HTTP client lazily when remote extras are installed."""

    httpx = import_optional_dependency(
        "httpx",
        extra="remote",
        feature="hubvault remote HTTP transport",
        missing_names={"httpx", "httpcore", "anyio"},
    )
    return httpx.Client(**kwargs)
