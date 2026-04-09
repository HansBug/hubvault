"""
Phase 10 end-to-end optimization tests for :mod:`hubvault`.

This module validates the public behavior added in Phase 10: FastCDC-backed
large-file chunking and write-time chunk reuse that avoids immediate duplicate
pack growth before any maintenance pass runs.
"""

from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, HubVaultApi, StorageOverview


def _section_size(overview: StorageOverview, name: str) -> int:
    for section in overview.sections:
        if section.name == name:
            return int(section.total_size)
    raise AssertionError("missing storage section: %s" % name)


@pytest.mark.unittest
class TestPhase10IntegratedOptimizationWorkflow:
    """
    Exercise the Phase 10 optimized chunk-storage workflow through public APIs.

    The covered scenario initializes a repository with chunked storage enabled,
    writes duplicate large files in one commit, writes the same large file
    again in a later commit, and confirms that pack usage stays close to one
    physical copy while public reads, downloads, and verification remain
    correct.
    """

    def test_phase10_fastcdc_and_write_time_reuse_keep_duplicate_large_files_compact(self, tmp_path):
        """
        Simulate a duplicate-heavy large-file workflow after Phase 10 changes.

        The simulated user story is:

        1. Initialize a repository with a small chunk threshold.
        2. Commit two repo paths that carry exactly the same large payload in
           one atomic commit.
        3. Confirm that public storage overview reports chunk-pack usage close
           to one physical payload copy rather than two immediate copies.
        4. Upload the same large payload again in a later commit and confirm
           that chunk-pack usage does not grow.
        5. Read and download the files through public APIs and verify the repo.
        """

        repo_dir = tmp_path / "phase10-repo"
        api = HubVaultApi(repo_dir)
        api.create_repo(large_file_threshold=64)

        payload = (
            (b"phase10-fastcdc-shared-block-0000\n" * 2048)
            + (b"phase10-fastcdc-shared-block-1111\n" * 2048)
            + (b"phase10-fastcdc-shared-block-2222\n" * 2048)
        )

        duplicate_commit = api.create_commit(
            operations=[
                CommitOperationAdd("artifacts/model-a.bin", payload),
                CommitOperationAdd("artifacts/model-b.bin", payload),
            ],
            commit_message="seed duplicate phase10 payloads",
        )

        assert duplicate_commit.commit_message == "seed duplicate phase10 payloads"
        overview_after_first = api.get_storage_overview()
        first_pack_bytes = _section_size(overview_after_first, "chunks.packs")
        assert first_pack_bytes >= len(payload)
        assert first_pack_bytes < len(payload) + 4096

        third_commit = api.create_commit(
            operations=[CommitOperationAdd("artifacts/model-c.bin", payload)],
            commit_message="reuse duplicate chunks",
        )
        assert third_commit.commit_message == "reuse duplicate chunks"

        overview_after_second = api.get_storage_overview()
        second_pack_bytes = _section_size(overview_after_second, "chunks.packs")
        assert second_pack_bytes == first_pack_bytes

        assert api.list_repo_files() == [
            "artifacts/model-a.bin",
            "artifacts/model-b.bin",
            "artifacts/model-c.bin",
        ]
        assert api.read_bytes("artifacts/model-a.bin") == payload
        assert api.read_bytes("artifacts/model-b.bin") == payload
        assert api.read_bytes("artifacts/model-c.bin") == payload
        assert Path(api.hf_hub_download("artifacts/model-c.bin")).read_bytes() == payload
        assert api.quick_verify().ok is True
        assert api.full_verify().ok is True
