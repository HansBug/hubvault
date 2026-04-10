import pytest

from hubvault.optional import MissingOptionalDependencyError
from hubvault.remote import HubVaultRemoteAPI, HubVaultRemoteApi


@pytest.mark.unittest
class TestRemoteApi:
    def test_aliases_and_lazy_client_construction_are_available(self):
        api = HubVaultRemoteApi("https://example.com", token="secret")

        assert HubVaultRemoteAPI is HubVaultRemoteApi
        assert api.endpoint == "https://example.com"
        assert api.token == "secret"

    def test_missing_remote_extra_is_deferred_to_build_client(self, monkeypatch):
        api = HubVaultRemoteApi("https://example.com", token="secret")

        def _raise_missing(*args, **kwargs):
            raise MissingOptionalDependencyError(extra="remote", feature="test remote client", missing_name="httpx")

        monkeypatch.setattr("hubvault.remote.client.import_optional_dependency", _raise_missing)

        with pytest.raises(MissingOptionalDependencyError, match="hubvault\\[remote\\]"):
            api.build_client()
