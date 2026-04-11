from datetime import datetime

import pytest

from hubvault.errors import EntryNotFoundError
from hubvault.remote.errors import HubVaultRemoteAuthError, HubVaultRemoteProtocolError
from hubvault.remote.serde import (
    decode_commit_info,
    decode_error_response,
    decode_gc_report,
    decode_git_commit_info,
    decode_git_commit_list,
    decode_git_refs,
    decode_merge_result,
    decode_reflog_entries,
    decode_repo_entry,
    decode_repo_entries,
    decode_snapshot_plan,
    decode_squash_report,
    decode_storage_overview,
    decode_verify_report,
)


@pytest.mark.unittest
class TestRemoteSerde:
    def test_decode_repo_entries_and_refs_round_trip_shapes(self):
        entries = decode_repo_entries(
            [
                {
                    "entry_type": "folder",
                    "path": "artifacts",
                    "tree_id": "tree-1",
                    "last_commit": None,
                },
                {
                    "entry_type": "file",
                    "path": "artifacts/model.bin",
                    "size": 12,
                    "blob_id": "blob-1",
                    "lfs": {
                        "size": 12,
                        "sha256": "abc",
                        "pointer_size": 128,
                    },
                    "last_commit": {
                        "oid": "commit-1",
                        "title": "seed",
                        "date": datetime(2026, 4, 11, 10, 0, 0).isoformat(),
                    },
                    "security": {
                        "safe": True,
                        "status": "clean",
                        "av_scan": {"state": "ok"},
                        "pickle_import_scan": None,
                    },
                    "oid": "blob-1",
                    "sha256": "abc",
                    "etag": "etag-1",
                },
            ]
        )
        refs = decode_git_refs(
            {
                "branches": [{"name": "main", "ref": "refs/heads/main", "target_commit": "commit-2"}],
                "converts": [],
                "tags": [{"name": "v1", "ref": "refs/tags/v1", "target_commit": "commit-1"}],
                "pull_requests": [],
            }
        )

        assert [item.path for item in entries] == ["artifacts", "artifacts/model.bin"]
        assert entries[1].lfs.sha256 == "abc"
        assert entries[1].security.status == "clean"
        assert refs.branches[0].name == "main"
        assert refs.tags[0].target_commit == "commit-1"
        assert refs.pull_requests == []

    def test_decode_snapshot_plan_validates_shape(self):
        manifest = decode_snapshot_plan(
            {
                "revision": "main",
                "resolved_revision": "commit-2",
                "head": "commit-2",
                "allow_patterns": ["artifacts/*"],
                "ignore_patterns": ["*.tmp"],
                "files": [
                    {
                        "path": "artifacts/model.bin",
                        "size": 12,
                        "blob_id": "blob-1",
                        "oid": "blob-1",
                        "sha256": "abc",
                        "etag": "etag-1",
                        "download_url": "/api/v1/content/download/artifacts/model.bin?revision=commit-2",
                    }
                ],
            }
        )

        assert manifest["resolved_revision"] == "commit-2"
        assert manifest["files"][0]["path"] == "artifacts/model.bin"

        with pytest.raises(HubVaultRemoteProtocolError, match="Snapshot plan files must be a JSON array"):
            decode_snapshot_plan(
                {
                    "revision": "main",
                    "resolved_revision": "commit-2",
                    "head": "commit-2",
                    "allow_patterns": [],
                    "ignore_patterns": [],
                    "files": {},
                }
            )

    def test_decode_error_response_maps_public_and_auth_errors(self):
        public_error = decode_error_response(
            {"error": {"type": "EntryNotFoundError", "message": "missing.txt"}},
            status_code=404,
        )
        auth_error = decode_error_response(
            {"error": {"type": "PermissionError", "message": "bad token"}},
            status_code=401,
        )

        assert isinstance(public_error, EntryNotFoundError)
        assert isinstance(auth_error, HubVaultRemoteAuthError)

    def test_decode_error_response_supports_detail_fallback_and_unknown_types(self):
        detail_error = decode_error_response({"detail": "plain error"}, status_code=500)
        auth_error = decode_error_response({"detail": "forbidden"}, status_code=403)

        assert isinstance(detail_error, HubVaultRemoteProtocolError)
        assert str(detail_error) == "plain error"
        assert isinstance(auth_error, HubVaultRemoteAuthError)
        assert str(auth_error) == "forbidden"

    def test_decode_repo_entry_rejects_invalid_nested_shapes_and_entry_types(self):
        with pytest.raises(HubVaultRemoteProtocolError, match="lfs must be a JSON object"):
            decode_repo_entry(
                {
                    "entry_type": "file",
                    "path": "artifacts/model.bin",
                    "size": 12,
                    "blob_id": "blob-1",
                    "lfs": [],
                    "last_commit": None,
                    "security": None,
                    "oid": "blob-1",
                    "sha256": "abc",
                    "etag": "etag-1",
                }
            )

        with pytest.raises(HubVaultRemoteProtocolError, match="security must be a JSON object"):
            decode_repo_entry(
                {
                    "entry_type": "file",
                    "path": "artifacts/model.bin",
                    "size": 12,
                    "blob_id": "blob-1",
                    "lfs": None,
                    "last_commit": None,
                    "security": [],
                    "oid": "blob-1",
                    "sha256": "abc",
                    "etag": "etag-1",
                }
            )

        with pytest.raises(HubVaultRemoteProtocolError, match="Unsupported repo entry type"):
            decode_repo_entry({"entry_type": "other"})

    def test_decode_commit_and_collection_helpers_reject_invalid_shapes(self):
        with pytest.raises(HubVaultRemoteProtocolError, match="error response must be a JSON object"):
            decode_error_response([], status_code=500)

        with pytest.raises(HubVaultRemoteProtocolError, match="created_at must be an ISO-8601 string"):
            decode_git_commit_info(
                {
                    "commit_id": "commit-1",
                    "authors": [],
                    "created_at": 1,
                    "title": "seed",
                    "message": "",
                    "formatted_title": None,
                    "formatted_message": None,
                }
            )

        with pytest.raises(HubVaultRemoteProtocolError, match="Invalid datetime for created_at"):
            decode_git_commit_info(
                {
                    "commit_id": "commit-1",
                    "authors": [],
                    "created_at": "not-a-datetime",
                    "title": "seed",
                    "message": "",
                    "formatted_title": None,
                    "formatted_message": None,
                }
            )

        with pytest.raises(HubVaultRemoteProtocolError, match="Commit list must be a JSON array"):
            decode_git_commit_list({})

        with pytest.raises(HubVaultRemoteProtocolError, match="Repository entries must be a JSON array"):
            decode_repo_entries({})

        with pytest.raises(HubVaultRemoteProtocolError, match="Reflog entries must be a JSON array"):
            decode_reflog_entries({})

    def test_decode_commit_merge_verify_and_maintenance_reports(self):
        commit = decode_commit_info(
            {
                "commit_url": "file:///tmp/repo#commit=abc",
                "commit_message": "seed",
                "commit_description": "body",
                "oid": "abc",
                "pr_url": None,
                "_url": "file:///tmp/repo#blob=main:demo.txt",
            }
        )
        merge = decode_merge_result(
            {
                "status": "conflict",
                "target_revision": "main",
                "source_revision": "feature",
                "base_commit": "base",
                "target_head_before": "target",
                "source_head": "source",
                "head_after": "target",
                "commit": None,
                "conflicts": [
                    {
                        "path": "demo.txt",
                        "conflict_type": "modify/modify",
                        "message": "Both sides changed demo.txt differently.",
                        "base_oid": "base-oid",
                        "target_oid": "target-oid",
                        "source_oid": "source-oid",
                        "related_path": None,
                    }
                ],
                "fast_forward": False,
                "created_commit": False,
            }
        )
        verify = decode_verify_report(
            {
                "ok": True,
                "checked_refs": ["refs/heads/main"],
                "warnings": [],
                "errors": [],
            }
        )
        overview = decode_storage_overview(
            {
                "total_size": 10,
                "reachable_size": 8,
                "historical_retained_size": 1,
                "reclaimable_gc_size": 1,
                "reclaimable_cache_size": 0,
                "reclaimable_temporary_size": 0,
                "sections": [
                    {
                        "name": "cache",
                        "path": "cache/",
                        "total_size": 1,
                        "file_count": 1,
                        "reclaimable_size": 1,
                        "reclaim_strategy": "prune-cache",
                        "notes": "Detached cache files.",
                    }
                ],
                "recommendations": ["Run gc()."],
            }
        )
        gc_report = decode_gc_report(
            {
                "dry_run": True,
                "checked_refs": ["refs/heads/main"],
                "reclaimed_size": 10,
                "reclaimed_object_size": 4,
                "reclaimed_chunk_size": 3,
                "reclaimed_cache_size": 2,
                "reclaimed_temporary_size": 1,
                "removed_file_count": 2,
                "notes": ["dry-run"],
            }
        )
        squash = decode_squash_report(
            {
                "ref_name": "refs/heads/main",
                "old_head": "old",
                "new_head": "new",
                "root_commit_before": "root",
                "rewritten_commit_count": 2,
                "dropped_ancestor_count": 1,
                "blocking_refs": [],
                "gc_report": None,
            }
        )

        assert commit.oid == "abc"
        assert merge.conflicts[0].conflict_type == "modify/modify"
        assert verify.ok is True
        assert overview.sections[0].name == "cache"
        assert gc_report.reclaimed_chunk_size == 3
        assert squash.new_head == "new"
