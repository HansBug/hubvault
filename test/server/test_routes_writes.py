import json
from hashlib import sha256

import pytest

from hubvault import CommitOperationAdd
from hubvault.storage import ChunkStore
from test.support import (
    TEST_DEFAULT_BRANCH,
    create_phase45_app,
    get_fastapi_test_client,
    ro_headers,
    rw_headers,
    seed_phase78_repo,
)


def _sha256_hex(data):
    return sha256(data).hexdigest()


def _add_manifest(path_in_repo, data, include_chunks=False):
    payload = {
        "type": "add",
        "path_in_repo": path_in_repo,
        "size": len(data),
        "sha256": _sha256_hex(data),
        "chunks": [],
    }
    if include_chunks:
        plan = ChunkStore().plan_bytes(data)
        payload["chunks"] = [
            {
                "chunk_id": descriptor.chunk_id,
                "checksum": descriptor.checksum,
                "logical_offset": descriptor.logical_offset,
                "logical_size": descriptor.logical_size,
                "stored_size": descriptor.stored_size,
                "compression": descriptor.compression,
            }
            for descriptor in plan.chunks
        ]
    return payload


@pytest.mark.unittest
class TestServerWriteRoutes:
    def test_commit_plan_and_apply_support_copy_and_full_upload(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))
        new_bytes = b"new-phase78-file\n"
        manifest = {
            "revision": TEST_DEFAULT_BRANCH,
            "commit_message": "apply phase78 writes",
            "operations": [
                _add_manifest("docs/copied.txt", seeded["shared_text"]),
                _add_manifest("docs/new.txt", new_bytes),
            ],
        }

        plan_response = client.post("/api/v1/write/commit-plan", headers=rw_headers(), json=manifest)

        assert plan_response.status_code == 200
        plan_payload = plan_response.json()
        assert plan_payload["base_head"] == seeded["api"].repo_info().head
        assert [item["strategy"] for item in plan_payload["operations"]] == ["copy", "upload-full"]

        apply_manifest = dict(manifest)
        apply_manifest["parent_commit"] = plan_payload["base_head"]
        apply_manifest["upload_plan"] = plan_payload
        commit_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(apply_manifest)},
            files={
                "upload_file_1": ("docs-new.txt", new_bytes, "application/octet-stream"),
            },
        )

        assert commit_response.status_code == 200
        assert seeded["api"].read_bytes("docs/copied.txt") == seeded["shared_text"]
        assert seeded["api"].read_bytes("docs/new.txt") == new_bytes

    def test_commit_plan_reports_chunk_reuse_for_large_updates(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))
        manifest = {
            "revision": TEST_DEFAULT_BRANCH,
            "commit_message": "update large artifact",
            "operations": [
                _add_manifest("artifacts/large.bin", seeded["large_update"], include_chunks=True),
            ],
        }

        response = client.post("/api/v1/write/commit-plan", headers=rw_headers(), json=manifest)

        assert response.status_code == 200
        payload = response.json()
        assert payload["operations"][0]["strategy"] == "chunk-upload"
        assert payload["operations"][0]["reused_chunk_count"] > 0
        assert payload["statistics"]["planned_upload_bytes"] < len(seeded["large_update"])

        apply_manifest = dict(manifest)
        apply_manifest["parent_commit"] = payload["base_head"]
        apply_manifest["upload_plan"] = payload
        files = {}
        chunk_plan = ChunkStore().plan_bytes(seeded["large_update"])
        for missing_chunk in payload["operations"][0]["missing_chunks"]:
            chunk_index = int(missing_chunk["chunk_index"])
            files[str(missing_chunk["field_name"])] = (
                str(missing_chunk["chunk_id"]) + ".bin",
                chunk_plan.parts[chunk_index].data,
                "application/octet-stream",
            )
        commit_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(apply_manifest)},
            files=files,
        )

        assert commit_response.status_code == 200
        assert seeded["api"].read_bytes("artifacts/large.bin") == seeded["large_update"]

    def test_commit_apply_rejects_stale_plans_after_intervening_writes(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))
        new_bytes = b"phase78-stale-plan\n"
        manifest = {
            "revision": TEST_DEFAULT_BRANCH,
            "commit_message": "stale upload",
            "operations": [
                _add_manifest("docs/stale.txt", new_bytes),
            ],
        }

        plan_response = client.post("/api/v1/write/commit-plan", headers=rw_headers(), json=manifest)
        assert plan_response.status_code == 200
        plan_payload = plan_response.json()

        seeded["api"].create_commit(
            operations=[CommitOperationAdd("docs/intervening.txt", b"new head\n")],
            commit_message="intervening write",
        )

        apply_manifest = dict(manifest)
        apply_manifest["parent_commit"] = plan_payload["base_head"]
        apply_manifest["upload_plan"] = plan_payload
        response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(apply_manifest)},
            files={
                "upload_file_0": ("stale.txt", new_bytes, "application/octet-stream"),
            },
        )

        assert response.status_code == 409
        assert response.json()["error"]["type"] == "ConflictError"

    def test_ro_tokens_are_rejected_and_merge_conflicts_are_structured(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        seeded["api"].create_commit(
            operations=[CommitOperationAdd("docs/source.txt", b"main-change\n")],
            commit_message="change main source",
        )
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        forbidden_response = client.post(
            "/api/v1/write/commit-plan",
            headers=ro_headers(),
            json={
                "revision": TEST_DEFAULT_BRANCH,
                "commit_message": "forbidden",
                "operations": [_add_manifest("docs/forbidden.txt", b"x")],
            },
        )
        merge_response = client.post(
            "/api/v1/write/merge",
            headers=rw_headers(),
            json={
                "source_revision": "feature",
                "target_revision": TEST_DEFAULT_BRANCH,
            },
        )

        assert forbidden_response.status_code == 403
        assert merge_response.status_code == 200
        assert merge_response.json()["status"] == "conflict"
        assert merge_response.json()["conflicts"]
