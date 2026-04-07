import json
import shutil
from pathlib import Path

import pytest

from hubvault import (
    CommitOperationAdd,
    CommitOperationCopy,
    CommitOperationDelete,
    ConflictError,
    HubVaultApi,
    IntegrityError,
    LockTimeoutError,
    PathNotFoundError,
    RepoAlreadyExistsError,
    RevisionNotFoundError,
    UnsupportedPathError,
)


def _single_file_repo(tmp_path, repo_name="repo", path_in_repo="file.bin", payload=b"payload-v1"):
    repo_dir = tmp_path / repo_name
    api = HubVaultApi(repo_dir)
    api.create_repo()
    api.create_commit(
        operations=[CommitOperationAdd.from_bytes(path_in_repo, payload)],
        commit_message="seed",
    )
    return api, repo_dir


def _only_path(root, pattern):
    matches = sorted(root.rglob(pattern))
    assert len(matches) == 1
    return matches[0]


def _object_json_path(repo_dir, object_type, object_id):
    algorithm, digest = object_id.split(":", 1)
    assert algorithm == "sha256"
    return repo_dir / "objects" / object_type / "sha256" / digest[:2] / (digest[2:] + ".json")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, payload):
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


@pytest.mark.unittest
class TestRepoSemantics:
    def test_repo_rejects_non_empty_target_and_invalid_public_paths(self, tmp_path):
        occupied_dir = tmp_path / "occupied"
        occupied_dir.mkdir()
        (occupied_dir / "placeholder.txt").write_text("busy", encoding="utf-8")

        with pytest.raises(RepoAlreadyExistsError):
            HubVaultApi(occupied_dir).create_repo()

        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()

        invalid_paths = [
            "",
            "/abs.txt",
            "C:/abs.txt",
            "bad?.txt",
            "...",
            "CON.txt",
        ]
        for invalid_path in invalid_paths:
            with pytest.raises(UnsupportedPathError):
                api.create_commit(
                    operations=[CommitOperationAdd.from_bytes(invalid_path, b"x")],
                    commit_message="invalid path",
                )

    def test_download_views_are_detached_and_rebuildable(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd.from_bytes("models/core/model.safetensors", b"payload-v1")],
            commit_message="seed",
        )

        view_path = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert view_path.as_posix().endswith("models/core/model.safetensors")
        assert view_path.read_bytes() == b"payload-v1"

        view_path.write_bytes(b"tampered")
        report = api.quick_verify()
        assert report.ok is True
        assert any("stale file view" in warning for warning in report.warnings)
        assert api.read_bytes("models/core/model.safetensors") == b"payload-v1"

        rebuilt_path = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert rebuilt_path == view_path
        assert rebuilt_path.read_bytes() == b"payload-v1"

        same_path = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert same_path == view_path
        assert same_path.read_bytes() == b"payload-v1"

        rebuilt_path.unlink()
        restored_path = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert restored_path == view_path
        assert restored_path.read_bytes() == b"payload-v1"

        external_path = Path(
            api.hf_hub_download(
                "models/core/model.safetensors",
                local_dir=tmp_path / "exports",
            )
        )
        external_path.write_bytes(b"tampered-external")
        refreshed_external_path = Path(
            api.hf_hub_download(
                "models/core/model.safetensors",
                local_dir=tmp_path / "exports",
            )
        )
        assert refreshed_external_path == external_path
        assert refreshed_external_path.read_bytes() == b"payload-v1"

        dir_blocking_path = tmp_path / "dir-exports" / "models" / "core" / "model.safetensors"
        dir_blocking_path.mkdir(parents=True)
        rebuilt_from_dir = Path(
            api.hf_hub_download(
                "models/core/model.safetensors",
                local_dir=tmp_path / "dir-exports",
            )
        )
        assert rebuilt_from_dir.is_file()
        assert rebuilt_from_dir.read_bytes() == b"payload-v1"

        symlink_target = tmp_path / "symlink-target.bin"
        symlink_target.write_bytes(b"elsewhere")
        symlink_path = tmp_path / "link-exports" / "models" / "core" / "model.safetensors"
        symlink_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            symlink_path.symlink_to(symlink_target)
        except (NotImplementedError, OSError):
            pass
        else:
            rebuilt_from_symlink = Path(
                api.hf_hub_download(
                    "models/core/model.safetensors",
                    local_dir=tmp_path / "link-exports",
                )
            )
            assert rebuilt_from_symlink.is_file()
            assert rebuilt_from_symlink.read_bytes() == b"payload-v1"

    def test_copy_delete_reset_and_repo_move_keep_working(self, tmp_path):
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
        assert api.quick_verify().ok is True

        moved_repo_dir = tmp_path / "moved-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        moved_api = HubVaultApi(moved_repo_dir)

        assert moved_api.repo_info().head == first_commit.commit_id
        assert moved_api.read_bytes("src/sub/b.txt") == b"B"
        report = moved_api.quick_verify()
        assert report.ok is True
        assert "refs/heads/main" in report.checked_refs

    def test_empty_branch_and_tag_resolution_paths(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        created = api.create_repo()

        report = api.quick_verify()
        assert report.ok is True
        assert report.errors == []
        assert report.checked_refs == ["refs/heads/main"]
        assert created.head is None

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files(revision="refs/heads/main")

        commit = api.create_commit(
            operations=[CommitOperationAdd.from_bytes("file.bin", b"payload")],
            commit_message="seed",
        )

        tag_empty_path = tmp_path / "repo" / "refs" / "tags" / "v-empty"
        tag_empty_path.parent.mkdir(parents=True, exist_ok=True)
        tag_empty_path.write_text("", encoding="utf-8")

        tag_good_path = tmp_path / "repo" / "refs" / "tags" / "v-good"
        tag_good_path.write_text(commit.commit_id + "\n", encoding="utf-8")

        tag_broken_path = tmp_path / "repo" / "refs" / "tags" / "v-broken"
        tag_broken_path.write_text("sha256:" + ("0" * 64) + "\n", encoding="utf-8")

        assert api.list_repo_files(revision="refs/tags/v-good") == ["file.bin"]
        assert api.list_repo_files(revision="v-good") == ["file.bin"]

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files(revision="refs/tags/missing")

        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files(revision="refs/tags/v-empty")

        report = api.quick_verify()
        assert "refs/tags/v-empty" in report.checked_refs
        assert "refs/tags/v-good" in report.checked_refs
        assert "refs/tags/v-broken" in report.checked_refs
        assert any(item.startswith("refs/tags/v-broken:") for item in report.errors)

    def test_repo_recovers_transaction_leftovers_and_lock_conflicts(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()

        stray_file = tmp_path / "repo" / "txn" / "note.txt"
        stray_file.write_text("keep me", encoding="utf-8")
        stale_dir = tmp_path / "repo" / "txn" / "stale"
        stale_dir.mkdir()
        (stale_dir / "payload.txt").write_text("remove me", encoding="utf-8")

        info = api.repo_info()
        assert info.default_branch == "main"
        assert stray_file.is_file()
        assert not stale_dir.exists()

        lock_owner = tmp_path / "repo" / "locks" / "write.lock"
        lock_owner.mkdir(parents=True)
        (lock_owner / "owner.json").write_text("{}", encoding="utf-8")

        with pytest.raises(LockTimeoutError):
            api.create_commit(
                operations=[CommitOperationAdd.from_bytes("blocked.bin", b"x")],
                commit_message="blocked",
            )

    def test_repo_detects_ref_and_config_corruption(self, tmp_path):
        api, repo_dir = _single_file_repo(tmp_path, repo_name="corrupt-refs")

        ref_path = repo_dir / "refs" / "heads" / "main"

        ref_path.write_text("broken\n", encoding="utf-8")
        with pytest.raises(IntegrityError):
            api.list_repo_files()

        ref_path.write_text("sha256:\n", encoding="utf-8")
        with pytest.raises(IntegrityError):
            api.list_repo_files()

        ref_path.write_text("sha256:" + ("0" * 64) + "\n", encoding="utf-8")
        report = api.quick_verify()
        assert report.ok is False
        assert any(item.startswith("refs/heads/main:") for item in report.errors)

        healthy_api, healthy_repo_dir = _single_file_repo(tmp_path, repo_name="corrupt-config")
        config_path = healthy_repo_dir / "repo.json"
        config_data = _read_json(config_path)
        config_data["format_version"] = 999
        _write_json(config_path, config_data)

        report = healthy_api.quick_verify()
        assert report.ok is False
        assert "unsupported format version" in report.errors

    def test_repo_detects_blob_tree_and_file_corruption(self, tmp_path):
        api, repo_dir = _single_file_repo(tmp_path, repo_name="blob-checksum", payload=b"payload")
        blob_data_path = _only_path(repo_dir / "objects" / "blobs" / "sha256", "*.data")
        blob_data_path.write_bytes(b"tampered")
        with pytest.raises(IntegrityError):
            api.read_bytes("file.bin")

        api, repo_dir = _single_file_repo(tmp_path, repo_name="invalid-file-container", payload=b"payload")
        file_object_path = _only_path(repo_dir / "objects" / "files" / "sha256", "*.json")
        file_object_path.write_text("{}", encoding="utf-8")
        with pytest.raises(IntegrityError):
            api.read_bytes("file.bin")

        api, repo_dir = _single_file_repo(tmp_path, repo_name="invalid-tree-entry", payload=b"payload")
        tree_object_path = _only_path(repo_dir / "objects" / "trees" / "sha256", "*.json")
        tree_payload = _read_json(tree_object_path)
        tree_payload["payload"]["entries"][0]["entry_type"] = "weird"
        _write_json(tree_object_path, tree_payload)
        with pytest.raises(IntegrityError):
            api.list_repo_files()

        api, repo_dir = _single_file_repo(tmp_path, repo_name="missing-commit-object", payload=b"payload")
        commit_object_path = _only_path(repo_dir / "objects" / "commits" / "sha256", "*.json")
        commit_object_path.unlink()
        report = api.quick_verify()
        assert report.ok is False
        assert any(item.startswith("refs/heads/main:") for item in report.errors)

    def test_repo_detects_verify_corruption_cases(self, tmp_path):
        api, repo_dir = _single_file_repo(tmp_path, repo_name="missing-blob-data", payload=b"payload")
        blob_data_path = _only_path(repo_dir / "objects" / "blobs" / "sha256", "*.data")
        blob_data_path.unlink()
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="wrong-file-sha", payload=b"payload")
        file_object_path = _only_path(repo_dir / "objects" / "files" / "sha256", "*.json")
        file_payload = _read_json(file_object_path)
        file_payload["payload"]["sha256"] = "sha256:" + ("1" * 64)
        _write_json(file_object_path, file_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="wrong-blob-sha", payload=b"payload")
        blob_meta_path = _only_path(repo_dir / "objects" / "blobs" / "sha256", "*.meta.json")
        blob_meta = _read_json(blob_meta_path)
        blob_meta["payload"]["payload_sha256"] = "sha256:" + ("2" * 64)
        _write_json(blob_meta_path, blob_meta)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="wrong-file-oid", payload=b"payload")
        file_object_path = _only_path(repo_dir / "objects" / "files" / "sha256", "*.json")
        file_payload = _read_json(file_object_path)
        file_payload["payload"]["oid"] = "0" * 40
        _write_json(file_object_path, file_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="missing-file-key", payload=b"payload")
        file_object_path = _only_path(repo_dir / "objects" / "files" / "sha256", "*.json")
        file_payload = _read_json(file_object_path)
        del file_payload["payload"]["content_object_id"]
        _write_json(file_object_path, file_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="duplicate-parent", payload=b"payload")
        first_head = (repo_dir / "refs" / "heads" / "main").read_text(encoding="utf-8").strip()
        api.create_commit(
            operations=[CommitOperationAdd.from_bytes("file.bin", b"payload-v2")],
            parent_commit=first_head,
            commit_message="second",
        )
        branch_head = (repo_dir / "refs" / "heads" / "main").read_text(encoding="utf-8").strip()
        head_commit_path = _object_json_path(repo_dir, "commits", branch_head)
        commit_payload = _read_json(head_commit_path)
        first_parent = commit_payload["payload"]["parents"][0]
        commit_payload["payload"]["parents"] = [first_parent, first_parent]
        _write_json(head_commit_path, commit_payload)
        assert api.quick_verify().ok is True

        api, repo_dir = _single_file_repo(tmp_path, repo_name="weird-tree-entry", payload=b"payload")
        tree_object_path = _only_path(repo_dir / "objects" / "trees" / "sha256", "*.json")
        tree_payload = _read_json(tree_object_path)
        tree_payload["payload"]["entries"][0]["entry_type"] = "weird"
        _write_json(tree_object_path, tree_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="malformed-tree", payload=b"payload")
        tree_object_path = _only_path(repo_dir / "objects" / "trees" / "sha256", "*.json")
        tree_payload = _read_json(tree_object_path)
        tree_payload["payload"]["entries"] = [{}]
        _write_json(tree_object_path, tree_payload)
        report = api.quick_verify()
        assert report.ok is False

    def test_repo_conflict_and_missing_path_cases(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[
                    CommitOperationAdd.from_bytes("dup.txt", b"a"),
                    CommitOperationAdd.from_bytes("dup.txt/child.txt", b"b"),
                ],
                commit_message="invalid hierarchy",
            )

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[
                    CommitOperationAdd.from_bytes("Case.txt", b"a"),
                    CommitOperationAdd.from_bytes("case.txt", b"b"),
                ],
                commit_message="case clash",
            )

        baseline = api.create_commit(
            operations=[CommitOperationAdd.from_bytes("data/file.txt", b"v1")],
            commit_message="seed",
        )

        copied = api.create_commit(
            operations=[CommitOperationCopy("data/file.txt", "data/copied.txt")],
            parent_commit=baseline.commit_id,
            commit_message="copy single file",
        )
        assert copied.parents == [baseline.commit_id]
        assert api.read_bytes("data/copied.txt") == b"v1"

        deleted = api.create_commit(
            operations=[CommitOperationDelete("data/copied.txt")],
            parent_commit=copied.commit_id,
            commit_message="delete single file",
        )
        assert deleted.parents == [copied.commit_id]
        with pytest.raises(PathNotFoundError):
            api.read_bytes("data/copied.txt")

        with pytest.raises(PathNotFoundError):
            api.create_commit(
                operations=[CommitOperationDelete("missing.txt")],
                parent_commit=deleted.commit_id,
                commit_message="missing delete",
            )

        with pytest.raises(PathNotFoundError):
            api.create_commit(
                operations=[CommitOperationCopy("missing.txt", "copied.txt")],
                parent_commit=deleted.commit_id,
                commit_message="missing copy",
            )

        with pytest.raises(RevisionNotFoundError):
            api.reset_ref("main", "missing")
