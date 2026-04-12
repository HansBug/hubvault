import asyncio
import re

import pytest

from hubvault.server import ServerConfig, create_app
from hubvault.server.asgi import create_app as create_asgi_app
from test.support import get_fastapi_test_client, ro_headers, rw_headers, seed_phase45_repo


def _first_asset_path(html):
    match = re.search(r'(?:src|href)="(?P<path>/assets/[^"]+)"', html)
    assert match is not None
    return match.group("path")


@pytest.mark.unittest
class TestServerApp:
    def test_create_app_rejects_mixed_config_and_kwargs(self, tmp_path):
        pytest.importorskip("fastapi")
        config = ServerConfig(repo_path=tmp_path / "repo", token_rw=("rw-token",))

        with pytest.raises(TypeError, match="Pass either a ServerConfig instance"):
            create_app(config=config, repo_path=tmp_path / "other-repo")

    def test_create_app_can_initialize_repo_from_kwargs(self, tmp_path):
        TestClient = get_fastapi_test_client()
        repo_dir = tmp_path / "repo"

        client = TestClient(
            create_app(
                repo_path=repo_dir,
                mode="api",
                token_rw=("rw-token",),
                init=True,
                initial_branch="dev",
                large_file_threshold=1024,
            )
        )
        service_response = client.get("/api/v1/meta/service", headers=rw_headers())

        assert service_response.status_code == 200
        assert service_response.json()["repo"]["default_branch"] == "dev"
        assert repo_dir.exists()

    def test_asgi_create_app_can_build_from_environment(self, monkeypatch, tmp_path):
        TestClient = get_fastapi_test_client()
        repo_dir = tmp_path / "repo"

        monkeypatch.setenv("HUBVAULT_REPO_PATH", str(repo_dir))
        monkeypatch.setenv("HUBVAULT_SERVE_MODE", "api")
        monkeypatch.setenv("HUBVAULT_TOKEN_RW", "rw-token")
        monkeypatch.setenv("HUBVAULT_INIT", "1")
        monkeypatch.setenv("HUBVAULT_INITIAL_BRANCH", "env-branch")

        client = TestClient(create_asgi_app())
        service_response = client.get("/api/v1/meta/service", headers=rw_headers())

        assert service_response.status_code == 200
        assert service_response.json()["repo"]["default_branch"] == "env-branch"

    def test_frontend_fallback_serves_assets_and_rejects_api_namespace(self, tmp_path):
        TestClient = get_fastapi_test_client()
        repo_dir = tmp_path / "repo"

        client = TestClient(
            create_app(
                repo_path=repo_dir,
                mode="frontend",
                token_rw=("rw-token",),
                init=True,
            )
        )

        fallback_response = client.get("/missing/path")
        api_namespace_response = client.get("/api/not-found")
        asset_path = _first_asset_path(fallback_response.text)
        asset_response = client.get(asset_path)

        assert asset_response.status_code == 200
        assert asset_response.text
        assert fallback_response.status_code == 200
        assert "/assets/index-" in fallback_response.text
        assert "vite-legacy-entry" in fallback_response.text
        assert api_namespace_response.status_code == 404
        assert api_namespace_response.json()["error"]["type"] == "HTTPException"

    def test_app_handles_parallel_read_requests(self, tmp_path):
        httpx = pytest.importorskip("httpx")
        repo_dir = tmp_path / "repo"
        seed_phase45_repo(repo_dir)

        app = create_app(
            ServerConfig(
                repo_path=repo_dir,
                mode="api",
                token_ro=("ro-token",),
                token_rw=("rw-token",),
            )
        )

        async def _exercise_requests():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers=ro_headers(),
            ) as client:
                async def _one_round():
                    service_response, refs_response, whoami_response = await asyncio.gather(
                        client.get("/api/v1/meta/service"),
                        client.get("/api/v1/refs"),
                        client.get("/api/v1/meta/whoami"),
                    )
                    assert service_response.status_code == 200
                    assert refs_response.status_code == 200
                    assert whoami_response.status_code == 200
                    assert service_response.json()["repo"]["default_branch"] == "release/v1"
                    assert whoami_response.json()["access"] == "ro"

                await asyncio.gather(*[_one_round() for _ in range(24)])

        asyncio.run(_exercise_requests())
