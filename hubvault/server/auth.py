"""Token parsing and authorization helpers for the server layer."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AuthContext:
    """Resolved token identity for one request."""

    access: str
    token: str

    @property
    def can_write(self) -> bool:
        """Whether the token grants write access."""

        return self.access == "rw"


def parse_request_token(
    authorization: Optional[str] = None,
    x_hubvault_token: Optional[str] = None,
) -> Optional[str]:
    """Extract a token from supported request headers."""

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
    """Resolve read-only and read-write API tokens."""

    def __init__(self, token_ro, token_rw) -> None:
        self._token_ro = frozenset(token_ro)
        self._token_rw = frozenset(token_rw)

    def resolve(self, token: Optional[str]) -> AuthContext:
        """Resolve one raw token into an :class:`AuthContext`."""

        if not token:
            raise PermissionError("Missing authentication token.")
        if token in self._token_rw:
            return AuthContext(access="rw", token=token)
        if token in self._token_ro:
            return AuthContext(access="ro", token=token)
        raise PermissionError("Invalid authentication token.")

    def require_write(self, context: AuthContext) -> AuthContext:
        """Ensure the current token grants write access."""

        if not context.can_write:
            raise PermissionError("Write access is required for this operation.")
        return context


def build_read_auth_dependency(authorizer: TokenAuthorizer):
    """Create a FastAPI dependency that enforces read access."""

    from .._optional import import_optional_dependency

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
        token = parse_request_token(authorization=authorization, x_hubvault_token=x_hubvault_token)
        try:
            return authorizer.resolve(token)
        except PermissionError as err:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err))

    return _dependency


def build_write_auth_dependency(authorizer: TokenAuthorizer):
    """Create a FastAPI dependency that enforces write access."""

    from .._optional import import_optional_dependency

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
        token = parse_request_token(authorization=authorization, x_hubvault_token=x_hubvault_token)
        try:
            context = authorizer.resolve(token)
            return authorizer.require_write(context)
        except PermissionError as err:
            detail = str(err)
            status_code = status.HTTP_401_UNAUTHORIZED if "token" in detail.lower() else status.HTTP_403_FORBIDDEN
            raise HTTPException(status_code=status_code, detail=detail)

    return _dependency
