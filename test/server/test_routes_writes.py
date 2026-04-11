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
    seed_phase45_repo,
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
    def test_commit_plan_and_apply_support_copy_delete_passthrough(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))
        manifest = {
            "revision": TEST_DEFAULT_BRANCH,
            "commit_message": "copy and delete through passthrough",
            "operations": [
                {
                    "type": "copy",
                    "src_path_in_repo": "docs/source.txt",
                    "path_in_repo": "docs/copied.txt",
                    "src_revision": TEST_DEFAULT_BRANCH,
                },
                {
                    "type": "delete",
                    "path_in_repo": "README.md",
                    "is_folder": False,
                },
            ],
        }

        plan_response = client.post("/api/v1/write/commit-plan", headers=rw_headers(), json=manifest)

        assert plan_response.status_code == 200
        plan_payload = plan_response.json()
        assert [item["strategy"] for item in plan_payload["operations"]] == ["passthrough", "passthrough"]

        apply_manifest = dict(manifest)
        apply_manifest["parent_commit"] = plan_payload["base_head"]
        apply_manifest["upload_plan"] = plan_payload
        commit_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            json=apply_manifest,
        )

        assert commit_response.status_code == 200
        assert seeded["api"].read_bytes("docs/copied.txt") == seeded["shared_text"]
        assert "README.md" not in seeded["api"].list_repo_files()

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
            data={"manifest": json.dumps(apply_manifest), "note": "skip extra field"},
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

    def test_branch_and_tag_routes_apply_default_flags_when_omitted(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        branch_response = client.post(
            "/api/v1/write/branches",
            headers=rw_headers(),
            json={
                "branch": "staging",
                "revision": TEST_DEFAULT_BRANCH,
            },
        )
        tag_response = client.post(
            "/api/v1/write/tags",
            headers=rw_headers(),
            json={
                "tag": "phase78-v2",
                "revision": TEST_DEFAULT_BRANCH,
            },
        )

        refs = seeded["api"].list_repo_refs()

        assert branch_response.status_code == 200
        assert tag_response.status_code == 200
        assert any(item.ref == "refs/heads/staging" for item in refs.branches)
        assert any(item.ref == "refs/tags/phase78-v2" for item in refs.tags)

    @pytest.mark.parametrize(
        ("method", "url", "payload", "message"),
        [
            (
                "post",
                "/api/v1/write/branches",
                [],
                "create_branch request body must be a JSON object.",
            ),
            (
                "post",
                "/api/v1/write/branches",
                {"branch": 1},
                "create_branch.branch must be a string.",
            ),
            (
                "post",
                "/api/v1/write/branches",
                {"branch": "demo", "exist_ok": "yes"},
                "create_branch.exist_ok must be a boolean.",
            ),
            (
                "post",
                "/api/v1/write/tags",
                {"tag": "v1", "tag_message": 1},
                "create_tag.tag_message must be a string.",
            ),
            (
                "post",
                "/api/v1/write/merge",
                {"source_revision": "feature", "target_revision": 1},
                "merge.target_revision must be a string.",
            ),
            (
                "post",
                "/api/v1/write/reset-ref",
                {"ref_name": "release/v1", "to_revision": 1},
                "reset_ref.to_revision must be a string.",
            ),
            (
                "post",
                "/api/v1/write/delete-file",
                {"path_in_repo": 1},
                "delete_file.path_in_repo must be a string.",
            ),
            (
                "post",
                "/api/v1/write/delete-folder",
                {"path_in_repo": 1},
                "delete_folder.path_in_repo must be a string.",
            ),
        ],
    )
    def test_write_routes_reject_invalid_json_shapes(self, tmp_path, method, url, payload, message):
        repo_dir = tmp_path / "repo"
        seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        response = getattr(client, method)(url, headers=rw_headers(), json=payload)

        assert response.status_code == 400
        assert response.json()["error"]["message"] == message

    def test_commit_apply_rejects_invalid_bodies_and_missing_upload_plan(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        invalid_json_response = client.post(
            "/api/v1/write/commit",
            headers=dict(rw_headers(), **{"content-type": "application/json"}),
            data="{",
        )
        missing_manifest_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={},
            files={"upload_file_0": ("demo.txt", b"x", "application/octet-stream")},
        )
        invalid_manifest_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": "{"},
            files={"upload_file_0": ("demo.txt", b"x", "application/octet-stream")},
        )
        missing_plan_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            json={
                "revision": TEST_DEFAULT_BRANCH,
                "commit_message": "missing upload plan",
                "operations": [],
            },
        )

        assert invalid_json_response.status_code == 400
        assert "Request body must contain valid JSON" in invalid_json_response.json()["error"]["message"]
        assert missing_manifest_response.status_code == 400
        assert missing_manifest_response.json()["error"]["message"] == (
            "multipart form field 'manifest' must contain JSON text."
        )
        assert invalid_manifest_response.status_code == 400
        assert "multipart form field 'manifest' must contain valid JSON" in invalid_manifest_response.json()[
            "error"
        ]["message"]
        assert missing_plan_response.status_code == 400
        assert missing_plan_response.json()["error"]["message"] == (
            "upload_plan is required when applying a write manifest."
        )

    def test_commit_apply_rejects_tampered_upload_plans_and_upload_payloads(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        small_bytes = b"small upload\n"
        manifest = {
            "revision": TEST_DEFAULT_BRANCH,
            "commit_message": "validate apply manifest",
            "operations": [
                _add_manifest("docs/new.txt", small_bytes),
            ],
        }

        plan_response = client.post("/api/v1/write/commit-plan", headers=rw_headers(), json=manifest)
        assert plan_response.status_code == 200
        plan_payload = plan_response.json()

        def _apply_payload():
            payload = json.loads(json.dumps(manifest))
            payload["upload_plan"] = json.loads(json.dumps(plan_payload))
            return payload

        mismatched_count = _apply_payload()
        mismatched_count["upload_plan"]["operations"] = []
        mismatched_count_response = client.post("/api/v1/write/commit", headers=rw_headers(), json=mismatched_count)

        mismatched_index = _apply_payload()
        mismatched_index["upload_plan"]["operations"][0]["index"] = 1
        mismatched_index_response = client.post("/api/v1/write/commit", headers=rw_headers(), json=mismatched_index)

        mismatched_type = _apply_payload()
        mismatched_type["upload_plan"]["operations"][0]["type"] = "copy"
        mismatched_type_response = client.post("/api/v1/write/commit", headers=rw_headers(), json=mismatched_type)

        mismatched_path = _apply_payload()
        mismatched_path["upload_plan"]["operations"][0]["path_in_repo"] = "docs/other.txt"
        mismatched_path_response = client.post("/api/v1/write/commit", headers=rw_headers(), json=mismatched_path)

        mismatched_revision = _apply_payload()
        mismatched_revision["upload_plan"]["revision"] = "refs/heads/feature"
        mismatched_revision_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            json=mismatched_revision,
        )

        missing_upload_response = client.post("/api/v1/write/commit", headers=rw_headers(), json=_apply_payload())
        wrong_size_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(_apply_payload())},
            files={"upload_file_0": ("new.txt", b"tiny", "application/octet-stream")},
        )
        wrong_checksum_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(_apply_payload())},
            files={"upload_file_0": ("new.txt", b"small uploae\n", "application/octet-stream")},
        )

        assert mismatched_count_response.status_code == 400
        assert mismatched_count_response.json()["error"]["message"] == "upload_plan.operations must align with operations."
        assert mismatched_index_response.status_code == 400
        assert mismatched_index_response.json()["error"]["message"] == "upload_plan.operations[0].index is out of sync."
        assert mismatched_type_response.status_code == 400
        assert mismatched_type_response.json()["error"]["message"] == "upload_plan.operations[0].type is out of sync."
        assert mismatched_path_response.status_code == 400
        assert mismatched_path_response.json()["error"]["message"] == (
            "upload_plan.operations[0].path_in_repo is out of sync."
        )
        assert mismatched_revision_response.status_code == 400
        assert mismatched_revision_response.json()["error"]["message"] == (
            "upload_plan.revision does not match the selected target branch."
        )
        assert missing_upload_response.status_code == 400
        assert missing_upload_response.json()["error"]["message"] == "Missing uploaded file payload: upload_file_0."
        assert wrong_size_response.status_code == 400
        assert wrong_size_response.json()["error"]["message"] == (
            "Uploaded file payload size does not match the manifest."
        )
        assert wrong_checksum_response.status_code == 400
        assert wrong_checksum_response.json()["error"]["message"] == (
            "Uploaded file payload checksum does not match the manifest."
        )

        large_manifest = {
            "revision": TEST_DEFAULT_BRANCH,
            "commit_message": "validate chunk upload",
            "operations": [
                _add_manifest("artifacts/large.bin", seeded["large_update"], include_chunks=True),
            ],
        }
        large_plan_response = client.post("/api/v1/write/commit-plan", headers=rw_headers(), json=large_manifest)
        assert large_plan_response.status_code == 200
        large_plan_payload = large_plan_response.json()
        missing_chunk = large_plan_payload["operations"][0]["missing_chunks"][0]
        missing_chunk_field = missing_chunk["field_name"]
        chunk_plan = ChunkStore().plan_bytes(seeded["large_update"])
        chunk_bytes = chunk_plan.parts[int(missing_chunk["chunk_index"])].data

        def _large_apply_payload():
            payload = json.loads(json.dumps(large_manifest))
            payload["upload_plan"] = json.loads(json.dumps(large_plan_payload))
            return payload

        missing_chunk_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            json=_large_apply_payload(),
        )
        wrong_chunk_size_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(_large_apply_payload())},
            files={
                missing_chunk_field: ("chunk.bin", chunk_bytes[:-1], "application/octet-stream"),
            },
        )
        wrong_chunk_checksum_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(_large_apply_payload())},
            files={
                missing_chunk_field: ("chunk.bin", b"x" * len(chunk_bytes), "application/octet-stream"),
            },
        )

        size_mismatch_manifest = _large_apply_payload()
        size_mismatch_manifest["operations"][0]["size"] = size_mismatch_manifest["operations"][0]["size"] - 1
        wrong_file_size_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(size_mismatch_manifest)},
            files={
                missing_chunk_field: ("chunk.bin", chunk_bytes, "application/octet-stream"),
            },
        )

        checksum_mismatch_manifest = _large_apply_payload()
        checksum_mismatch_manifest["operations"][0]["sha256"] = "0" * 64
        wrong_file_checksum_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            data={"manifest": json.dumps(checksum_mismatch_manifest)},
            files={
                missing_chunk_field: ("chunk.bin", chunk_bytes, "application/octet-stream"),
            },
        )

        assert missing_chunk_response.status_code == 400
        assert missing_chunk_response.json()["error"]["message"] == (
            "Missing uploaded chunk payload: %s." % (missing_chunk_field,)
        )
        assert wrong_chunk_size_response.status_code == 400
        assert wrong_chunk_size_response.json()["error"]["message"] == "Chunk payload size does not match the manifest."
        assert wrong_chunk_checksum_response.status_code == 400
        assert wrong_chunk_checksum_response.json()["error"]["message"] == (
            "Chunk payload checksum does not match the manifest."
        )
        assert wrong_file_size_response.status_code == 400
        assert wrong_file_size_response.json()["error"]["message"] == (
            "Reconstructed file size does not match the manifest."
        )
        assert wrong_file_checksum_response.status_code == 400
        assert wrong_file_checksum_response.json()["error"]["message"] == (
            "Reconstructed file checksum does not match the manifest."
        )

        unsupported_strategy_manifest = _large_apply_payload()
        unsupported_strategy_manifest["upload_plan"]["operations"][0]["strategy"] = "mystery"
        unsupported_strategy_response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            json=unsupported_strategy_manifest,
        )

        assert unsupported_strategy_response.status_code == 400
        assert unsupported_strategy_response.json()["error"]["message"] == "Unsupported upload strategy: mystery."

    def test_commit_apply_rejects_stale_upload_plan_without_explicit_parent_commit(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))
        new_bytes = b"phase78-stale-plan-without-parent\n"
        manifest = {
            "revision": TEST_DEFAULT_BRANCH,
            "commit_message": "stale upload without explicit parent",
            "operations": [
                _add_manifest("docs/stale-no-parent.txt", new_bytes),
            ],
        }

        plan_response = client.post("/api/v1/write/commit-plan", headers=rw_headers(), json=manifest)
        assert plan_response.status_code == 200
        plan_payload = plan_response.json()

        seeded["api"].create_commit(
            operations=[CommitOperationAdd("docs/intervening-two.txt", b"new head\n")],
            commit_message="intervening write two",
        )

        apply_manifest = json.loads(json.dumps(manifest))
        apply_manifest["parent_commit"] = seeded["api"].repo_info().head
        apply_manifest["upload_plan"] = plan_payload
        response = client.post(
            "/api/v1/write/commit",
            headers=rw_headers(),
            json=apply_manifest,
        )

        assert response.status_code == 409
        assert response.json()["error"]["message"] == "branch head changed after upload planning; please re-plan the upload"

    def test_reset_ref_and_delete_folder_routes_apply_successfully(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        TestClient = get_fastapi_test_client()
        client = TestClient(create_phase45_app(repo_dir))

        reset_response = client.post(
            "/api/v1/write/reset-ref",
            headers=rw_headers(),
            json={
                "ref_name": TEST_DEFAULT_BRANCH,
                "to_revision": seeded["seed_commit"].oid,
            },
        )

        assert reset_response.status_code == 200
        assert seeded["api"].repo_info().head == seeded["seed_commit"].oid
        assert "docs/guide.md" not in seeded["api"].list_repo_files()

        delete_folder_response = client.post(
            "/api/v1/write/delete-folder",
            headers=rw_headers(),
            json={
                "path_in_repo": "artifacts",
                "revision": TEST_DEFAULT_BRANCH,
            },
        )

        assert delete_folder_response.status_code == 200
        remaining_files = seeded["api"].list_repo_files()
        assert "artifacts/model.bin" not in remaining_files
        assert "artifacts/weights.tmp" not in remaining_files
