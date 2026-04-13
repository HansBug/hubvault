import pytest

from hubvault.errors import HubVaultValidationError
from hubvault.server.schemas import (
    build_error_payload,
    normalize_commit_manifest_request,
    normalize_gc_request,
    normalize_paths_request,
    normalize_squash_history_request,
    normalize_snapshot_plan_request,
)


@pytest.mark.unittest
class TestServerSchemas:
    def test_normalize_paths_request_accepts_strings_lists_and_objects(self):
        assert normalize_paths_request("demo.txt") == ["demo.txt"]
        assert normalize_paths_request(["a.txt", "b.txt"]) == ["a.txt", "b.txt"]
        assert normalize_paths_request({"paths": "nested/demo.txt"}) == ["nested/demo.txt"]

    def test_normalize_paths_request_rejects_invalid_shapes(self):
        with pytest.raises(HubVaultValidationError, match="paths items must be strings"):
            normalize_paths_request(["ok", 1])

        with pytest.raises(HubVaultValidationError, match="Request body must be a path string"):
            normalize_paths_request(1)

    def test_normalize_snapshot_plan_request_accepts_none_strings_and_lists(self):
        assert normalize_snapshot_plan_request(None) == {
            "allow_patterns": [],
            "ignore_patterns": [],
        }
        assert normalize_snapshot_plan_request(
            {
                "allow_patterns": "artifacts/*",
                "ignore_patterns": ["*.tmp"],
            }
        ) == {
            "allow_patterns": ["artifacts/*"],
            "ignore_patterns": ["*.tmp"],
        }

    def test_normalize_snapshot_plan_request_rejects_invalid_payloads(self):
        with pytest.raises(HubVaultValidationError, match="allow_patterns items must be strings"):
            normalize_snapshot_plan_request({"allow_patterns": ["ok", 2]})

        with pytest.raises(HubVaultValidationError, match="ignore_patterns must be a string or a list of strings"):
            normalize_snapshot_plan_request({"ignore_patterns": 1})

        with pytest.raises(HubVaultValidationError, match="Request body must be a JSON object"):
            normalize_snapshot_plan_request(1)

    def test_build_error_payload_returns_stable_shape(self):
        assert build_error_payload("ConflictError", "boom") == {
            "error": {
                "type": "ConflictError",
                "message": "boom",
            }
        }

    def test_normalize_commit_manifest_request_accepts_manifest_and_plan_payloads(self):
        payload = normalize_commit_manifest_request(
            {
                "revision": "main",
                "parent_commit": "abc",
                "commit_message": "seed",
                "commit_description": "body",
                "operations": [
                    {
                        "type": "add",
                        "path_in_repo": "demo.txt",
                        "size": 4,
                        "sha256": "sha256:abcd",
                        "chunks": [
                            {
                                "chunk_id": "sha256:chunk",
                                "checksum": "sha256:chunk",
                                "logical_offset": 0,
                                "logical_size": 4,
                                "stored_size": 4,
                                "compression": "none",
                            }
                        ],
                    },
                    {
                        "type": "delete",
                        "path_in_repo": "old.txt",
                        "is_folder": False,
                    },
                    {
                        "type": "copy",
                        "src_path_in_repo": "source.txt",
                        "path_in_repo": "copied.txt",
                        "src_revision": "refs/heads/main",
                    },
                ],
                "upload_plan": {
                    "revision": "main",
                    "base_head": "abc",
                    "operations": [
                        {
                            "index": 0,
                            "type": "add",
                            "path_in_repo": "demo.txt",
                            "strategy": "chunk-upload",
                            "missing_chunks": [
                                {
                                    "chunk_id": "sha256:chunk",
                                    "chunk_index": 0,
                                    "field_name": "upload_chunk_0_0",
                                    "logical_size": 4,
                                }
                            ],
                            "reused_chunk_count": 0,
                            "missing_chunk_count": 1,
                        },
                        {
                            "index": 1,
                            "type": "delete",
                            "path_in_repo": "old.txt",
                            "strategy": "passthrough",
                            "missing_chunks": [],
                            "reused_chunk_count": 0,
                            "missing_chunk_count": 0,
                        },
                    ],
                },
            }
        )

        assert payload["operations"][0]["sha256"] == "abcd"
        assert payload["operations"][2]["src_path_in_repo"] == "source.txt"
        assert payload["upload_plan"]["operations"][0]["missing_chunks"][0]["field_name"] == "upload_chunk_0_0"

    def test_normalize_commit_manifest_request_rejects_invalid_shapes(self):
        with pytest.raises(HubVaultValidationError, match="Request body must be a JSON object"):
            normalize_commit_manifest_request(None)

        with pytest.raises(HubVaultValidationError, match="operations must be a JSON array"):
            normalize_commit_manifest_request({"operations": "bad", "commit_message": "seed"})

        with pytest.raises(HubVaultValidationError, match="operations\\[0\\] must be a JSON object"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": ["bad"],
                }
            )

        with pytest.raises(HubVaultValidationError, match="operations\\[0\\]\\.chunks must be a JSON array"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [
                        {
                            "type": "add",
                            "path_in_repo": "demo.txt",
                            "size": 4,
                            "sha256": "sha256:abcd",
                            "chunks": "bad",
                        }
                    ],
                }
            )

        with pytest.raises(HubVaultValidationError, match="operations\\[0\\]\\.chunks\\[0\\] must be a JSON object"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [
                        {
                            "type": "add",
                            "path_in_repo": "demo.txt",
                            "size": 4,
                            "sha256": "sha256:abcd",
                            "chunks": ["bad"],
                        }
                    ],
                }
            )

        with pytest.raises(HubVaultValidationError, match="upload_plan must be a JSON object"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [],
                    "upload_plan": "bad",
                }
            )

        with pytest.raises(HubVaultValidationError, match="upload_plan\\.operations must be a JSON array"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [],
                    "upload_plan": {
                        "revision": "main",
                        "operations": "bad",
                    },
                }
            )

        with pytest.raises(HubVaultValidationError, match="upload_plan\\.operations\\[0\\] must be a JSON object"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [],
                    "upload_plan": {
                        "revision": "main",
                        "operations": ["bad"],
                    },
                }
            )

        with pytest.raises(HubVaultValidationError, match="upload_plan\\.operations\\[0\\]\\.missing_chunks must be a JSON array"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [],
                    "upload_plan": {
                        "revision": "main",
                        "operations": [
                            {
                                "index": 0,
                                "type": "add",
                                "strategy": "chunk-upload",
                                "missing_chunks": "bad",
                            }
                        ],
                    },
                }
            )

        with pytest.raises(HubVaultValidationError, match="upload_plan\\.operations\\[0\\]\\.missing_chunks\\[0\\] must be a JSON object"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [],
                    "upload_plan": {
                        "revision": "main",
                        "operations": [
                            {
                                "index": 0,
                                "type": "add",
                                "strategy": "chunk-upload",
                                "missing_chunks": ["bad"],
                            }
                        ],
                    },
                }
            )

        with pytest.raises(HubVaultValidationError, match="commit_message must be a string"):
            normalize_commit_manifest_request(
                {
                    "commit_message": None,
                    "operations": [],
                }
            )

        with pytest.raises(HubVaultValidationError, match="ref_name must be a string"):
            normalize_squash_history_request(
                {
                    "ref_name": None,
                }
            )

        with pytest.raises(HubVaultValidationError, match="Request body must be a JSON object"):
            normalize_gc_request("bad")

        with pytest.raises(HubVaultValidationError, match="Request body must be a JSON object"):
            normalize_squash_history_request("bad")

        with pytest.raises(HubVaultValidationError, match="run_gc must be a boolean"):
            normalize_squash_history_request(
                {
                    "ref_name": "main",
                    "run_gc": "bad",
                }
            )

        with pytest.raises(HubVaultValidationError, match="dry_run must be a boolean"):
            normalize_gc_request({"dry_run": "bad"})

        with pytest.raises(HubVaultValidationError, match="prune_cache must be a boolean"):
            normalize_gc_request({"prune_cache": "bad"})

        with pytest.raises(HubVaultValidationError, match="Unsupported write operation type"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [{"type": "unknown"}],
                }
            )

    def test_normalize_commit_manifest_request_rejects_invalid_scalar_field_types(self):
        with pytest.raises(HubVaultValidationError, match="revision must be a string"):
            normalize_commit_manifest_request(
                {
                    "revision": 1,
                    "commit_message": "seed",
                    "operations": [],
                }
            )

        with pytest.raises(HubVaultValidationError, match="parent_commit must be a string"):
            normalize_commit_manifest_request(
                {
                    "parent_commit": 1,
                    "commit_message": "seed",
                    "operations": [],
                }
            )

        with pytest.raises(HubVaultValidationError, match="commit_description must be a string"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "commit_description": 1,
                    "operations": [],
                }
            )

        with pytest.raises(HubVaultValidationError, match="size must be a non-negative integer"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [
                        {
                            "type": "add",
                            "path_in_repo": "demo.txt",
                            "size": True,
                            "sha256": "abcd",
                            "chunks": [],
                        }
                    ],
                }
            )

        with pytest.raises(HubVaultValidationError, match="logical_offset must be a non-negative integer"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [
                        {
                            "type": "add",
                            "path_in_repo": "demo.txt",
                            "size": 4,
                            "sha256": "abcd",
                            "chunks": [
                                {
                                    "chunk_id": "sha256:chunk",
                                    "checksum": "sha256:chunk",
                                    "logical_offset": -1,
                                    "logical_size": 4,
                                    "stored_size": 4,
                                    "compression": "none",
                                }
                            ],
                        }
                    ],
                }
            )

        with pytest.raises(HubVaultValidationError, match="is_folder must be a boolean"):
            normalize_commit_manifest_request(
                {
                    "commit_message": "seed",
                    "operations": [
                        {
                            "type": "delete",
                            "path_in_repo": "demo.txt",
                            "is_folder": "bad",
                        }
                    ],
                }
            )

    def test_normalize_gc_and_squash_requests(self):
        assert normalize_gc_request(None) == {"dry_run": False, "prune_cache": True}
        assert normalize_squash_history_request(
            {
                "ref_name": "main",
                "run_gc": False,
                "prune_cache": True,
            }
        ) == {
            "ref_name": "main",
            "root_revision": None,
            "commit_message": None,
            "commit_description": None,
            "run_gc": False,
            "prune_cache": True,
        }
