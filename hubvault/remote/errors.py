"""Error types for the future remote client layer."""


class HubVaultRemoteError(Exception):
    """Base error for remote-client failures."""


class HubVaultRemoteTransportError(HubVaultRemoteError):
    """Raised when the remote transport cannot complete a request."""
