import pytest

from hubvault.remote.errors import (
    HubVaultRemoteAuthError,
    HubVaultRemoteError,
    HubVaultRemoteProtocolError,
    HubVaultRemoteTransportError,
)


@pytest.mark.unittest
class TestRemoteErrors:
    def test_remote_error_hierarchy_is_stable(self):
        assert issubclass(HubVaultRemoteTransportError, HubVaultRemoteError)
        assert issubclass(HubVaultRemoteProtocolError, HubVaultRemoteError)
        assert issubclass(HubVaultRemoteAuthError, HubVaultRemoteError)

    def test_remote_error_instances_preserve_messages(self):
        assert str(HubVaultRemoteTransportError("transport")) == "transport"
        assert str(HubVaultRemoteProtocolError("protocol")) == "protocol"
        assert str(HubVaultRemoteAuthError("auth")) == "auth"
