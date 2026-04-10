import pytest

from hubvault.server.auth import TokenAuthorizer, parse_request_token


@pytest.mark.unittest
class TestServerAuth:
    def test_parse_request_token_prefers_explicit_header(self):
        token = parse_request_token(
            authorization="Bearer ignored",
            x_hubvault_token="direct-token",
        )

        assert token == "direct-token"

    def test_parse_request_token_accepts_bearer_authorization(self):
        assert parse_request_token(authorization="Bearer abc123") == "abc123"
        assert parse_request_token(authorization="Basic abc123") is None
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
