"""Public remote API skeleton."""

from .client import build_http_client


class HubVaultRemoteApi:
    """Remote API placeholder aligned with future server routes."""

    def __init__(self, endpoint: str, token: str = None, timeout: float = 30.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout

    def build_client(self):
        """Build the underlying HTTP client lazily."""

        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer %s" % (self.token,)
        return build_http_client(base_url=self.endpoint, timeout=self.timeout, headers=headers or None)


HubVaultRemoteAPI = HubVaultRemoteApi
