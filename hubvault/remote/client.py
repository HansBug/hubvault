"""
HTTP transport helpers for :mod:`hubvault.remote`.

This module delays ``httpx`` imports until the remote client is actually used,
so the base ``hubvault`` installation can still import the remote surface
without the remote extra installed.

The module contains:

* :func:`build_http_client` - Construct the underlying ``httpx`` client lazily
* :func:`request_json` - Execute one JSON request with error mapping
* :func:`request_bytes` - Execute one binary request with error mapping
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
    kwargs.setdefault("follow_redirects", True)
    return httpx.Client(**kwargs)


def _send_request(client, method: str, url: str, **kwargs: Any):
    """
    Send one HTTP request through the remote transport.

    :param client: Active HTTP client
    :type client: object
    :param method: HTTP method name
    :type method: str
    :param url: Relative or absolute request URL
    :type url: str
    :param kwargs: Additional request keyword arguments
    :type kwargs: Any
    :return: Transport response object
    :rtype: object
    :raises hubvault.remote.errors.HubVaultRemoteTransportError: Raised when the
        underlying HTTP request fails.
    """

    from .errors import HubVaultRemoteTransportError

    httpx = import_optional_dependency(
        "httpx",
        extra="remote",
        feature="hubvault remote HTTP transport",
        missing_names={"httpx", "httpcore", "anyio"},
    )

    try:
        return client.request(method, url, **kwargs)
    except httpx.HTTPError as err:
        raise HubVaultRemoteTransportError("Remote request failed: %s" % (err,))


def request_json(client, method: str, url: str, **kwargs: Any):
    """
    Execute one JSON request and decode the payload.

    :param client: Active HTTP client
    :type client: object
    :param method: HTTP method name
    :type method: str
    :param url: Relative or absolute request URL
    :type url: str
    :param kwargs: Additional request keyword arguments
    :type kwargs: Any
    :return: Decoded JSON payload
    :rtype: object
    :raises hubvault.errors.HubVaultError: Raised when the server returns a
        structured application error.
    :raises hubvault.remote.errors.HubVaultRemoteError: Raised when transport or
        response parsing fails.
    """

    from .errors import HubVaultRemoteProtocolError
    from .serde import decode_error_response, decode_json_payload

    response = _send_request(client, method, url, **kwargs)
    try:
        payload = response.json()
    except ValueError as err:
        if int(response.status_code) >= 400:
            raise HubVaultRemoteProtocolError(
                "Remote request failed with status %d and a non-JSON error payload." % (response.status_code,)
            )
        raise HubVaultRemoteProtocolError("Remote response was not valid JSON: %s" % (err,))

    if int(response.status_code) >= 400:
        raise decode_error_response(payload, status_code=int(response.status_code))
    return decode_json_payload(payload)


def request_bytes(client, method: str, url: str, **kwargs: Any) -> bytes:
    """
    Execute one binary request and return the response content.

    :param client: Active HTTP client
    :type client: object
    :param method: HTTP method name
    :type method: str
    :param url: Relative or absolute request URL
    :type url: str
    :param kwargs: Additional request keyword arguments
    :type kwargs: Any
    :return: Response content bytes
    :rtype: bytes
    :raises hubvault.errors.HubVaultError: Raised when the server returns a
        structured application error.
    :raises hubvault.remote.errors.HubVaultRemoteError: Raised when transport or
        response parsing fails.
    """

    from .errors import HubVaultRemoteProtocolError
    from .serde import decode_error_response

    response = _send_request(client, method, url, **kwargs)
    if int(response.status_code) >= 400:
        try:
            payload = response.json()
        except ValueError:
            raise HubVaultRemoteProtocolError(
                "Remote request failed with status %d and a non-JSON error payload." % (response.status_code,)
            )
        raise decode_error_response(payload, status_code=int(response.status_code))
    return bytes(response.content)
