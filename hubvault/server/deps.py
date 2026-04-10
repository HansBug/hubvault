"""
Shared dependency helpers for :mod:`hubvault.server`.

This module centralizes lightweight dependency-construction helpers that are
shared by route factories.
"""

from .auth import TokenAuthorizer


def get_token_authorizer(config) -> TokenAuthorizer:
    """
    Build the shared token authorizer for one server app.

    :param config: Server configuration carrying normalized token lists
    :type config: hubvault.server.config.ServerConfig
    :return: Token authorizer bound to the config tokens
    :rtype: TokenAuthorizer
    """

    return TokenAuthorizer(token_ro=config.token_ro, token_rw=config.token_rw)
