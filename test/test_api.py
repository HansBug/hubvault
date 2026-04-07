import io
from hashlib import sha1, sha256
from pathlib import Path

import pytest

from hubvault import (
    CommitOperationAdd,
    ConflictError,
    EntryNotFoundError,
    HubVaultApi,
    RepoFile,
    RepoFolder,
    RepoInfo,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
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

        created = api.create_repo(default_branch="release/v1")
        assert isinstance(created, RepoInfo)
        assert created.default_branch == "release/v1"
        assert created.head is None
        assert created.refs == ["refs/heads/release/v1"]

        with pytest.raises(RepositoryAlreadyExistsError):
            api.create_repo(default_branch="release/v1")

        reused = api.create_repo(default_branch="release/v1", exist_ok=True)
        assert reused.repo_path == str(repo_dir)

        source_file = tmp_path / "weights.bin"
        source_file.write_bytes(b"weights-v1")
        stream = io.BytesIO(b'{"layers": 3}\n')
        model_bytes = b"tensor-content-v1"

        commit = api.create_commit(
            operations=[
                CommitOperationAdd("models/core/model.safetensors", model_bytes),
                CommitOperationAdd("artifacts/weights.bin", str(source_file)),
                CommitOperationAdd("configs/model.json", stream),
            ],
            commit_message="add api assets",
            revision="release/v1",
        )

        info = api.repo_info()
        assert info.head == commit.oid
        assert commit.oid.startswith("sha256:")
        assert commit.commit_message == "add api assets"
        assert commit.commit_description == ""
        assert commit.repo_url.startswith("file:")
        assert "#commit=" in commit.commit_url
        commit_history = api.list_repo_commits()
        assert len(commit_history) == 1
        assert commit_history[0].commit_id == commit.oid
        assert commit_history[0].title == "add api assets"
        assert commit_history[0].message == ""
        assert commit_history[0].formatted_title is None
        assert commit_history[0].formatted_message is None
        assert api.list_repo_files() == [
            "artifacts/weights.bin",
            "configs/model.json",
            "models/core/model.safetensors",
        ]

        root_items = {item.path: item for item in api.list_repo_tree()}
        assert sorted(root_items) == ["artifacts", "configs", "models"]
        assert isinstance(root_items["models"], RepoFolder)
        assert root_items["models"].tree_id.startswith("sha256:")

        nested_items = api.list_repo_tree("models/core")
        assert len(nested_items) == 1
        assert isinstance(nested_items[0], RepoFile)
        assert nested_items[0].path == "models/core/model.safetensors"
        assert nested_items[0].oid == _git_blob_oid(model_bytes)
        assert nested_items[0].blob_id == _git_blob_oid(model_bytes)
        assert nested_items[0].sha256 == _sha256_value(model_bytes)
        assert nested_items[0].etag == _git_blob_oid(model_bytes)
        assert nested_items[0].lfs is None

        recursive_tree = api.list_repo_tree("models", recursive=True)
        assert [item.path for item in recursive_tree] == [
            "models/core",
            "models/core/model.safetensors",
        ]

        path_items = api.get_paths_info(["models", "models/core/model.safetensors"])
        assert [type(item).__name__ for item in path_items] == ["RepoFolder", "RepoFile"]
        assert isinstance(path_items[0], RepoFolder)
        assert isinstance(path_items[1], RepoFile)
        assert path_items[1].sha256 == _sha256_value(model_bytes)
        assert api.get_paths_info("models/core/model.safetensors")[0].blob_id == _git_blob_oid(model_bytes)
        assert api.get_paths_info(["missing.txt"]) == []
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
        with pytest.raises(RepositoryNotFoundError):
            missing_api.repo_info()
        with pytest.raises(RepositoryNotFoundError):
            missing_api.quick_verify()

        invalid_branch_api = HubVaultApi(tmp_path / "invalid-branch-repo")
        with pytest.raises(UnsupportedPathError):
            invalid_branch_api.create_repo(default_branch="../bad")

        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        assert api.list_repo_commits() == []
        first_commit = api.create_commit(
            operations=[CommitOperationAdd("data/file.txt", b"v1")],
            commit_message="seed",
        )

        formatted_history = api.list_repo_commits(formatted=True)
        assert len(formatted_history) == 1
        assert formatted_history[0].title == "seed"
        assert formatted_history[0].formatted_title == "seed"
        assert formatted_history[0].formatted_message == ""

        with pytest.raises(ConflictError):
            api.create_commit(operations=[], commit_message="noop")

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[CommitOperationAdd("data/file.txt", b"v2")],
                parent_commit="sha256:not-the-head",
                commit_message="stale parent",
            )

        with pytest.raises(ValueError):
            api.create_commit(
                operations=[CommitOperationAdd("data/file.txt", b"v2")],
                commit_message="",
            )

        assert api.get_paths_info(["missing.txt"]) == []

        with pytest.raises(EntryNotFoundError):
            api.read_bytes("missing.txt")

        with pytest.raises(EntryNotFoundError):
            api.open_file("missing.txt")

        with pytest.raises(EntryNotFoundError):
            api.hf_hub_download("missing.txt")

        with pytest.raises(EntryNotFoundError):
            api.list_repo_tree("missing-dir")

        with pytest.raises(UnsupportedPathError):
            api.create_commit(
                operations=[CommitOperationAdd("../bad.txt", b"x")],
                parent_commit=first_commit.oid,
                commit_message="bad path",
            )

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[object()],
                parent_commit=first_commit.oid,
                commit_message="unsupported operation",
            )

        with pytest.raises(UnsupportedPathError):
            api.list_repo_tree("data/file.txt")

        with pytest.raises(RevisionNotFoundError):
            api.create_commit(
                revision="feature/missing",
                operations=[CommitOperationAdd("new.txt", b"x")],
                commit_message="missing branch",
            )

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files(revision="missing")

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_commits(revision="missing")

    def test_create_commit_defaults_to_current_head_when_parent_is_omitted(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        first_commit = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"v1")],
            commit_message="seed",
        )

        second_commit = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"v2")],
            commit_message="advance without explicit parent",
        )

        assert api.repo_info().head == second_commit.oid
        assert api.read_bytes("notes.txt") == b"v2"

    def test_list_repo_commits_supports_hf_style_formatted_fields(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        commit = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"v1")],
            commit_message="document <api>\n\nbody & tail",
        )

        plain_history = api.list_repo_commits()
        assert len(plain_history) == 1
        assert plain_history[0].commit_id == commit.oid
        assert plain_history[0].title == "document <api>"
        assert plain_history[0].message == "body & tail"
        assert plain_history[0].formatted_title is None
        assert plain_history[0].formatted_message is None

        formatted_history = api.list_repo_commits(formatted=True)
        assert len(formatted_history) == 1
        assert formatted_history[0].title == "document <api>"
        assert formatted_history[0].message == "body & tail"
        assert formatted_history[0].formatted_title == "document &lt;api&gt;"
        assert formatted_history[0].formatted_message == "body &amp; tail"
        assert commit.commit_message == "document <api>"
        assert commit.commit_description == "body & tail"
