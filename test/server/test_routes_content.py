from urllib.parse import parse_qs, urlparse

import pytest

from hubvault.models import RepoFolder, RepoInfo
from hubvault.server.auth import TokenAuthorizer
from hubvault.server.exception_handlers import register_exception_handlers
from hubvault.server.routes.content import create_content_router
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
        blob_response = client.get("/api/v1/content/blob/configs/config.json", headers=ro_headers())
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
        tree_payload = {item["path"]: item for item in tree_response.json()}
        assert tree_payload["README.md"]["last_commit"]["title"] == "seed release"
        assert tree_payload["artifacts"]["last_commit"]["title"] == "update release artifacts"
        assert tree_payload["docs"]["last_commit"]["title"] == "update release artifacts"

        assert files_response.status_code == 200
        assert sorted(files_response.json()) == sorted(seeded["api"].list_repo_files())

        assert blob_response.status_code == 200
        assert blob_response.content == b'{"version": 1}\n'
        assert blob_response.headers["content-type"] == "application/json"

        assert download_response.status_code == 200
        assert download_response.content == seeded["model_bytes"]
        assert download_response.headers["X-HubVault-Repo-Path"] == "artifacts/model.bin"
        assert download_response.headers["ETag"] == seeded["api"].get_paths_info("artifacts/model.bin")[0].etag
        assert download_response.headers["content-type"] == "application/octet-stream"

    def test_blob_and_download_accept_query_token_for_browser_urls(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        blob_response = client.get(
            "/api/v1/content/blob/configs/config.json",
            params={"token": "ro-token"},
        )
        download_response = client.get(
            "/api/v1/content/download/artifacts/model.bin",
            params={"token": "ro-token"},
        )

        assert blob_response.status_code == 200
        assert blob_response.content == b'{"version": 1}\n'
        assert blob_response.headers["content-type"] == "application/json"

        assert download_response.status_code == 200
        assert download_response.content == seeded["model_bytes"]
        assert download_response.headers["content-type"] == "application/octet-stream"

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

    def test_snapshot_plan_rejects_non_file_entries_from_route_contract(self):
        fastapi = pytest.importorskip("fastapi")
        TestClient = get_fastapi_test_client()

        class _BadSnapshotApi:
            @staticmethod
            def repo_info(revision=None):
                del revision
                return RepoInfo(
                    repo_path="/tmp/repo",
                    format_version=1,
                    default_branch="main",
                    head="commit-1",
                    refs=[],
                )

            @staticmethod
            def list_repo_files(revision=None):
                del revision
                return ["artifacts"]

            @staticmethod
            def get_paths_info(paths, revision=None):
                del paths, revision
                return [RepoFolder("artifacts", "tree-1")]

        app = fastapi.FastAPI()
        register_exception_handlers(app)
        app.include_router(
            create_content_router(
                api=_BadSnapshotApi(),
                authorizer=TokenAuthorizer(token_ro=("ro-token",), token_rw=("rw-token",)),
            )
        )
        client = TestClient(app)

        response = client.post("/api/v1/content/snapshot-plan", headers=ro_headers(), json={})

        assert response.status_code == 400
        assert response.json()["error"] == {
            "type": "HubVaultValidationError",
            "message": "Snapshot plans can only contain file entries.",
        }
