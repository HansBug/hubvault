import re

import pytest

from hubvault.server import ServerConfig, create_app
from test.support import get_fastapi_test_client


def _first_asset_paths(html):
    return re.findall(r'(?:src|href)="(?P<path>/assets/[^"]+)"', html)


@pytest.mark.unittest
class TestServerUi:
    def test_frontend_mode_serves_real_built_assets_and_spa_fallback(self, tmp_path):
        TestClient = get_fastapi_test_client()
        repo_dir = tmp_path / "repo"
        client = TestClient(
            create_app(
                ServerConfig(
                    repo_path=repo_dir,
                    mode="frontend",
                    token_rw=("rw-token",),
                    init=True,
                )
            )
        )

        index_response = client.get("/")
        nested_response = client.get("/repo/files?revision=main")
        asset_paths = _first_asset_paths(index_response.text)
        js_asset_path = next(
            path for path in asset_paths if path.endswith(".js") and "/assets/index-" in path and "legacy" not in path
        )
        js_asset_response = client.get(js_asset_path)

        assert index_response.status_code == 200
        assert nested_response.status_code == 200
        assert index_response.text == nested_response.text
        assert len(asset_paths) >= 3
        assert "vite-legacy-entry" in index_response.text
        assert js_asset_response.status_code == 200
        assert "/api/v1/" in js_asset_response.text
