import pytest

from test.support import create_phase45_app, get_fastapi_test_client, ro_headers, seed_phase45_repo


@pytest.mark.unittest
class TestServerRefsRoutes:
    def test_refs_route_returns_branches_tags_and_optional_pull_requests(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        response = client.get("/api/v1/refs", headers=ro_headers())
        pull_request_response = client.get("/api/v1/refs", headers=ro_headers(), params={"include_pull_requests": True})

        assert response.status_code == 200
        assert response.json()["branches"] == [
            {
                "name": item.name,
                "ref": item.ref,
                "target_commit": item.target_commit,
            }
            for item in seeded["api"].list_repo_refs().branches
        ]
        assert response.json()["tags"] == [
            {
                "name": item.name,
                "ref": item.ref,
                "target_commit": item.target_commit,
            }
            for item in seeded["api"].list_repo_refs().tags
        ]
        assert response.json()["pull_requests"] is None

        assert pull_request_response.status_code == 200
        assert pull_request_response.json()["pull_requests"] == []

