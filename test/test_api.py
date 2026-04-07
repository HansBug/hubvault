import io
from hashlib import sha1, sha256
from pathlib import Path

import pytest

from hubvault import (
    CommitOperationAdd,
    ConflictError,
    HubVaultApi,
    PathNotFoundError,
    RepoAlreadyExistsError,
    RepoInfo,
    RepoNotFoundError,
    RevisionNotFoundError,
    UnsupportedPathError,
)


def _git_blob_oid(data):
    header = ("blob %d\0" % len(data)).encode("utf-8")
    return sha1(header + data).hexdigest()


def _sha256_value(data):
    return sha256(data).hexdigest()


@pytest.mark.unittest
class TestApi:
    def test_create_repo_commit_and_read_methods(self, tmp_path):
        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir, revision="release/v1")

        created = api.create_repo(default_branch="release/v1", metadata={"owner": "tester"})
        assert isinstance(created, RepoInfo)
        assert created.default_branch == "release/v1"
        assert created.head is None
        assert created.refs == ["refs/heads/release/v1"]

        with pytest.raises(RepoAlreadyExistsError):
            api.create_repo(default_branch="release/v1")

        reused = api.create_repo(default_branch="release/v1", exist_ok=True)
        assert reused.repo_path == str(repo_dir)

        source_file = tmp_path / "weights.bin"
        source_file.write_bytes(b"weights-v1")
        stream = io.BytesIO(b'{"layers": 3}\n')
        model_bytes = b"tensor-content-v1"

        commit = api.create_commit(
            revision="release/v1",
            operations=[
                CommitOperationAdd.from_bytes("models/core/model.safetensors", model_bytes),
                CommitOperationAdd.from_file("artifacts/weights.bin", str(source_file)),
                CommitOperationAdd.from_fileobj("configs/model.json", stream),
            ],
            commit_message="add api assets",
        )

        info = api.repo_info()
        assert info.head == commit.commit_id
        assert api.list_repo_files() == [
            "artifacts/weights.bin",
            "configs/model.json",
            "models/core/model.safetensors",
        ]

        root_items = {item.path: item for item in api.list_repo_tree()}
        assert sorted(root_items) == ["artifacts", "configs", "models"]
        assert root_items["models"].path_type == "directory"

        nested_items = api.list_repo_tree("models/core")
        assert len(nested_items) == 1
        assert nested_items[0].path == "models/core/model.safetensors"
        assert nested_items[0].oid == _git_blob_oid(model_bytes)
        assert nested_items[0].blob_id == _git_blob_oid(model_bytes)
        assert nested_items[0].sha256 == _sha256_value(model_bytes)
        assert nested_items[0].etag == _git_blob_oid(model_bytes)

        path_items = api.get_paths_info(["models", "models/core/model.safetensors"])
        assert [item.path_type for item in path_items] == ["directory", "file"]
        assert api.read_bytes("models/core/model.safetensors") == model_bytes

        with api.open_file("models/core/model.safetensors") as fileobj:
            assert fileobj.read() == model_bytes
            assert fileobj.writable() is False

        export_path = Path(
            api.hf_hub_download(
                "models/core/model.safetensors",
                local_dir=tmp_path / "exports",
            )
        )
        assert export_path == tmp_path / "exports" / "models" / "core" / "model.safetensors"
        assert export_path.read_bytes() == model_bytes

    def test_public_api_error_paths(self, tmp_path):
        missing_api = HubVaultApi(tmp_path / "missing-repo")
        with pytest.raises(RepoNotFoundError):
            missing_api.repo_info()

        invalid_branch_api = HubVaultApi(tmp_path / "invalid-branch-repo")
        with pytest.raises(UnsupportedPathError):
            invalid_branch_api.create_repo(default_branch="../bad")

        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        first_commit = api.create_commit(
            operations=[CommitOperationAdd.from_bytes("data/file.txt", b"v1")],
            commit_message="seed",
        )

        with pytest.raises(ConflictError):
            api.create_commit(operations=[], commit_message="noop")

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[CommitOperationAdd.from_bytes("data/file.txt", b"v2")],
                parent_commit="sha256:not-the-head",
                commit_message="stale parent",
            )

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[CommitOperationAdd.from_bytes("data/file.txt", b"v2")],
                parent_commit=first_commit.commit_id,
                expected_head="sha256:another",
                commit_message="mismatch",
            )

        with pytest.raises(PathNotFoundError):
            api.get_paths_info(["missing.txt"])

        with pytest.raises(PathNotFoundError):
            api.read_bytes("missing.txt")

        with pytest.raises(PathNotFoundError):
            api.open_file("missing.txt")

        with pytest.raises(PathNotFoundError):
            api.hf_hub_download("missing.txt")

        with pytest.raises(PathNotFoundError):
            api.list_repo_tree("missing-dir")

        with pytest.raises(UnsupportedPathError):
            api.create_commit(
                operations=[CommitOperationAdd.from_bytes("../bad.txt", b"x")],
                parent_commit=first_commit.commit_id,
                commit_message="bad path",
            )

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[object()],
                parent_commit=first_commit.commit_id,
                commit_message="unsupported operation",
            )

        with pytest.raises(UnsupportedPathError):
            api.list_repo_tree("data/file.txt")

        with pytest.raises(RevisionNotFoundError):
            api.create_commit(
                revision="feature/missing",
                operations=[CommitOperationAdd.from_bytes("new.txt", b"x")],
                commit_message="missing branch",
            )

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files(revision="missing")
