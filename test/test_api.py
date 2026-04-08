import io
import os
from hashlib import sha1, sha256
from pathlib import Path

import pytest

from hubvault import (
    CommitOperationAdd,
    CommitOperationDelete,
    ConflictError,
    EntryNotFoundError,
    GcReport,
    HubVaultApi,
    MergeConflict,
    MergeResult,
    RepoFile,
    RepoFolder,
    RepoInfo,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
    SquashReport,
    StorageOverview,
    UnsupportedPathError,
)
from hubvault.storage.chunk import canonical_lfs_pointer, git_blob_oid as lfs_pointer_oid


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
        assert created.head is not None
        assert created.refs == ["refs/heads/release/v1"]
        initial_commit_id = created.head

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
        assert len(commit_history) == 2
        assert commit_history[0].commit_id == commit.oid
        assert commit_history[0].title == "add api assets"
        assert commit_history[0].message == ""
        assert commit_history[0].formatted_title is None
        assert commit_history[0].formatted_message is None
        assert commit_history[1].commit_id == initial_commit_id
        assert commit_history[1].title == "Initial commit"
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
        assert [item.title for item in api.list_repo_commits()] == ["Initial commit"]
        first_commit = api.create_commit(
            operations=[CommitOperationAdd("data/file.txt", b"v1")],
            commit_message="seed",
        )

        formatted_history = api.list_repo_commits(formatted=True)
        assert len(formatted_history) == 2
        assert formatted_history[0].title == "seed"
        assert formatted_history[0].formatted_title == "seed"
        assert formatted_history[0].formatted_message == ""
        assert formatted_history[1].title == "Initial commit"

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
        assert len(plain_history) == 2
        assert plain_history[0].commit_id == commit.oid
        assert plain_history[0].title == "document <api>"
        assert plain_history[0].message == "body & tail"
        assert plain_history[0].formatted_title is None
        assert plain_history[0].formatted_message is None
        assert plain_history[1].title == "Initial commit"

        formatted_history = api.list_repo_commits(formatted=True)
        assert len(formatted_history) == 2
        assert formatted_history[0].title == "document <api>"
        assert formatted_history[0].message == "body & tail"
        assert formatted_history[0].formatted_title == "document &lt;api&gt;"
        assert formatted_history[0].formatted_message == "body &amp; tail"
        assert formatted_history[1].title == "Initial commit"
        assert commit.commit_message == "document <api>"
        assert commit.commit_description == "body & tail"

    def test_merge_public_api_supports_fast_forward_and_merge_commit_results(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo(large_file_threshold=64)

        seed_commit = api.create_commit(
            operations=[CommitOperationAdd("shared.txt", b"seed")],
            commit_message="seed main",
        )
        api.create_branch(branch="feature")
        feature_commit = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("feature.txt", b"feature-only")],
            commit_message="feature work",
        )

        fast_forward = api.merge("feature")
        assert isinstance(fast_forward, MergeResult)
        assert fast_forward.status == "fast-forward"
        assert fast_forward.fast_forward is True
        assert fast_forward.created_commit is False
        assert fast_forward.base_commit == seed_commit.oid
        assert fast_forward.target_head_before == seed_commit.oid
        assert fast_forward.source_head == feature_commit.oid
        assert fast_forward.head_after == feature_commit.oid
        assert fast_forward.commit is not None
        assert fast_forward.commit.oid == feature_commit.oid
        assert fast_forward.conflicts == []
        assert api.read_bytes("feature.txt") == b"feature-only"

        main_commit = api.create_commit(
            operations=[CommitOperationAdd("main.txt", b"main-only")],
            commit_message="main work",
        )
        release_payload = b"B" * 256
        feature_branch_commit = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("artifacts/model.bin", release_payload)],
            commit_message="feature release",
        )
        api.create_tag(tag="feature-ready", revision="feature")

        merge_commit = api.merge("feature-ready")
        assert merge_commit.status == "merged"
        assert merge_commit.fast_forward is False
        assert merge_commit.created_commit is True
        assert merge_commit.base_commit == feature_commit.oid
        assert merge_commit.target_head_before == main_commit.oid
        assert merge_commit.source_head == feature_branch_commit.oid
        assert merge_commit.head_after == merge_commit.commit.oid
        assert merge_commit.commit.commit_message == "Merge feature-ready into main"
        assert merge_commit.conflicts == []
        assert api.read_bytes("main.txt") == b"main-only"
        assert api.read_bytes("feature.txt") == b"feature-only"
        assert api.read_bytes("artifacts/model.bin") == release_payload

        history_ids = [item.commit_id for item in api.list_repo_commits()]
        assert history_ids[0] == merge_commit.commit.oid
        assert feature_branch_commit.oid in history_ids
        assert main_commit.oid in history_ids
        assert seed_commit.oid in history_ids

    def test_merge_public_api_returns_structured_conflicts_without_mutating_target(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        seed_commit = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"seed")],
            commit_message="seed",
        )
        api.create_branch(branch="feature")
        feature_commit = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("notes.txt", b"feature")],
            commit_message="feature edit",
        )
        main_commit = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"main")],
            commit_message="main edit",
        )

        conflict = api.merge("feature", parent_commit=main_commit.oid)
        assert isinstance(conflict, MergeResult)
        assert conflict.status == "conflict"
        assert conflict.fast_forward is False
        assert conflict.created_commit is False
        assert conflict.base_commit == seed_commit.oid
        assert conflict.target_head_before == main_commit.oid
        assert conflict.source_head == feature_commit.oid
        assert conflict.head_after == main_commit.oid
        assert conflict.commit is None
        assert len(conflict.conflicts) == 1
        assert isinstance(conflict.conflicts[0], MergeConflict)
        assert conflict.conflicts[0].path == "notes.txt"
        assert conflict.conflicts[0].conflict_type == "modify/modify"
        assert api.repo_info().head == main_commit.oid
        assert api.read_bytes("notes.txt") == b"main"

        with pytest.raises(ConflictError):
            api.merge("feature", parent_commit=seed_commit.oid)

    def test_merge_public_api_treats_equal_and_ancestor_source_heads_as_already_up_to_date(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        initial_head = api.repo_info().head
        api.create_branch(branch="feature")

        same_head_result = api.merge("feature")
        assert same_head_result.status == "already-up-to-date"
        assert same_head_result.base_commit == initial_head
        assert same_head_result.target_head_before == initial_head
        assert same_head_result.source_head == initial_head
        assert same_head_result.head_after == initial_head
        assert same_head_result.commit is not None
        assert same_head_result.commit.oid == initial_head

        main_commit = api.create_commit(
            operations=[CommitOperationAdd("main.txt", b"main")],
            commit_message="seed main",
        )

        result = api.merge("feature")

        assert result.status == "already-up-to-date"
        assert result.base_commit == initial_head
        assert result.target_head_before == main_commit.oid
        assert result.source_head == initial_head
        assert result.head_after == main_commit.oid
        assert result.commit is not None
        assert result.commit.oid == main_commit.oid
        assert result.conflicts == []
        assert api.repo_info().head == main_commit.oid

    def test_merge_public_api_fast_forwards_ancestor_target_branch_via_full_ref_name(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        initial_head = api.repo_info().head
        api.create_branch(branch="archive")
        source_commit = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"seed")],
            commit_message="seed main",
        )

        result = api.merge("main", target_revision="refs/heads/archive")

        assert result.status == "fast-forward"
        assert result.base_commit == initial_head
        assert result.target_revision == "archive"
        assert result.target_head_before == initial_head
        assert result.source_head == source_commit.oid
        assert result.head_after == source_commit.oid
        assert result.commit is not None
        assert result.commit.oid == source_commit.oid
        assert api.list_repo_files(revision="archive") == ["notes.txt"]

    def test_merge_public_api_handles_same_head_and_ancestor_source_without_new_commit(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        seed_commit = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"seed")],
            commit_message="seed",
        )
        api.create_branch(branch="feature")
        main_commit = api.create_commit(
            operations=[CommitOperationAdd("main.txt", b"main")],
            commit_message="main work",
        )

        same_head = api.merge("main")
        assert same_head.status == "already-up-to-date"
        assert same_head.base_commit == main_commit.oid
        assert same_head.target_head_before == main_commit.oid
        assert same_head.source_head == main_commit.oid
        assert same_head.head_after == main_commit.oid
        assert same_head.commit is not None
        assert same_head.commit.oid == main_commit.oid

        ancestor_source = api.merge("feature")
        assert ancestor_source.status == "already-up-to-date"
        assert ancestor_source.base_commit == seed_commit.oid
        assert ancestor_source.target_head_before == main_commit.oid
        assert ancestor_source.source_head == seed_commit.oid
        assert ancestor_source.head_after == main_commit.oid
        assert ancestor_source.commit is not None
        assert ancestor_source.commit.oid == main_commit.oid

    def test_merge_public_api_supports_explicit_message_and_description(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        _ = api.create_commit(
            operations=[CommitOperationAdd("shared.txt", b"base")],
            commit_message="seed",
        )
        api.create_branch(branch="feature")
        _ = api.create_commit(
            operations=[CommitOperationAdd("main.txt", b"main")],
            commit_message="main work",
        )
        _ = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("feature.txt", b"feature")],
            commit_message="feature work",
        )

        result = api.merge(
            "feature",
            commit_message="merge feature branch",
            commit_description="explicit merge body",
        )

        assert result.status == "merged"
        assert result.commit is not None
        assert result.commit.commit_message == "merge feature branch"
        assert result.commit.commit_description == "explicit merge body"
        history = api.list_repo_commits()
        assert history[0].title == "merge feature branch"
        assert history[0].message == "explicit merge body"

    def test_merge_public_api_reports_add_add_conflicts(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        _ = api.create_commit(
            operations=[CommitOperationAdd("seed.txt", b"seed")],
            commit_message="seed",
        )
        api.create_branch(branch="feature")
        _ = api.create_commit(
            operations=[CommitOperationAdd("shared.txt", b"main")],
            commit_message="main add",
        )
        _ = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("shared.txt", b"feature")],
            commit_message="feature add",
        )

        result = api.merge("feature")

        assert result.status == "conflict"
        assert result.commit is None
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == "add/add"
        assert result.conflicts[0].path == "shared.txt"

    def test_merge_public_api_reports_delete_modify_conflicts(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        _ = api.create_commit(
            operations=[CommitOperationAdd("shared.txt", b"seed")],
            commit_message="seed",
        )
        api.create_branch(branch="feature")
        _ = api.create_commit(
            operations=[CommitOperationAdd("shared.txt", b"main")],
            commit_message="main modify",
        )
        _ = api.create_commit(
            revision="feature",
            operations=[CommitOperationDelete("shared.txt")],
            commit_message="feature delete",
        )

        result = api.merge("feature")

        assert result.status == "conflict"
        assert result.commit is None
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == "delete/modify"
        assert result.conflicts[0].path == "shared.txt"

    def test_merge_public_api_rejects_invalid_target_revision_and_empty_message(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        commit = api.create_commit(
            operations=[CommitOperationAdd("shared.txt", b"base")],
            commit_message="seed",
        )
        api.create_branch(branch="feature")
        api.create_tag(tag="v1", revision="main")
        _ = api.create_commit(
            operations=[CommitOperationAdd("main.txt", b"main")],
            commit_message="main work",
        )
        _ = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("feature.txt", b"feature")],
            commit_message="feature work",
        )

        with pytest.raises(UnsupportedPathError):
            api.merge("feature", target_revision=commit.oid)

        with pytest.raises(UnsupportedPathError):
            api.merge("feature", target_revision="refs/tags/v1")

        with pytest.raises(ValueError):
            api.merge("feature", commit_message="")

    def test_phase2_public_refs_upload_delete_snapshot_and_reflog_methods(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        upload_commit = api.upload_file(
            path_or_fileobj=b"weights-v1",
            path_in_repo="models/model.bin",
        )

        assert upload_commit.commit_message == "Upload models/model.bin with hubvault"
        assert upload_commit.commit_description == ""
        assert str(upload_commit).endswith("#blob=main:models/model.bin")

        refs_after_upload = api.list_repo_refs()
        assert [item.name for item in refs_after_upload.branches] == ["main"]
        assert refs_after_upload.branches[0].ref == "refs/heads/main"
        assert refs_after_upload.branches[0].target_commit == upload_commit.oid
        assert refs_after_upload.tags == []
        assert refs_after_upload.pull_requests is None
        assert api.list_repo_reflog("main", limit=1)[0].message == "Upload models/model.bin with hubvault"

        api.create_branch(branch="dev", revision=upload_commit.oid)
        api.create_branch(branch="dev", exist_ok=True)
        api.create_tag(tag="v1", revision=upload_commit.oid, tag_message="release")

        refs = api.list_repo_refs(include_pull_requests=True)
        assert sorted(item.name for item in refs.branches) == ["dev", "main"]
        assert [item.name for item in refs.tags] == ["v1"]
        assert refs.tags[0].target_commit == upload_commit.oid
        assert refs.pull_requests == []

        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        (staging_dir / "keep.txt").write_text("keep\n", encoding="utf-8")
        (staging_dir / "drop.log").write_text("drop\n", encoding="utf-8")
        (staging_dir / "nested").mkdir()
        (staging_dir / "nested" / "inner.txt").write_text("inner\n", encoding="utf-8")
        (staging_dir / "nested" / ".git").mkdir()
        (staging_dir / "nested" / ".git" / "ignored.txt").write_text("ignored\n", encoding="utf-8")

        folder_commit = api.upload_folder(
            folder_path=staging_dir,
            path_in_repo="bundle",
            revision="dev",
            allow_patterns="*.txt",
        )

        assert folder_commit.commit_message == "Upload folder using hubvault"
        assert str(folder_commit).endswith("#tree=dev:bundle")
        assert api.list_repo_files(revision="dev") == [
            "bundle/keep.txt",
            "bundle/nested/inner.txt",
            "models/model.bin",
        ]

        snapshot_dir = Path(
            api.snapshot_download(
                revision="dev",
                local_dir=tmp_path / "snapshot-export",
            )
        )
        assert snapshot_dir == Path(os.path.realpath(str(tmp_path / "snapshot-export")))
        assert (snapshot_dir / "models" / "model.bin").read_bytes() == b"weights-v1"
        assert (snapshot_dir / "bundle" / "keep.txt").read_text(encoding="utf-8") == "keep\n"
        assert (snapshot_dir / "bundle" / "nested" / "inner.txt").read_text(encoding="utf-8") == "inner\n"
        assert (snapshot_dir / ".cache" / "hubvault" / "snapshot.json").is_file()

        delete_file_commit = api.delete_file("models/model.bin", revision="dev")
        delete_folder_commit = api.delete_folder("bundle", revision="dev")

        assert delete_file_commit.commit_message == "Delete models/model.bin with hubvault"
        assert delete_folder_commit.commit_message == "Delete folder bundle with hubvault"
        assert api.list_repo_files(revision="dev") == []
        assert [item.title for item in api.list_repo_commits(revision="dev")] == [
            "Delete folder bundle with hubvault",
            "Delete models/model.bin with hubvault",
            "Upload folder using hubvault",
            "Upload models/model.bin with hubvault",
            "Initial commit",
        ]

        api.delete_tag(tag="v1")
        api.delete_branch(branch="dev")

        final_refs = api.list_repo_refs()
        assert [item.name for item in final_refs.branches] == ["main"]
        assert final_refs.tags == []
        tag_reflog = api.list_repo_reflog("refs/tags/v1")
        assert [item.message for item in tag_reflog] == ["delete tag", "release"]
        assert tag_reflog[0].new_head is None
        assert tag_reflog[1].new_head == upload_commit.oid

    def test_phase2_public_api_error_paths(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        assert [item.message for item in api.list_repo_reflog("main")] == ["Initial commit"]

        with pytest.raises(RevisionNotFoundError):
            api.create_branch(branch="dev", revision="missing")

        with pytest.raises(RevisionNotFoundError):
            api.create_tag(tag="v1", revision="missing")

        first_commit = api.upload_file(path_or_fileobj=b"payload", path_in_repo="file.txt")
        api.create_branch(branch="same", revision=first_commit.oid)
        api.create_tag(tag="same", revision=first_commit.oid)
        api.create_branch(branch="same", exist_ok=True)
        api.create_tag(tag="same", revision=first_commit.oid, exist_ok=True)

        with pytest.raises(ConflictError):
            api.create_branch(branch="same")

        with pytest.raises(ConflictError):
            api.create_tag(tag="same", revision=first_commit.oid)

        with pytest.raises(ConflictError):
            api.list_repo_reflog("same")

        assert api.list_repo_reflog("refs/tags/same")[0].ref_name == "refs/tags/same"

        with pytest.raises(ConflictError):
            api.delete_branch(branch="main")

        with pytest.raises(ValueError):
            api.list_repo_reflog("main", limit=-1)

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_reflog("missing")

        with pytest.raises(UnsupportedPathError):
            api.snapshot_download(local_dir=repo_dir / "unsafe")

        with pytest.raises(ValueError):
            api.upload_folder(folder_path=tmp_path / "missing-folder")

    def test_phase3_public_range_read_and_large_folder_upload_methods(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo(large_file_threshold=32)

        large_payload = b"phase3-range-" * 12
        expected_sha256 = _sha256_value(large_payload)
        expected_oid = lfs_pointer_oid(canonical_lfs_pointer(expected_sha256, len(large_payload)))

        commit = api.create_commit(
            operations=[CommitOperationAdd("models/model.bin", large_payload)],
            commit_message="seed phase3 public api",
        )

        assert commit.commit_message == "seed phase3 public api"
        info = api.get_paths_info("models/model.bin")[0]
        assert isinstance(info, RepoFile)
        assert info.size == len(large_payload)
        assert info.blob_id == expected_oid
        assert info.oid == expected_oid
        assert info.sha256 == expected_sha256
        assert info.etag == expected_sha256
        assert info.lfs is not None
        assert info.lfs.size == len(large_payload)
        assert info.lfs.sha256 == expected_sha256
        assert info.lfs.pointer_size == len(canonical_lfs_pointer(expected_sha256, len(large_payload)))
        assert api.read_range("models/model.bin", start=7, length=19) == large_payload[7:26]

        source_dir = tmp_path / "large-folder"
        (source_dir / "bundle").mkdir(parents=True)
        (source_dir / "bundle" / "keep.bin").write_bytes(b"K" * 96)
        (source_dir / "bundle" / "drop.log").write_bytes(b"ignored\n")

        folder_commit = api.upload_large_folder(
            folder_path=source_dir,
            allow_patterns="*.bin",
        )

        assert folder_commit.commit_message == "Upload large folder using hubvault"
        assert api.list_repo_files() == [
            "bundle/keep.bin",
            "models/model.bin",
        ]
        assert api.read_bytes("bundle/keep.bin") == b"K" * 96

    def test_phase3_public_threshold_boundary_only_chunks_eligible_files(self, tmp_path):
        """
        Simulate a public API upload at the chunk threshold boundary.

        The simulated user flow creates one repository with a small
        ``large_file_threshold`` and uploads three files whose sizes are below,
        equal to, and above that threshold. The assertions verify that only the
        threshold-eligible files switch to Phase 3 chunk storage while the
        smaller file remains a normal whole-blob object.
        """

        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        threshold = 64
        api.create_repo(large_file_threshold=threshold)

        below_payload = b"b" * (threshold - 1)
        exact_payload = b"e" * threshold
        above_payload = b"a" * (threshold + 1)

        api.create_commit(
            operations=[
                CommitOperationAdd("sizes/below.bin", below_payload),
                CommitOperationAdd("sizes/exact.bin", exact_payload),
                CommitOperationAdd("sizes/above.bin", above_payload),
            ],
            commit_message="seed threshold boundary files",
        )

        items = {
            item.path: item
            for item in api.get_paths_info(
                [
                    "sizes/below.bin",
                    "sizes/exact.bin",
                    "sizes/above.bin",
                ]
            )
        }

        assert items["sizes/below.bin"].lfs is None
        assert items["sizes/below.bin"].oid == _git_blob_oid(below_payload)
        assert items["sizes/below.bin"].etag == _git_blob_oid(below_payload)

        exact_expected_oid = lfs_pointer_oid(canonical_lfs_pointer(_sha256_value(exact_payload), len(exact_payload)))
        above_expected_oid = lfs_pointer_oid(canonical_lfs_pointer(_sha256_value(above_payload), len(above_payload)))
        assert items["sizes/exact.bin"].lfs is not None
        assert items["sizes/exact.bin"].oid == exact_expected_oid
        assert items["sizes/exact.bin"].etag == _sha256_value(exact_payload)
        assert items["sizes/above.bin"].lfs is not None
        assert items["sizes/above.bin"].oid == above_expected_oid
        assert items["sizes/above.bin"].etag == _sha256_value(above_payload)

        pack_files = sorted((repo_dir / "chunks" / "packs").glob("*.pack"))
        assert len(pack_files) == 2
        assert api.read_bytes("sizes/below.bin") == below_payload
        assert api.read_bytes("sizes/exact.bin") == exact_payload
        assert api.read_bytes("sizes/above.bin") == above_payload

    def test_phase4_public_storage_analysis_gc_and_blocking_refs(self, tmp_path):
        """
        Simulate a public maintenance workflow with storage analysis and squash.

        The simulated user story creates two revisions of the same large file,
        inspects the public storage overview, previews GC, and then verifies
        that another branch still blocks immediate reclamation after a squash on
        the main branch.
        """

        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo(large_file_threshold=64)

        first_commit = api.create_commit(
            operations=[
                CommitOperationAdd("artifacts/model.bin", b"A" * 512),
                CommitOperationAdd("notes.txt", b"v1\n"),
            ],
            commit_message="seed v1",
        )
        second_commit = api.create_commit(
            operations=[
                CommitOperationAdd("artifacts/model.bin", b"B" * 512),
                CommitOperationAdd("notes.txt", b"v2\n"),
            ],
            commit_message="seed v2",
        )
        api.create_branch(branch="archive", revision=first_commit.oid)

        _ = api.hf_hub_download("artifacts/model.bin")
        _ = api.snapshot_download()

        verify_report = api.full_verify()
        overview = api.get_storage_overview()
        gc_report = api.gc(dry_run=True, prune_cache=True)
        squash_report = api.squash_history(
            "main",
            root_revision=second_commit.oid,
            run_gc=False,
        )

        assert verify_report.ok is True
        assert isinstance(overview, StorageOverview)
        assert overview.total_size > 0
        assert overview.reclaimable_cache_size > 0
        assert any(section.name == "chunks.packs" for section in overview.sections)

        assert isinstance(gc_report, GcReport)
        assert gc_report.dry_run is True
        assert gc_report.reclaimed_cache_size > 0
        assert "refs/heads/archive" in gc_report.checked_refs

        assert isinstance(squash_report, SquashReport)
        assert squash_report.ref_name == "refs/heads/main"
        assert squash_report.old_head == second_commit.oid
        assert squash_report.new_head != second_commit.oid
        assert squash_report.root_commit_before == second_commit.oid
        assert squash_report.rewritten_commit_count == 1
        assert squash_report.dropped_ancestor_count == 2
        assert squash_report.blocking_refs == ["refs/heads/archive"]
        assert squash_report.gc_report is None
