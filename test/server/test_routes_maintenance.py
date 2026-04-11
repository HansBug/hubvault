import pytest

from test.support import create_phase45_app, get_fastapi_test_client, ro_headers, seed_phase45_repo


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


@pytest.mark.unittest
class TestServerMaintenanceRoutes:
    def test_ro_token_can_read_verify_reports_and_storage_overview(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        quick_response = client.post("/api/v1/maintenance/quick-verify", headers=ro_headers())
        full_response = client.post("/api/v1/maintenance/full-verify", headers=ro_headers())
        overview_response = client.get("/api/v1/maintenance/storage-overview", headers=ro_headers())

        assert quick_response.status_code == 200
        assert quick_response.json() == _verify_report_payload(seeded["api"].quick_verify())

        assert full_response.status_code == 200
        assert full_response.json() == _verify_report_payload(seeded["api"].full_verify())

        assert overview_response.status_code == 200
        assert overview_response.json() == _storage_overview_payload(seeded["api"].get_storage_overview())
