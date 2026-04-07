import io
import shutil
from hashlib import sha1, sha256
from pathlib import Path

import pytest

from hubvault import (
    BlobLfsInfo,
    CommitInfo,
    CommitOperationAdd,
    CommitOperationCopy,
    CommitOperationDelete,
    ConflictError,
    HubVaultApi,
    HubVaultError,
    IntegrityError,
    PathInfo,
    PathNotFoundError,
    RepoAlreadyExistsError,
    RepoInfo,
    RepoNotFoundError,
    RevisionNotFoundError,
    UnsupportedPathError,
    VerificationError,
    VerifyReport,
)


def _git_blob_oid(data):
    header = ("blob %d\0" % len(data)).encode("utf-8")
    return sha1(header + data).hexdigest()


def _sha256_value(data):
    return "sha256:" + sha256(data).hexdigest()


@pytest.mark.unittest
class TestHubVaultApiMvp:
    def test_public_exports_and_repo_creation_support_nested_default_branch(self, tmp_path):
        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir, revision="release/v1")

        info = api.create_repo(default_branch="release/v1", metadata={"owner": "tester"})

        assert isinstance(info, RepoInfo)
        assert info.repo_path == str(repo_dir)
        assert info.format_version == 1
        assert info.default_branch == "release/v1"
        assert info.head is None
        assert info.refs == ["refs/heads/release/v1"]

        assert (repo_dir / "FORMAT").is_file()
        assert (repo_dir / "repo.json").is_file()
        assert (repo_dir / "refs" / "heads" / "release" / "v1").is_file()
        assert (repo_dir / "logs" / "refs" / "heads").is_dir()
        assert (repo_dir / "objects" / "commits" / "sha256").is_dir()
        assert (repo_dir / "objects" / "blobs" / "sha256").is_dir()
        assert (repo_dir / "txn").is_dir()
        assert (repo_dir / "locks").is_dir()
        assert (repo_dir / "cache" / "files").is_dir()
        assert (repo_dir / "cache" / "materialized" / "sha256").is_dir()
        assert (repo_dir / "quarantine" / "objects").is_dir()

        assert isinstance(BlobLfsInfo(size=4, sha256="sha256:test", pointer_size=12), BlobLfsInfo)
        assert isinstance(CommitInfo(commit_id="c", revision="main", tree_id="t"), CommitInfo)
        assert isinstance(PathInfo(path="a", path_type="file", size=1, oid="o", blob_id="b", sha256="s", etag="e"), PathInfo)
        assert isinstance(VerifyReport(ok=True), VerifyReport)
        assert issubclass(ConflictError, HubVaultError)
        assert issubclass(IntegrityError, HubVaultError)
        assert issubclass(RepoAlreadyExistsError, HubVaultError)
        assert issubclass(RepoNotFoundError, HubVaultError)
        assert issubclass(RevisionNotFoundError, HubVaultError)
        assert issubclass(UnsupportedPathError, HubVaultError)
        assert issubclass(VerificationError, HubVaultError)

        with pytest.raises(RepoAlreadyExistsError):
            api.create_repo(default_branch="release/v1")

        reused = api.create_repo(default_branch="release/v1", exist_ok=True)
        assert reused.refs == ["refs/heads/release/v1"]

    def test_create_commit_read_download_and_verify_public_behavior(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        source_file = tmp_path / "weights.bin"
        source_file.write_bytes(b"weights-v1")
        stream = io.BytesIO(b'{"layers": 3}\n')
        model_bytes = b"tensor-content-v1"

        commit = api.create_commit(
            operations=[
                CommitOperationAdd.from_bytes("models/core/model.safetensors", model_bytes),
                CommitOperationAdd.from_file("artifacts/weights.bin", str(source_file)),
                CommitOperationAdd.from_fileobj("configs/model.json", stream),
            ],
            commit_message="add mvp assets",
            metadata={"stage": "mvp"},
        )

        assert isinstance(commit, CommitInfo)
        assert commit.revision == "main"
        assert commit.parents == []
        assert commit.message == "add mvp assets"
        assert commit.commit_id.startswith("sha256:")
        assert commit.tree_id.startswith("sha256:")

        info = api.repo_info()
        assert info.head == commit.commit_id
        assert info.refs == ["refs/heads/main"]

        assert api.list_repo_files() == [
            "artifacts/weights.bin",
            "configs/model.json",
            "models/core/model.safetensors",
        ]

        root_items = {item.path: item for item in api.list_repo_tree()}
        assert sorted(root_items) == ["artifacts", "configs", "models"]
        assert root_items["models"].path_type == "directory"

        nested_items = api.list_repo_tree("models")
        assert [(item.path, item.path_type) for item in nested_items] == [("models/core", "directory")]

        file_item = api.list_repo_tree("models/core")[0]
        assert file_item.path == "models/core/model.safetensors"
        assert file_item.path_type == "file"
        assert file_item.size == len(model_bytes)
        assert file_item.oid == _git_blob_oid(model_bytes)
        assert file_item.blob_id == _git_blob_oid(model_bytes)
        assert file_item.sha256 == _sha256_value(model_bytes)
        assert file_item.etag == _git_blob_oid(model_bytes)

        info_items = api.get_paths_info(["models", "models/core/model.safetensors"])
        assert [item.path_type for item in info_items] == ["directory", "file"]
        assert info_items[1] == file_item

        assert api.read_bytes("models/core/model.safetensors") == model_bytes
        with api.open_file("models/core/model.safetensors") as file_obj:
            assert file_obj.read() == model_bytes
            assert file_obj.writable() is False
            with pytest.raises(io.UnsupportedOperation):
                file_obj.write(b"mutated")

        download_path = Path(api.hf_hub_download("demo", "models/core/model.safetensors"))
        assert download_path.is_file()
        assert download_path.as_posix().endswith("models/core/model.safetensors")
        assert download_path.read_bytes() == model_bytes

        download_path.write_bytes(b"tampered")
        report = api.quick_verify()
        assert report.ok is True
        assert report.errors == []
        assert any("stale file view" in warning for warning in report.warnings)
        assert api.read_bytes("models/core/model.safetensors") == model_bytes

        restored_path = Path(api.hf_hub_download("demo", "models/core/model.safetensors"))
        assert restored_path == download_path
        assert restored_path.read_bytes() == model_bytes

        restored_path.unlink()
        rebuilt_path = Path(api.hf_hub_download("demo", "models/core/model.safetensors"))
        assert rebuilt_path == download_path
        assert rebuilt_path.read_bytes() == model_bytes

        local_dir = tmp_path / "exports"
        external_path = Path(
            api.hf_hub_download(
                "demo",
                "models/core/model.safetensors",
                local_dir=local_dir,
            )
        )
        assert external_path == local_dir / "models" / "core" / "model.safetensors"
        assert external_path.read_bytes() == model_bytes

    def test_copy_delete_reset_and_repo_move_keep_public_behavior(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        first_commit = api.create_commit(
            operations=[
                CommitOperationAdd.from_bytes("src/a.txt", b"A"),
                CommitOperationAdd.from_bytes("src/sub/b.txt", b"B"),
            ],
            commit_message="seed repo",
        )

        second_commit = api.create_commit(
            operations=[
                CommitOperationCopy("src", "mirror"),
                CommitOperationDelete("src/sub"),
            ],
            parent_commit=first_commit.commit_id,
            commit_message="copy and prune",
        )

        assert second_commit.parents == [first_commit.commit_id]
        assert api.list_repo_files() == [
            "mirror/a.txt",
            "mirror/sub/b.txt",
            "src/a.txt",
        ]

        reset = api.reset_ref("main", first_commit.commit_id)
        assert reset.commit_id == first_commit.commit_id
        assert api.list_repo_files() == ["src/a.txt", "src/sub/b.txt"]
        assert api.read_bytes("src/sub/b.txt") == b"B"
        assert api.quick_verify().ok is True

        moved_repo_dir = tmp_path / "moved-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))

        moved_api = HubVaultApi(moved_repo_dir)
        moved_info = moved_api.repo_info()
        assert moved_info.repo_path == str(moved_repo_dir)
        assert moved_info.head == first_commit.commit_id
        assert moved_api.list_repo_files() == ["src/a.txt", "src/sub/b.txt"]
        assert moved_api.read_bytes("src/a.txt") == b"A"
        assert moved_api.quick_verify().ok is True

        moved_download = Path(moved_api.hf_hub_download("demo", "src/sub/b.txt"))
        assert moved_download.is_file()
        assert moved_download.as_posix().endswith("src/sub/b.txt")
        assert moved_download.read_bytes() == b"B"

    def test_public_errors_and_conflicts(self, tmp_path):
        missing_api = HubVaultApi(tmp_path / "missing-repo")
        with pytest.raises(RepoNotFoundError):
            missing_api.repo_info()

        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        with pytest.raises(ConflictError):
            api.create_commit(operations=[], commit_message="noop")

        first_commit = api.create_commit(
            operations=[CommitOperationAdd.from_bytes("data/file.txt", b"v1")],
            commit_message="seed",
        )

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[CommitOperationAdd.from_bytes("data/file.txt", b"v2")],
                parent_commit="sha256:not-the-head",
                commit_message="stale parent",
            )

        with pytest.raises(PathNotFoundError):
            api.get_paths_info(["missing.txt"])

        with pytest.raises(PathNotFoundError):
            api.read_bytes("missing.txt")

        with pytest.raises(PathNotFoundError):
            api.create_commit(
                operations=[CommitOperationDelete("missing.txt")],
                parent_commit=first_commit.commit_id,
                commit_message="missing delete",
            )

        with pytest.raises(UnsupportedPathError):
            api.create_commit(
                operations=[CommitOperationAdd.from_bytes("../bad.txt", b"x")],
                parent_commit=first_commit.commit_id,
                commit_message="bad path",
            )

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files(revision="missing")
