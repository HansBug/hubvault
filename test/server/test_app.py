import pytest

from hubvault.server import ServerConfig, create_app
from hubvault.server.asgi import create_app as create_asgi_app
from test.support import get_fastapi_test_client, rw_headers


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

        asset_response = client.get("/__init__.py")
        fallback_response = client.get("/missing/path")
        api_namespace_response = client.get("/api/not-found")

        assert asset_response.status_code == 200
        assert "placeholder" not in asset_response.text.lower()
        assert fallback_response.status_code == 200
        assert "hubvault web ui placeholder" in fallback_response.text.lower()
        assert api_namespace_response.status_code == 404
        assert api_namespace_response.json()["error"]["type"] == "HTTPException"
