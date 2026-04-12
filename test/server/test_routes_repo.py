import pytest

from test.support import create_phase45_app, get_fastapi_test_client, ro_headers, seed_phase45_repo


@pytest.mark.unittest
class TestServerRepoRoutes:
    def test_repo_route_uses_repository_default_branch_without_assuming_main(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        response = client.get("/api/v1/repo", headers=ro_headers())

        assert response.status_code == 200
        assert response.json() == {
            "repo_path": str(repo_dir),
            "format_version": seeded["repo_info"].format_version,
            "default_branch": "release/v1",
            "head": seeded["head_commit"].oid,
            "refs": seeded["repo_info"].refs,
        }

