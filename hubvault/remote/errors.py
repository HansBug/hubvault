"""
Error types for :mod:`hubvault.remote`.

The remote client keeps its own exception hierarchy so callers do not need to
depend on the concrete HTTP transport implementation.
"""


class HubVaultRemoteError(Exception):
    """
    Base error for remote-client failures.

    Remote operations should surface this hierarchy instead of raw transport
    exceptions once the higher-level client is implemented.
    """


class HubVaultRemoteTransportError(HubVaultRemoteError):
    """Raised when the remote transport cannot complete a request."""
