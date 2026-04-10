"""
Token parsing and authorization helpers for :mod:`hubvault.server`.

This module keeps bearer-token parsing and access-level checks independent from
the FastAPI app factory so the authorization policy can be tested without API
extras installed.

The module contains:

* :class:`AuthContext` - Resolved token identity for one request
* :class:`TokenAuthorizer` - Read/write token resolver
* :func:`parse_request_token` - Header parser for supported token inputs
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AuthContext:
    """
    Resolved token identity for one request.

    :param access: Access level string, currently ``"ro"`` or ``"rw"``
    :type access: str
    :param token: Original bearer token text
    :type token: str
    """

    access: str
    token: str

    @property
    def can_write(self) -> bool:
        """
        Whether the token grants write access.

        :return: ``True`` when the token carries read-write permissions
        :rtype: bool
        """

        return self.access == "rw"


def parse_request_token(
    authorization: Optional[str] = None,
    x_hubvault_token: Optional[str] = None,
) -> Optional[str]:
    """
    Extract a token from supported request headers.

    ``X-HubVault-Token`` takes precedence over ``Authorization`` so simple
    internal callers can bypass bearer-header formatting.

    :param authorization: Raw ``Authorization`` header value
    :type authorization: Optional[str]
    :param x_hubvault_token: Raw ``X-HubVault-Token`` header value
    :type x_hubvault_token: Optional[str]
    :return: Normalized token string or ``None`` when no supported token is
        present
    :rtype: Optional[str]
    """

    if x_hubvault_token:
        token = x_hubvault_token.strip()
        return token or None
    if not authorization:
        return None

    scheme, _, value = authorization.partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    token = value.strip()
    return token or None


class TokenAuthorizer:
    """
    Resolve read-only and read-write API tokens.

    :param token_ro: Read-only token values
    :type token_ro: Iterable[str]
    :param token_rw: Read-write token values
    :type token_rw: Iterable[str]
    """

    def __init__(self, token_ro, token_rw) -> None:
        """
        Build one token authorizer from normalized token collections.

        :param token_ro: Read-only token values
        :type token_ro: Iterable[str]
        :param token_rw: Read-write token values
        :type token_rw: Iterable[str]
        :return: ``None``.
        :rtype: None
        """

        self._token_ro = frozenset(token_ro)
        self._token_rw = frozenset(token_rw)

    def resolve(self, token: Optional[str]) -> AuthContext:
        """
        Resolve one raw token into an :class:`AuthContext`.

        :param token: Raw token string extracted from the request
        :type token: Optional[str]
        :return: Resolved authorization context
        :rtype: AuthContext
        :raises PermissionError: Raised when the token is missing or invalid.
        """

        if not token:
            raise PermissionError("Missing authentication token.")
        if token in self._token_rw:
            return AuthContext(access="rw", token=token)
        if token in self._token_ro:
            return AuthContext(access="ro", token=token)
        raise PermissionError("Invalid authentication token.")

    def require_write(self, context: AuthContext) -> AuthContext:
        """
        Ensure the current token grants write access.

        :param context: Previously resolved authorization context
        :type context: AuthContext
        :return: The same authorization context when write access is allowed
        :rtype: AuthContext
        :raises PermissionError: Raised when the token is read-only.
        """

        if not context.can_write:
            raise PermissionError("Write access is required for this operation.")
        return context


def build_read_auth_dependency(authorizer: TokenAuthorizer):
    """
    Create a FastAPI dependency that enforces read access.

    :param authorizer: Token authorizer shared by the server app
    :type authorizer: TokenAuthorizer
    :return: FastAPI dependency callable that returns :class:`AuthContext`
    :rtype: Callable[..., Awaitable[AuthContext]]
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    """

    from ..optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="server authentication dependencies",
        missing_names={"starlette", "pydantic"},
    )
    Header = fastapi.Header
    HTTPException = fastapi.HTTPException
    status = fastapi.status

    async def _dependency(
        authorization: Optional[str] = Header(default=None),
        x_hubvault_token: Optional[str] = Header(default=None, alias="X-HubVault-Token"),
    ) -> AuthContext:
        """
        Resolve read access for one request.

        :param authorization: Raw bearer authorization header
        :type authorization: Optional[str]
        :param x_hubvault_token: Raw direct token header
        :type x_hubvault_token: Optional[str]
        :return: Resolved authorization context
        :rtype: AuthContext
        :raises fastapi.HTTPException: Raised when the token is missing or
            invalid.
        """

        token = parse_request_token(authorization=authorization, x_hubvault_token=x_hubvault_token)
        try:
            return authorizer.resolve(token)
        except PermissionError as err:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err))

    return _dependency


def build_write_auth_dependency(authorizer: TokenAuthorizer):
    """
    Create a FastAPI dependency that enforces write access.

    :param authorizer: Token authorizer shared by the server app
    :type authorizer: TokenAuthorizer
    :return: FastAPI dependency callable that returns :class:`AuthContext`
    :rtype: Callable[..., Awaitable[AuthContext]]
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    """

    from ..optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="server authentication dependencies",
        missing_names={"starlette", "pydantic"},
    )
    Header = fastapi.Header
    HTTPException = fastapi.HTTPException
    status = fastapi.status

    async def _dependency(
        authorization: Optional[str] = Header(default=None),
        x_hubvault_token: Optional[str] = Header(default=None, alias="X-HubVault-Token"),
    ) -> AuthContext:
        """
        Resolve write access for one request.

        :param authorization: Raw bearer authorization header
        :type authorization: Optional[str]
        :param x_hubvault_token: Raw direct token header
        :type x_hubvault_token: Optional[str]
        :return: Resolved authorization context with write access
        :rtype: AuthContext
        :raises fastapi.HTTPException: Raised when authentication fails or the
            token is read-only.
        """

        token = parse_request_token(authorization=authorization, x_hubvault_token=x_hubvault_token)
        try:
            context = authorizer.resolve(token)
            return authorizer.require_write(context)
        except PermissionError as err:
            detail = str(err)
            status_code = status.HTTP_401_UNAUTHORIZED if "token" in detail.lower() else status.HTTP_403_FORBIDDEN
            raise HTTPException(status_code=status_code, detail=detail)

    return _dependency
