"""
Public remote API surface for :mod:`hubvault.remote`.

This module defines the early public client shell that will eventually mirror
selected local :class:`hubvault.api.HubVaultApi` read APIs over HTTP.

The module contains:

* :class:`HubVaultRemoteApi` - Remote API entry point
* :data:`HubVaultRemoteAPI` - Compatibility alias for the preferred class name
"""

from typing import Optional

from .client import build_http_client


class HubVaultRemoteApi:
    """
    Remote API placeholder aligned with future server routes.

    :param endpoint: Base URL of the remote server
    :type endpoint: str
    :param token: Optional bearer token used for authenticated requests
    :type token: Optional[str]
    :param timeout: Default request timeout in seconds
    :type timeout: float

    Example::

        >>> api = HubVaultRemoteApi("https://example.com/api", token="secret")
        >>> api.endpoint
        'https://example.com/api'
    """

    def __init__(self, endpoint: str, token: Optional[str] = None, timeout: float = 30.0) -> None:
        """
        Build one remote API client shell.

        :param endpoint: Base URL of the remote server
        :type endpoint: str
        :param token: Optional bearer token used for authenticated requests
        :type token: Optional[str]
        :param timeout: Default request timeout in seconds
        :type timeout: float
        :return: ``None``.
        :rtype: None
        """

        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout

    def build_client(self):
        """
        Build the underlying HTTP client lazily.

        :return: Configured HTTP transport client
        :rtype: httpx.Client
        :raises hubvault.optional.MissingOptionalDependencyError: Raised when
            the remote extra is not installed.
        """

        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer %s" % (self.token,)
        return build_http_client(base_url=self.endpoint, timeout=self.timeout, headers=headers or None)


HubVaultRemoteAPI = HubVaultRemoteApi
