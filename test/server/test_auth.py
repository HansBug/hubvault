import pytest

from hubvault.server.auth import (
    TokenAuthorizer,
    build_read_auth_dependency,
    build_write_auth_dependency,
    parse_request_token,
)
from test.support import get_fastapi_test_client


@pytest.mark.unittest
class TestServerAuth:
    def test_parse_request_token_prefers_explicit_header(self):
        token = parse_request_token(
            authorization="Bearer ignored",
            x_hubvault_token="direct-token",
            query_token="query-token",
        )

        assert token == "direct-token"

    def test_parse_request_token_accepts_bearer_authorization_and_query_fallback(self):
        assert parse_request_token(authorization="Bearer abc123") == "abc123"
        assert parse_request_token(authorization="Basic abc123", query_token="query-token") == "query-token"
        assert parse_request_token(authorization=None, query_token="query-token") == "query-token"
        assert parse_request_token(authorization=None, query_token="   ") is None
        assert parse_request_token(authorization=None) is None

    def test_authorizer_distinguishes_read_and_write_tokens(self):
        authorizer = TokenAuthorizer(token_ro=("ro-token",), token_rw=("rw-token",))

        ro_context = authorizer.resolve("ro-token")
        rw_context = authorizer.resolve("rw-token")

        assert ro_context.access == "ro"
        assert ro_context.can_write is False
        assert rw_context.access == "rw"
        assert rw_context.can_write is True
        assert authorizer.require_write(rw_context) is rw_context

    def test_authorizer_rejects_missing_invalid_and_read_only_write_requests(self):
        authorizer = TokenAuthorizer(token_ro=("ro-token",), token_rw=("rw-token",))

        with pytest.raises(PermissionError, match="Missing authentication token"):
            authorizer.resolve(None)

        with pytest.raises(PermissionError, match="Invalid authentication token"):
            authorizer.resolve("bad-token")

        with pytest.raises(PermissionError, match="Write access is required"):
            authorizer.require_write(authorizer.resolve("ro-token"))

    def test_read_auth_dependency_accepts_query_token_for_browser_resource_urls(self):
        fastapi = pytest.importorskip("fastapi")
        TestClient = get_fastapi_test_client()
        authorizer = TokenAuthorizer(token_ro=("ro-token",), token_rw=("rw-token",))
        app = fastapi.FastAPI()
        require_read = build_read_auth_dependency(authorizer)

        @app.get("/read")
        async def _read_endpoint(auth=fastapi.Depends(require_read)):
            return {
                "access": auth.access,
                "token": auth.token,
                "can_write": auth.can_write,
            }

        client = TestClient(app)

        response = client.get("/read", params={"token": "ro-token"})
        assert response.status_code == 200
        assert response.json() == {
            "access": "ro",
            "token": "ro-token",
            "can_write": False,
        }
        assert client.get("/read", params={"token": "bad-token"}).status_code == 401

    def test_write_auth_dependency_enforces_rw_and_maps_status_codes(self):
        fastapi = pytest.importorskip("fastapi")
        TestClient = get_fastapi_test_client()
        authorizer = TokenAuthorizer(token_ro=("ro-token",), token_rw=("rw-token",))
        app = fastapi.FastAPI()
        require_write = build_write_auth_dependency(authorizer)

        @app.get("/write")
        async def _write_endpoint(auth=fastapi.Depends(require_write)):
            return {
                "access": auth.access,
                "token": auth.token,
                "can_write": auth.can_write,
            }

        client = TestClient(app)

        assert client.get("/write").status_code == 401
        assert client.get("/write", params={"token": "rw-token"}).status_code == 401
        assert client.get("/write", headers={"Authorization": "Bearer bad-token"}).status_code == 401
        assert client.get("/write", headers={"Authorization": "Bearer ro-token"}).status_code == 403

        response = client.get("/write", headers={"X-HubVault-Token": "rw-token"})
        assert response.status_code == 200
        assert response.json() == {
            "access": "rw",
            "token": "rw-token",
            "can_write": True,
        }
