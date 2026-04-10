import runpy
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

from hubvault import HubVaultApi
from hubvault._optional import MissingOptionalDependencyError
from hubvault.server import ServerConfig, create_app, launch
from hubvault.server.config import DEFAULT_SERVER_PORT


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unittest
class TestServerLaunch:
    def test_public_imports_are_stable(self):
        assert ServerConfig is not None
        assert create_app is not None
        assert launch is not None

    def test_python_module_help_runs_without_starting_server(self):
        result = subprocess.run(
            [sys.executable, "-m", "hubvault.server", "--help"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "--token-rw" in result.stdout

    def test_runpy_server_main_help(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["hubvault.server", "--help"])

        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("hubvault.server.__main__", run_name="__main__")

        captured = capsys.readouterr()
        assert exc_info.value.code == 0
        assert "usage" in captured.out.lower()

    def test_missing_api_extra_is_deferred_to_create_app_call(self, monkeypatch, tmp_path):
        config = ServerConfig(repo_path=tmp_path / "repo", token_rw=("rw-token",))

        def _raise_missing(*args, **kwargs):
            raise MissingOptionalDependencyError(extra="api", feature="test app factory", missing_name="fastapi")

        monkeypatch.setattr("hubvault.server.app.import_optional_dependency", _raise_missing)

        with pytest.raises(MissingOptionalDependencyError, match="hubvault\\[api\\]"):
            create_app(config=config)

    def test_missing_uvicorn_extra_is_deferred_to_launch_call(self, monkeypatch, tmp_path):
        config = ServerConfig(repo_path=tmp_path / "repo", token_rw=("rw-token",))
        launch_module = import_module("hubvault.server.launch")

        def _raise_missing(*args, **kwargs):
            raise MissingOptionalDependencyError(extra="api", feature="test launcher", missing_name="uvicorn")

        monkeypatch.setattr(launch_module, "import_optional_dependency", _raise_missing)

        with pytest.raises(MissingOptionalDependencyError, match="hubvault\\[api\\]"):
            launch(config)

    def test_launch_delegates_to_uvicorn_and_optional_browser(self, monkeypatch, tmp_path):
        config = ServerConfig(repo_path=tmp_path / "repo", token_rw=("rw-token",), open_browser=True)
        launch_module = import_module("hubvault.server.launch")
        seen = {}

        class _FakeUvicorn(object):
            @staticmethod
            def run(app, host, port):
                seen["app"] = app
                seen["host"] = host
                seen["port"] = port

        monkeypatch.setattr(launch_module, "import_optional_dependency", lambda *args, **kwargs: _FakeUvicorn())
        monkeypatch.setattr(launch_module, "create_app", lambda config=None: "demo-app")
        monkeypatch.setattr(launch_module.webbrowser, "open", lambda url: seen.setdefault("browser_url", url))

        launch(config)

        assert seen["app"] == "demo-app"
        assert seen["host"] == "127.0.0.1"
        assert seen["port"] == DEFAULT_SERVER_PORT
        assert seen["browser_url"] == "http://127.0.0.1:%d/" % (DEFAULT_SERVER_PORT,)

    def test_create_app_serves_meta_routes_and_frontend_modes(self, tmp_path):
        fastapi = pytest.importorskip("fastapi")
        assert fastapi is not None
        testclient = pytest.importorskip("fastapi.testclient")
        TestClient = testclient.TestClient

        repo_dir = tmp_path / "repo"
        HubVaultApi(repo_dir).create_repo()

        api_app = create_app(ServerConfig(repo_path=repo_dir, mode="api", token_ro=("ro-token",), token_rw=("rw-token",)))
        api_client = TestClient(api_app)

        no_token_response = api_client.get("/api/v1/meta/service")
        bad_token_response = api_client.get("/api/v1/meta/service", headers={"Authorization": "Bearer bad"})
        ro_response = api_client.get("/api/v1/meta/service", headers={"Authorization": "Bearer ro-token"})
        whoami_response = api_client.get("/api/v1/meta/whoami", headers={"Authorization": "Bearer rw-token"})
        api_root_response = api_client.get("/")

        assert no_token_response.status_code == 401
        assert bad_token_response.status_code == 401
        assert ro_response.status_code == 200
        assert ro_response.json()["auth"]["access"] == "ro"
        assert ro_response.json()["ui_enabled"] is False
        assert whoami_response.status_code == 200
        assert whoami_response.json() == {"access": "rw", "can_write": True}
        assert api_root_response.status_code == 404

        frontend_app = create_app(
            ServerConfig(repo_path=repo_dir, mode="frontend", token_ro=("ro-token",), token_rw=("rw-token",))
        )
        frontend_client = TestClient(frontend_app)
        frontend_root_response = frontend_client.get("/")

        assert frontend_root_response.status_code == 200
        assert "hubvault web ui placeholder" in frontend_root_response.text.lower()
