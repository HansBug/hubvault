import pytest

from test.support import create_phase45_app, get_fastapi_test_client, ro_headers, seed_phase45_repo


@pytest.mark.unittest
class TestServerHistoryRoutes:
    def test_ro_token_can_read_commit_history(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        response = client.get("/api/v1/history/commits", headers=ro_headers(), params={"formatted": True})

        assert response.status_code == 200
        assert response.json() == [
            {
                "commit_id": item.commit_id,
                "authors": item.authors,
                "created_at": item.created_at.isoformat(),
                "title": item.title,
                "message": item.message,
                "formatted_title": item.formatted_title,
                "formatted_message": item.formatted_message,
            }
            for item in seeded["api"].list_repo_commits(formatted=True)
        ]

    def test_ro_token_can_read_reflog(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        response = client.get("/api/v1/history/reflog/release/v1", headers=ro_headers(), params={"limit": 2})

        assert response.status_code == 200
        assert response.json() == [
            {
                "timestamp": item.timestamp.isoformat(),
                "ref_name": item.ref_name,
                "old_head": item.old_head,
                "new_head": item.new_head,
                "message": item.message,
                "checksum": item.checksum,
            }
            for item in seeded["api"].list_repo_reflog("release/v1", limit=2)
        ]

    def test_ro_token_can_read_commit_detail(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        detail = seeded["api"].get_commit_detail(seeded["head_commit"].oid, formatted=True)
        response = client.get(
            "/api/v1/history/commits/%s" % (seeded["head_commit"].oid,),
            headers=ro_headers(),
            params={"formatted": True},
        )

        assert response.status_code == 200
        assert response.json()["commit"]["commit_id"] == detail.commit.commit_id
        assert response.json()["commit"]["formatted_title"] == detail.commit.formatted_title
        assert response.json()["parent_commit_ids"] == detail.parent_commit_ids
        assert response.json()["compare_parent_commit_id"] == detail.compare_parent_commit_id
        assert [item["path"] for item in response.json()["changes"]] == [item.path for item in detail.changes]
