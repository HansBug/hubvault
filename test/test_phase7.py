"""
Phase 7 real-baseline comparison tests for :mod:`hubvault`.

This module validates the public ID and metadata semantics introduced for Phase
7 against real baseline tooling. The default suite stays fully offline by
comparing :mod:`hubvault` with local ``git`` behavior and Git-LFS pointer
rules, while an optional live Hugging Face smoke test can be enabled through
an environment variable when network access is available.
"""

import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, HubVaultApi, RepoFile, RepoFolder


def _is_git_oid(value):
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdef" for ch in value)


def _git(cwd, *args, input_bytes=None, env=None):
    completed = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        input=input_bytes,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.decode("utf-8").strip()


def _git_commit_env(created_at):
    timestamp = int(created_at.timestamp())
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "HubVault",
            "GIT_AUTHOR_EMAIL": "hubvault@local",
            "GIT_AUTHOR_DATE": "%d +0000" % timestamp,
            "GIT_COMMITTER_NAME": "HubVault",
            "GIT_COMMITTER_EMAIL": "hubvault@local",
            "GIT_COMMITTER_DATE": "%d +0000" % timestamp,
        }
    )
    return env


def _replace_git_worktree(root, files):
    for current in root.iterdir():
        if current.name == ".git":
            continue
        if current.is_dir():
            shutil.rmtree(str(current))
        else:
            current.unlink()
    for relative_path, data in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _git_commit_tree(cwd, tree_oid, created_at, message, parents=()):
    command = ["commit-tree", tree_oid]
    for parent in parents:
        command.extend(["-p", parent])
    raw_message = message if message.endswith("\n") else message + "\n"
    return _git(cwd, *command, env=_git_commit_env(created_at), input_bytes=raw_message.encode("utf-8"))


def _canonical_lfs_pointer(file_sha256, size):
    return (
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:%s\n"
        "size %d\n"
    ) % (file_sha256, size)


@pytest.mark.unittest
class TestPhase7RealBaselines:
    """
    Validate Phase 7 public compatibility against real external baselines.

    The covered scenarios compare :mod:`hubvault` public IDs against local
    ``git`` object IDs for ordinary file history, compare chunked large-file
    metadata against canonical Git-LFS pointer rules, and optionally run a live
    Hugging Face smoke test when explicitly enabled.
    """

    def test_phase7_git_baseline_aligns_commit_tree_and_blob_oids_for_small_files(self, tmp_path):
        """
        Compare the public small-file history surface with real ``git`` objects.

        The simulated workflow builds the same two-commit small-file history in
        both :mod:`hubvault` and a temporary git repository, then verifies that
        the initial commit OID, subsequent commit OIDs, directory tree OIDs,
        and file blob OIDs all match the real git results exactly.
        """

        repo_dir = tmp_path / "hubvault-repo"
        api = HubVaultApi(repo_dir)
        created = api.create_repo(large_file_threshold=10_000)

        first_files = {
            "artifacts/model.bin": b"model-v1\n",
            "notes/readme.txt": b"phase7 readme v1\n",
        }
        second_files = {
            "artifacts/model.bin": b"model-v2\n",
            "notes/readme.txt": b"phase7 readme v2\n",
            "configs/config.json": b'{"dtype":"float16","layers":12}\n',
        }

        first_commit = api.create_commit(
            operations=[CommitOperationAdd(path, data) for path, data in sorted(first_files.items())],
            commit_message="phase7 seed",
        )
        second_commit = api.create_commit(
            operations=[CommitOperationAdd(path, data) for path, data in sorted(second_files.items())],
            commit_message="phase7 update\n\nbody line",
        )

        history = api.list_repo_commits()
        assert [item.commit_id for item in history] == [second_commit.oid, first_commit.oid, created.head]
        assert all(_is_git_oid(item.commit_id) for item in history)
        assert _is_git_oid(api.repo_info().head)

        git_dir = tmp_path / "git-baseline"
        git_dir.mkdir()
        _git(git_dir, "init", "-q")

        initial_created_at = history[2].created_at
        first_created_at = history[1].created_at
        second_created_at = history[0].created_at

        empty_tree_oid = _git(git_dir, "write-tree")
        expected_initial_commit = _git_commit_tree(git_dir, empty_tree_oid, initial_created_at, "Initial commit")

        _replace_git_worktree(git_dir, first_files)
        _git(git_dir, "add", "-A")
        expected_first_tree = _git(git_dir, "write-tree")
        expected_first_commit = _git_commit_tree(
            git_dir,
            expected_first_tree,
            first_created_at,
            "phase7 seed",
            parents=[expected_initial_commit],
        )

        _replace_git_worktree(git_dir, second_files)
        _git(git_dir, "add", "-A")
        expected_second_tree = _git(git_dir, "write-tree")
        expected_second_commit = _git_commit_tree(
            git_dir,
            expected_second_tree,
            second_created_at,
            "phase7 update\n\nbody line",
            parents=[expected_first_commit],
        )

        assert created.head == expected_initial_commit
        assert first_commit.oid == expected_first_commit
        assert second_commit.oid == expected_second_commit

        path_infos = api.get_paths_info(["artifacts", "artifacts/model.bin", "notes", "configs"])
        by_path = {item.path: item for item in path_infos}

        assert isinstance(by_path["artifacts"], RepoFolder)
        assert isinstance(by_path["notes"], RepoFolder)
        assert isinstance(by_path["configs"], RepoFolder)
        assert isinstance(by_path["artifacts/model.bin"], RepoFile)

        assert by_path["artifacts"].tree_id == _git(git_dir, "rev-parse", expected_second_commit + ":artifacts")
        assert by_path["notes"].tree_id == _git(git_dir, "rev-parse", expected_second_commit + ":notes")
        assert by_path["configs"].tree_id == _git(git_dir, "rev-parse", expected_second_commit + ":configs")
        assert by_path["artifacts/model.bin"].blob_id == _git(git_dir, "rev-parse", expected_second_commit + ":artifacts/model.bin")
        assert by_path["artifacts/model.bin"].oid == by_path["artifacts/model.bin"].blob_id

    def test_phase7_git_lfs_baseline_aligns_chunked_metadata_and_download_views(self, tmp_path):
        """
        Compare chunked large-file metadata with real Git-LFS pointer semantics.

        The simulated workflow commits one small file and one threshold-crossing
        large file, then verifies that only the large file becomes chunked, its
        public blob OID matches the git hash of the canonical LFS pointer, its
        SHA-256 stays bare hex, and detached download/snapshot outputs preserve
        the repo-relative path suffix while exposing a public commit ID in
        snapshot metadata.
        """

        repo_dir = tmp_path / "hubvault-repo"
        api = HubVaultApi(repo_dir)
        api.create_repo(large_file_threshold=64)

        small_payload = b"tiny\n"
        large_payload = (b"A" * 96) + (b"B" * 48)
        large_sha256 = sha256(large_payload).hexdigest()
        large_pointer = _canonical_lfs_pointer(large_sha256, len(large_payload)).encode("utf-8")

        commit = api.create_commit(
            operations=[
                CommitOperationAdd("notes/small.txt", small_payload),
                CommitOperationAdd("models/big/model.safetensors", large_payload),
            ],
            commit_message="phase7 chunked baseline",
        )

        infos = api.get_paths_info(["notes/small.txt", "models/big/model.safetensors"])
        by_path = {item.path: item for item in infos}
        small_info = by_path["notes/small.txt"]
        large_info = by_path["models/big/model.safetensors"]

        assert isinstance(small_info, RepoFile)
        assert isinstance(large_info, RepoFile)
        assert small_info.lfs is None
        assert large_info.lfs is not None
        assert large_info.size == len(large_payload)
        assert large_info.sha256 == large_sha256
        assert large_info.lfs.sha256 == large_sha256
        assert large_info.blob_id == _git(tmp_path, "hash-object", "--stdin", input_bytes=large_pointer)
        assert large_info.oid == large_info.blob_id

        download_path = Path(api.hf_hub_download("models/big/model.safetensors"))
        assert download_path.as_posix().endswith("models/big/model.safetensors")
        assert download_path.read_bytes() == large_payload

        export_dir = tmp_path / "snapshot-export"
        snapshot_root = Path(api.snapshot_download(local_dir=export_dir))
        metadata = json.loads((snapshot_root / ".cache" / "hubvault" / "snapshot.json").read_text(encoding="utf-8"))

        assert snapshot_root == export_dir.resolve()
        assert snapshot_root.joinpath("models", "big", "model.safetensors").read_bytes() == large_payload
        assert metadata["commit_id"] == commit.oid
        assert _is_git_oid(metadata["commit_id"])

    @pytest.mark.skipif(os.environ.get("HUBVAULT_LIVE_HF") != "1", reason="set HUBVAULT_LIVE_HF=1 to enable live HF smoke checks")
    def test_phase7_optional_live_hf_baseline_matches_documented_public_formats(self):
        """
        Smoke-test the documented HF baseline against a real public repository.

        This optional check uses the installed :mod:`huggingface_hub` package
        and a public repository to confirm the live field formats that Phase 7
        aligns with: 40-hex commit/tree/blob IDs, bare SHA-256 strings for LFS
        metadata, and snapshot-style download paths ending in ``snapshots`` and
        the resolved commit ID.
        """

        huggingface_hub = pytest.importorskip("huggingface_hub")

        api = huggingface_hub.HfApi()
        commit = api.list_repo_commits("gpt2", formatted=True)[0]
        refs = api.list_repo_refs("gpt2")
        paths = api.get_paths_info("gpt2", ["config.json"])
        download_path = Path(huggingface_hub.hf_hub_download("gpt2", "config.json"))

        assert _is_git_oid(commit.commit_id)
        assert _is_git_oid(refs.branches[0].target_commit)
        assert _is_git_oid(paths[0].blob_id)
        assert download_path.parts[-3] == "snapshots"
        assert _is_git_oid(download_path.parts[-2])
        assert download_path.parts[-1] == "config.json"
