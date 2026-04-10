"""Shared dependency helpers for FastAPI route modules."""

from .auth import TokenAuthorizer


def get_token_authorizer(config) -> TokenAuthorizer:
    """Build the shared token authorizer for one server app."""

    return TokenAuthorizer(token_ro=config.token_ro, token_rw=config.token_rw)
