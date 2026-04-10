from datetime import datetime

import pytest

from hubvault.errors import EntryNotFoundError
from hubvault.remote.errors import HubVaultRemoteAuthError, HubVaultRemoteProtocolError
from hubvault.remote.serde import (
    decode_error_response,
    decode_git_refs,
    decode_repo_entries,
    decode_snapshot_plan,
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
                    "lfs": None,
                    "last_commit": {
                        "oid": "commit-1",
                        "title": "seed",
                        "date": datetime(2026, 4, 11, 10, 0, 0).isoformat(),
                    },
                    "security": None,
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

