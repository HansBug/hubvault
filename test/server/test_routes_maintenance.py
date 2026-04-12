import pytest

from hubvault import CommitOperationAdd
from test.support import create_phase45_app, get_fastapi_test_client, ro_headers, rw_headers, seed_phase45_repo


def _verify_report_payload(report):
    return {
        "ok": report.ok,
        "checked_refs": report.checked_refs,
        "warnings": report.warnings,
        "errors": report.errors,
    }


def _storage_overview_payload(overview):
    return {
        "total_size": overview.total_size,
        "reachable_size": overview.reachable_size,
        "historical_retained_size": overview.historical_retained_size,
        "reclaimable_gc_size": overview.reclaimable_gc_size,
        "reclaimable_cache_size": overview.reclaimable_cache_size,
        "reclaimable_temporary_size": overview.reclaimable_temporary_size,
        "sections": [
            {
                "name": section.name,
                "path": section.path,
                "total_size": section.total_size,
                "file_count": section.file_count,
                "reclaimable_size": section.reclaimable_size,
                "reclaim_strategy": section.reclaim_strategy,
                "notes": section.notes,
            }
            for section in overview.sections
        ],
        "recommendations": overview.recommendations,
    }


def _path_metrics(path):
    if not path.exists():
        return 0, 0
    if path.is_symlink() or path.is_file():
        return path.stat().st_size, 1

    total_size = 0
    file_count = 0
    for current in path.rglob("*"):
        if current.is_symlink() or current.is_file():
            total_size += current.stat().st_size
            file_count += 1
    return total_size, file_count


def _storage_summary_payload(repo_dir, api):
    refs = api.list_repo_refs()
    metadata_size = (
        _path_metrics(repo_dir / "FORMAT")[0]
        + _path_metrics(repo_dir / "metadata.sqlite3")[0]
        + _path_metrics(repo_dir / "locks")[0]
    )
    metadata_file_count = (
        _path_metrics(repo_dir / "FORMAT")[1]
        + _path_metrics(repo_dir / "metadata.sqlite3")[1]
        + _path_metrics(repo_dir / "locks")[1]
    )
    total_size, total_file_count = _path_metrics(repo_dir)
    return {
        "total_size": total_size,
        "total_file_count": total_file_count,
        "metadata_size": metadata_size,
        "metadata_file_count": metadata_file_count,
        "branch_count": len(refs.branches),
        "tag_count": len(refs.tags),
    }


@pytest.mark.unittest
class TestServerMaintenanceRoutes:
    def test_ro_token_can_read_verify_reports_and_storage_overview(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        quick_response = client.post("/api/v1/maintenance/quick-verify", headers=ro_headers())
        full_response = client.post("/api/v1/maintenance/full-verify", headers=ro_headers())
        summary_response = client.get("/api/v1/maintenance/storage-summary", headers=ro_headers())
        overview_response = client.get("/api/v1/maintenance/storage-overview", headers=ro_headers())

        assert quick_response.status_code == 200
        assert quick_response.json() == _verify_report_payload(seeded["api"].quick_verify())

        assert full_response.status_code == 200
        assert full_response.json() == _verify_report_payload(seeded["api"].full_verify())

        assert summary_response.status_code == 200
        assert summary_response.json() == _storage_summary_payload(repo_dir, seeded["api"])

        assert overview_response.status_code == 200
        assert overview_response.json() == _storage_overview_payload(seeded["api"].get_storage_overview())

    def test_rw_token_can_run_gc_and_squash_history(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        seeded["api"].create_commit(
            operations=[CommitOperationAdd("README.md", b"# hubvault phase45\n")],
            commit_message="second main commit",
        )
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        gc_response = client.post(
            "/api/v1/maintenance/gc",
            headers=rw_headers(),
            json={"dry_run": True, "prune_cache": True},
        )
        squash_response = client.post(
            "/api/v1/maintenance/squash-history",
            headers=rw_headers(),
            json={"ref_name": "release/v1", "run_gc": False},
        )

        assert gc_response.status_code == 200
        assert gc_response.json()["dry_run"] is True
        assert gc_response.json()["checked_refs"]

        assert squash_response.status_code == 200
        assert squash_response.json()["ref_name"] == "refs/heads/release/v1"
        assert squash_response.json()["rewritten_commit_count"] >= 1

    def test_ro_token_cannot_run_mutating_maintenance_endpoints(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        gc_response = client.post("/api/v1/maintenance/gc", headers=ro_headers(), json={})
        squash_response = client.post(
            "/api/v1/maintenance/squash-history",
            headers=ro_headers(),
            json={"ref_name": "release/v1"},
        )

        assert gc_response.status_code == 403
        assert squash_response.status_code == 403
