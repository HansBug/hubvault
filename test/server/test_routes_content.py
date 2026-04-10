from urllib.parse import parse_qs, urlparse

import pytest

from test.support import create_phase45_app, get_fastapi_test_client, ro_headers, seed_phase45_repo


@pytest.mark.unittest
class TestServerContentRoutes:
    def test_ro_token_can_browse_paths_tree_files_and_downloads(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        paths_response = client.post(
            "/api/v1/content/paths-info",
            headers=ro_headers(),
            json=["artifacts", "artifacts/model.bin", "missing.txt"],
        )
        tree_response = client.get("/api/v1/content/tree", headers=ro_headers())
        files_response = client.get("/api/v1/content/files", headers=ro_headers())
        download_response = client.get("/api/v1/content/download/artifacts/model.bin", headers=ro_headers())

        assert paths_response.status_code == 200
        assert [item["path"] for item in paths_response.json()] == ["artifacts", "artifacts/model.bin"]
        assert [item["entry_type"] for item in paths_response.json()] == ["folder", "file"]

        assert tree_response.status_code == 200
        assert sorted(item["path"] for item in tree_response.json()) == [
            "README.md",
            "artifacts",
            "configs",
            "docs",
        ]

        assert files_response.status_code == 200
        assert sorted(files_response.json()) == sorted(seeded["api"].list_repo_files())

        assert download_response.status_code == 200
        assert download_response.content == seeded["model_bytes"]
        assert download_response.headers["X-HubVault-Repo-Path"] == "artifacts/model.bin"
        assert download_response.headers["ETag"] == seeded["api"].get_paths_info("artifacts/model.bin")[0].etag

    def test_range_route_matches_local_api_and_surfaces_validation_errors(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        response = client.get(
            "/api/v1/content/blob/artifacts/model.bin/range",
            headers=ro_headers(),
            params={"start": 3, "length": 7},
        )
        bad_response = client.get(
            "/api/v1/content/blob/artifacts/model.bin/range",
            headers=ro_headers(),
            params={"start": -1, "length": 1},
        )

        assert response.status_code == 200
        assert response.content == seeded["api"].read_range("artifacts/model.bin", start=3, length=7)

        assert bad_response.status_code == 400
        assert bad_response.json()["error"]["type"] == "HubVaultValidationError"

    def test_snapshot_plan_returns_immutable_download_manifest(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        response = client.post(
            "/api/v1/content/snapshot-plan",
            headers=ro_headers(),
            json={
                "allow_patterns": ["artifacts/*", "docs/"],
                "ignore_patterns": ["*.tmp"],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["revision"] == "release/v1"
        assert payload["resolved_revision"] == seeded["head_commit"].oid
        assert payload["head"] == seeded["head_commit"].oid
        assert payload["allow_patterns"] == ["artifacts/*", "docs/"]
        assert payload["ignore_patterns"] == ["*.tmp"]
        assert [item["path"] for item in payload["files"]] == [
            "artifacts/model.bin",
            "docs/guide.md",
        ]

        model_entry = payload["files"][0]
        model_query = parse_qs(urlparse(model_entry["download_url"]).query)
        assert model_query["revision"] == [seeded["head_commit"].oid]

        manifest_download = client.get(model_entry["download_url"], headers=ro_headers())
        assert manifest_download.status_code == 200
        assert manifest_download.content == seeded["model_bytes"]

