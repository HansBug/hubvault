"""
Error types for :mod:`hubvault.remote`.

The remote client keeps its own exception hierarchy so callers do not need to
depend on the concrete HTTP transport implementation.
"""


class HubVaultRemoteError(Exception):
    """
    Base error for remote-client failures.

    Remote operations surface this hierarchy instead of leaking concrete HTTP
    client exceptions back to callers.

    Example::

        >>> str(HubVaultRemoteError("boom"))
        'boom'
    """


class HubVaultRemoteTransportError(HubVaultRemoteError):
    """
    Raised when the remote transport cannot complete a request.

    Example::

        >>> str(HubVaultRemoteTransportError("offline"))
        'offline'
    """


class HubVaultRemoteProtocolError(HubVaultRemoteError):
    """
    Raised when the remote server returns an invalid or unsupported payload.

    Example::

        >>> str(HubVaultRemoteProtocolError("bad json"))
        'bad json'
    """


class HubVaultRemoteAuthError(HubVaultRemoteError):
    """
    Raised when the remote server rejects authentication or permissions.

    Example::

        >>> str(HubVaultRemoteAuthError("forbidden"))
        'forbidden'
    """
