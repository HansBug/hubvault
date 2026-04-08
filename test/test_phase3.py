"""
Phase 3 end-to-end workflow tests for :mod:`hubvault`.

This module simulates a realistic large-artifact workflow built on the Phase 3
public surface: chunked storage, HF-style LFS metadata, byte-range reads,
detached downloads, large-folder uploads, snapshot exports, commit history, and
repository portability after moving the repo directory.
"""

import shutil
from hashlib import sha1, sha256
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, HubVaultApi, RepoFile
from hubvault.storage.chunk import DEFAULT_CHUNK_SIZE, canonical_lfs_pointer, git_blob_oid as lfs_pointer_oid


def _git_blob_oid(data):
    header = ("blob %d\0" % len(data)).encode("utf-8")
    return sha1(header + data).hexdigest()


def _sha256_value(data):
    return sha256(data).hexdigest()


def _assert_repo_file_info(api, path, payload, *, expect_lfs):
    info = api.get_paths_info(path)[0]
    assert isinstance(info, RepoFile)
    assert info.path == path
    assert info.size == len(payload)
    assert info.sha256 == _sha256_value(payload)

    if expect_lfs:
        expected_oid = lfs_pointer_oid(canonical_lfs_pointer(_sha256_value(payload), len(payload)))
        assert info.blob_id == expected_oid
        assert info.oid == expected_oid
        assert info.etag == _sha256_value(payload)
        assert info.lfs is not None
        assert info.lfs.size == len(payload)
        assert info.lfs.sha256 == _sha256_value(payload)
        assert info.lfs.pointer_size == len(canonical_lfs_pointer(_sha256_value(payload), len(payload)))
        return

    assert info.blob_id == _git_blob_oid(payload)
    assert info.oid == _git_blob_oid(payload)
    assert info.etag == _git_blob_oid(payload)
    assert info.lfs is None


@pytest.mark.unittest
class TestPhase3IntegratedLifecycle:
    """
    Exercise the Phase 3 public workflow as a realistic large-artifact process.

    The covered scenario initializes a repository with an aggressive chunking
    threshold, seeds one normal file and one multi-chunk large artifact,
    validates HF-style file metadata and byte-range reads, uploads a follow-up
    folder through the large-folder helper, validates commit history and
    detached downloads, exports a snapshot, and reopens the moved repository to
    prove that chunk packs and manifests remain portable.
    """

    def test_phase3_chunked_storage_workflow_from_init_to_reopen(self, tmp_path):
        """
        Simulate a realistic Phase 3 workflow from initialization to reopen.

        The simulated user story is:

        1. Initialize a local repository with a small public large-file threshold.
        2. Create one seed commit that contains a normal config file and a
           multi-chunk model artifact.
        3. Inspect HF-style file metadata and read a narrow byte range from the
           model artifact.
        4. Download the model through a detached file view and upload a
           follow-up release folder through the Phase 3 large-folder helper.
        5. Export a detached snapshot, inspect commit history and on-disk chunk
           layout, and verify the repository.
        6. Move the repository directory and reopen it without losing
           correctness.
        """

        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir)

        created = api.create_repo(large_file_threshold=64)
        assert created.default_branch == "main"
        assert created.head is None

        config_payload = b'{"model":"phase3","dtype":"fp16"}\n'
        large_payload = (b"A" * DEFAULT_CHUNK_SIZE) + (b"B" * 512)

        seed_commit = api.create_commit(
            operations=[
                CommitOperationAdd("configs/model.json", config_payload),
                CommitOperationAdd("artifacts/model.safetensors", large_payload),
            ],
            commit_message="seed phase3 assets",
        )

        assert seed_commit.commit_message == "seed phase3 assets"
        _assert_repo_file_info(api, "configs/model.json", config_payload, expect_lfs=False)
        _assert_repo_file_info(api, "artifacts/model.safetensors", large_payload, expect_lfs=True)

        expected_slice = large_payload[DEFAULT_CHUNK_SIZE - 16:DEFAULT_CHUNK_SIZE + 32]
        assert api.read_range(
            "artifacts/model.safetensors",
            start=DEFAULT_CHUNK_SIZE - 16,
            length=48,
        ) == expected_slice

        detached_model = Path(api.hf_hub_download("artifacts/model.safetensors"))
        assert detached_model.as_posix().endswith("artifacts/model.safetensors")
        assert detached_model.read_bytes() == large_payload

        release_dir = tmp_path / "release-folder"
        (release_dir / "release").mkdir(parents=True)
        (release_dir / "release" / "notes.txt").write_bytes(b"phase3 release notes\n")
        (release_dir / "release" / "embeddings.bin").write_bytes(b"E" * 128)
        (release_dir / ".git").mkdir()
        (release_dir / ".git" / "ignored.txt").write_bytes(b"ignored\n")

        folder_commit = api.upload_large_folder(
            folder_path=release_dir,
            allow_patterns=["release/*"],
        )
        assert folder_commit.commit_message == "Upload large folder using hubvault"

        _assert_repo_file_info(api, "release/notes.txt", b"phase3 release notes\n", expect_lfs=False)
        _assert_repo_file_info(api, "release/embeddings.bin", b"E" * 128, expect_lfs=True)

        assert api.list_repo_files() == [
            "artifacts/model.safetensors",
            "configs/model.json",
            "release/embeddings.bin",
            "release/notes.txt",
        ]
        assert [item.title for item in api.list_repo_commits()] == [
            "Upload large folder using hubvault",
            "seed phase3 assets",
        ]

        snapshot_dir = Path(api.snapshot_download())
        assert (snapshot_dir / "artifacts" / "model.safetensors").read_bytes() == large_payload
        assert (snapshot_dir / "release" / "notes.txt").read_bytes() == b"phase3 release notes\n"

        manifest_path = repo_dir / "chunks" / "index" / "MANIFEST"
        pack_files = sorted((repo_dir / "chunks" / "packs").glob("*.pack"))
        assert manifest_path.is_file()
        assert len(pack_files) >= 2
        assert api.quick_verify().ok is True

        moved_repo_dir = tmp_path / "moved-portable-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        _assert_repo_file_info(reopened_api, "artifacts/model.safetensors", large_payload, expect_lfs=True)
        assert reopened_api.read_range(
            "artifacts/model.safetensors",
            start=DEFAULT_CHUNK_SIZE - 16,
            length=48,
        ) == expected_slice
        assert reopened_api.read_bytes("release/notes.txt") == b"phase3 release notes\n"
        assert reopened_api.quick_verify().ok is True
