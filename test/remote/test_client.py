import pytest

from hubvault.remote.client import build_http_client, request_bytes, request_json
from hubvault.remote.errors import HubVaultRemoteProtocolError, HubVaultRemoteTransportError


@pytest.mark.unittest
class TestRemoteClient:
    def test_build_http_client_enables_follow_redirects_by_default(self):
        pytest.importorskip("httpx")

        client = build_http_client(base_url="https://example.com")
        try:
            assert client.follow_redirects is True
        finally:
            client.close()

    def test_request_json_maps_transport_and_invalid_json_errors(self):
        httpx = pytest.importorskip("httpx")

        def _transport_error_handler(request):
            raise httpx.ConnectError("offline", request=request)

        def _json_error_handler(request):
            if request.url.path == "/success-text":
                return httpx.Response(200, content=b"plain-text")
            return httpx.Response(400, content=b"plain-error")

        transport_error_client = httpx.Client(
            transport=httpx.MockTransport(_transport_error_handler),
            base_url="https://example.com",
        )
        invalid_json_client = httpx.Client(
            transport=httpx.MockTransport(_json_error_handler),
            base_url="https://example.com",
        )
        try:
            with pytest.raises(HubVaultRemoteTransportError, match="offline"):
                request_json(transport_error_client, "GET", "/boom")

            with pytest.raises(HubVaultRemoteProtocolError, match="Remote response was not valid JSON"):
                request_json(invalid_json_client, "GET", "/success-text")

            with pytest.raises(HubVaultRemoteProtocolError, match="non-JSON error payload"):
                request_json(invalid_json_client, "GET", "/error-text")
        finally:
            transport_error_client.close()
            invalid_json_client.close()

    def test_request_bytes_rejects_non_json_error_payloads(self):
        httpx = pytest.importorskip("httpx")

        def _handler(_request):
            return httpx.Response(500, content=b"plain-error")

        client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://example.com",
        )
        try:
            with pytest.raises(HubVaultRemoteProtocolError, match="non-JSON error payload"):
                request_bytes(client, "GET", "/error")
        finally:
            client.close()

