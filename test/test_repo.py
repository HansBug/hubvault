import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import warnings
from pathlib import Path
from textwrap import dedent

import pytest

from hubvault import (
    CommitOperationAdd,
    CommitOperationCopy,
    CommitOperationDelete,
    ConflictError,
    EntryNotFoundError,
    HubVaultApi,
    IntegrityError,
    RepositoryAlreadyExistsError,
    RevisionNotFoundError,
    UnsupportedPathError,
)
from hubvault.storage.chunk import DEFAULT_CHUNK_SIZE
from hubvault.storage.pack import PACK_MAGIC
from hubvault.repo.sqlite import SQLITE_METADATA_FILENAME


def _single_file_repo(tmp_path, repo_name="repo", path_in_repo="file.bin", payload=b"payload-v1"):
    repo_dir = tmp_path / repo_name
    api = HubVaultApi(repo_dir)
    api.create_repo()
    api.create_commit(
        operations=[CommitOperationAdd(path_in_repo, payload)],
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


def _repo_db_path(repo_dir):
    return Path(repo_dir) / SQLITE_METADATA_FILENAME


def _object_table(object_type):
    return {
        "commits": "objects_commits",
        "trees": "objects_trees",
        "files": "objects_files",
        "blobs": "objects_blobs",
    }[object_type]


def _internal_ref_value(repo_dir, ref_kind, ref_name):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        row = conn.execute(
            "SELECT commit_id FROM refs WHERE ref_kind = ? AND ref_name = ?",
            (ref_kind, ref_name),
        ).fetchone()
    assert row is not None
    return row[0]


def _set_internal_ref_value(repo_dir, ref_kind, ref_name, commit_id):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO refs (ref_kind, ref_name, commit_id, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (ref_kind, ref_name, commit_id, "2026-04-10T00:00:00Z"),
        )
        conn.commit()


def _head_commit_id(repo_dir, branch_name="main"):
    return _internal_ref_value(repo_dir, "branch", branch_name)


def _object_payload(repo_dir, object_type, object_id):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        row = conn.execute(
            "SELECT payload_json FROM %s WHERE object_id = ?" % _object_table(object_type),
            (object_id,),
        ).fetchone()
    assert row is not None
    return json.loads(row[0])


def _set_object_payload(repo_dir, object_type, object_id, payload):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        conn.execute(
            "UPDATE %s SET payload_json = ? WHERE object_id = ?" % _object_table(object_type),
            (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), object_id),
        )
        conn.commit()


def _mutate_object_payload(repo_dir, object_type, object_id, mutator):
    payload = _object_payload(repo_dir, object_type, object_id)
    mutator(payload)
    _set_object_payload(repo_dir, object_type, object_id, payload)


def _first_object_id(repo_dir, object_type):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        row = conn.execute("SELECT object_id FROM %s ORDER BY object_id LIMIT 1" % _object_table(object_type)).fetchone()
    assert row is not None
    return str(row[0])


def _head_tree_id(repo_dir, branch_name="main"):
    return str(_object_payload(repo_dir, "commits", _head_commit_id(repo_dir, branch_name))["tree_id"])


def _mutate_repo_meta(repo_dir, key, mutator):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        row = conn.execute("SELECT value_json FROM repo_meta WHERE key = ?", (key,)).fetchone()
        assert row is not None
        value = mutator(json.loads(row[0]))
        conn.execute(
            "UPDATE repo_meta SET value_json = ? WHERE key = ?",
            (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False), key),
        )
        conn.commit()


def _delete_reflog_rows(repo_dir, ref_kind, ref_name):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        conn.execute("DELETE FROM reflog WHERE ref_kind = ? AND ref_name = ?", (ref_kind, ref_name))
        conn.commit()


def _delete_object(repo_dir, object_type, object_id):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        conn.execute("DELETE FROM %s WHERE object_id = ?" % _object_table(object_type), (object_id,))
        conn.commit()


def _load_index_records(repo_dir):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        rows = conn.execute(
            """
            SELECT chunk_id, pack_id, offset, stored_size, logical_size, compression, checksum
            FROM chunk_visible
            ORDER BY chunk_id
            """
        ).fetchall()
    records = [
        {
            "chunk_id": row[0],
            "pack_id": row[1],
            "offset": row[2],
            "stored_size": row[3],
            "logical_size": row[4],
            "compression": row[5],
            "checksum": row[6],
        }
        for row in rows
    ]
    assert records
    return records


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, payload):
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _create_empty_legacy_repo(repo_dir):
    repo_dir = Path(repo_dir)
    (repo_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (repo_dir / "FORMAT").write_text("hubvault-repo/v1\n", encoding="utf-8")
    (repo_dir / "repo.json").write_text(
        json.dumps(
            {
                "default_branch": "main",
                "file_mode": "whole-blob-first",
                "format_version": 1,
                "large_file_threshold": 16777216,
                "metadata": {},
                "object_hash": "sha256",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    (repo_dir / "refs" / "heads" / "main").write_text("", encoding="utf-8")


def _wait_for_path(path, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(path).exists():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for %s" % path)


def _repo_root():
    return Path(__file__).resolve().parents[1]


def _is_git_oid(value):
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdef" for ch in value)


@pytest.mark.unittest
class TestRepoSemantics:
    def test_repo_rejects_non_empty_target_and_invalid_public_paths(self, tmp_path):
        occupied_dir = tmp_path / "occupied"
        occupied_dir.mkdir()
        (occupied_dir / "placeholder.txt").write_text("busy", encoding="utf-8")

        with pytest.raises(RepositoryAlreadyExistsError):
            HubVaultApi(occupied_dir).create_repo()

        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()

        invalid_paths = [
            "",
            ".",
            "/abs.txt",
            "C:/abs.txt",
            "bad?.txt",
            "...",
            "CON.txt",
        ]
        for invalid_path in invalid_paths:
            with pytest.raises(UnsupportedPathError):
                api.create_commit(
                    operations=[CommitOperationAdd(invalid_path, b"x")],
                    commit_message="invalid path",
                )

    def test_create_repo_runtime_failpoint_leaves_empty_public_branch_state(self, tmp_path, monkeypatch):
        api = HubVaultApi(tmp_path / "repo")

        with monkeypatch.context() as env:
            env.setenv("HUBVAULT_FAILPOINT", "create_repo.initial_commit.after_reflog_append")
            env.setenv("HUBVAULT_FAIL_ACTION", "raise-runtime")
            with pytest.raises(RuntimeError) as excinfo:
                api.create_repo()

        assert "create_repo.initial_commit.after_reflog_append" in str(excinfo.value)
        assert api.repo_info().head is None
        assert api.list_repo_tree() == []
        assert api.list_repo_commits() == []
        assert api.quick_verify().ok is True

    def test_download_views_are_detached_and_rebuildable(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("models/core/model.safetensors", b"payload-v1")],
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

    def test_managed_download_view_metadata_is_rebuilt_when_metadata_is_invalid(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("models/core/model.safetensors", b"payload-v1")],
            commit_message="seed",
        )

        repo_dir = tmp_path / "repo"
        view_path = Path(api.hf_hub_download("models/core/model.safetensors"))
        view_meta_path = _only_path(repo_dir / "cache" / "views" / "files", "*.json")

        metadata = _read_json(view_meta_path)
        metadata.pop("view_mtime_ns")
        _write_json(view_meta_path, metadata)

        rebuilt_without_mtime = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert rebuilt_without_mtime == view_path
        assert rebuilt_without_mtime.read_bytes() == b"payload-v1"
        assert "view_mtime_ns" in _read_json(view_meta_path)

        metadata = _read_json(view_meta_path)
        metadata["target_path"] = "cache/files/invalid/models/core/model.safetensors"
        _write_json(view_meta_path, metadata)

        rebuilt_with_wrong_target = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert rebuilt_with_wrong_target == view_path
        assert rebuilt_with_wrong_target.read_bytes() == b"payload-v1"

        view_meta_path.write_text("[]", encoding="utf-8")
        rebuilt_from_list_metadata = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert rebuilt_from_list_metadata == view_path
        assert rebuilt_from_list_metadata.read_bytes() == b"payload-v1"

        view_meta_path.write_text("{bad json", encoding="utf-8")
        rebuilt_from_bad_json = Path(api.hf_hub_download("models/core/model.safetensors"))
        assert rebuilt_from_bad_json == view_path
        assert rebuilt_from_bad_json.read_bytes() == b"payload-v1"

    def test_managed_download_view_rebuilds_for_metadata_mismatches_and_verify_tolerates_bad_size(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("models/core/model.safetensors", b"payload-v1")],
            commit_message="seed",
        )

        repo_dir = tmp_path / "repo"
        view_path = Path(api.hf_hub_download("models/core/model.safetensors"))
        view_meta_path = _only_path(repo_dir / "cache" / "views" / "files", "*.json")

        def assert_rebuilt():
            rebuilt = Path(api.hf_hub_download("models/core/model.safetensors"))
            assert rebuilt == view_path
            assert rebuilt.read_bytes() == b"payload-v1"

        for field, replacement in (
            ("revision", "other"),
            ("commit_id", None),
            ("path_in_repo", "models/core/other.safetensors"),
            ("sha256", "0" * 64),
            ("size", 999),
        ):
            metadata = _read_json(view_meta_path)
            metadata[field] = replacement
            _write_json(view_meta_path, metadata)
            assert_rebuilt()

        metadata = _read_json(view_meta_path)
        metadata["size"] = "invalid"
        _write_json(view_meta_path, metadata)

        report = api.quick_verify()
        assert report.ok is True
        assert not any("stale file view" in warning for warning in report.warnings)

        assert_rebuilt()

    def test_legacy_repo_reopen_repairs_incomplete_sqlite_bootstrap(self, tmp_path):
        repo_dir = tmp_path / "legacy-repo"
        _create_empty_legacy_repo(repo_dir)

        sqlite_path = repo_dir / SQLITE_METADATA_FILENAME
        with sqlite3.connect(str(sqlite_path)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_info (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES (?, ?)", ("schema_version", "1"))
            conn.execute("CREATE TABLE IF NOT EXISTS repo_meta (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)")
            conn.commit()

        api = HubVaultApi(repo_dir)
        info = api.repo_info()

        assert info.default_branch == "main"
        assert info.head is None
        assert api.list_repo_tree() == []
        assert api.quick_verify().ok is True

        created = api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"legacy repaired\n")],
            commit_message="repair legacy sqlite bootstrap",
        )
        assert api.repo_info().head == created.oid
        assert api.read_bytes("notes.txt") == b"legacy repaired\n"

    def test_repo_raises_integrity_error_for_incomplete_sqlite_truth_without_legacy_fallback(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()

        with sqlite3.connect(str(tmp_path / "repo" / SQLITE_METADATA_FILENAME)) as conn:
            conn.execute("DELETE FROM repo_meta")
            conn.commit()

        broken_api = HubVaultApi(tmp_path / "repo")
        with pytest.raises(IntegrityError, match="sqlite metadata store is incomplete"):
            broken_api.repo_info()

    def test_copy_delete_reset_and_repo_move_keep_working(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        first_commit = api.create_commit(
            operations=[
                CommitOperationAdd("src/a.txt", b"A"),
                CommitOperationAdd("src/sub/b.txt", b"B"),
            ],
            commit_message="seed repo",
        )
        second_commit = api.create_commit(
            operations=[
                CommitOperationCopy("src", "mirror", src_revision="main"),
                CommitOperationDelete("src/sub/"),
            ],
            parent_commit=first_commit.oid,
            commit_message="copy and prune",
        )

        assert _is_git_oid(second_commit.oid)
        assert api.list_repo_files() == [
            "mirror/a.txt",
            "mirror/sub/b.txt",
            "src/a.txt",
        ]

        reset = api.reset_ref("main", to_revision=first_commit.oid)
        assert reset.oid == first_commit.oid
        assert api.list_repo_files() == ["src/a.txt", "src/sub/b.txt"]
        assert api.quick_verify().ok is True

        moved_repo_dir = tmp_path / "moved-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        moved_api = HubVaultApi(moved_repo_dir)

        assert moved_api.repo_info().head == first_commit.oid
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
        assert created.head is not None
        assert api.list_repo_tree() == []
        assert api.list_repo_files(revision="refs/heads/main") == []
        assert [item.title for item in api.list_repo_commits(revision="refs/heads/main")] == ["Initial commit"]

        commit = api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"payload")],
            commit_message="seed",
        )

        repo_dir = tmp_path / "repo"
        _set_internal_ref_value(repo_dir, "tag", "v-empty", None)
        _set_internal_ref_value(repo_dir, "tag", "v-good", _internal_ref_value(repo_dir, "branch", "main"))
        _set_internal_ref_value(repo_dir, "tag", "v-broken", "sha256:" + ("0" * 64))

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

    def test_empty_branch_public_listing_and_merge_paths(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        commit = api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"payload")],
            commit_message="seed",
        )
        api.create_branch(branch="empty")

        _set_internal_ref_value(tmp_path / "repo", "branch", "empty", None)

        assert api.list_repo_tree(revision="refs/heads/empty") == []
        assert api.list_repo_commits(revision="refs/heads/empty") == []

        verify_report = api.quick_verify()
        assert verify_report.ok is True
        assert "refs/heads/empty" in verify_report.checked_refs

        empty_source_result = api.merge("empty")
        assert empty_source_result.status == "already-up-to-date"
        assert empty_source_result.source_head is None
        assert empty_source_result.target_head_before == commit.oid
        assert empty_source_result.head_after == commit.oid
        assert empty_source_result.created_commit is False
        assert api.repo_info().head == commit.oid

        empty_target_result = api.merge("main", target_revision="empty")
        assert empty_target_result.status == "fast-forward"
        assert empty_target_result.target_head_before is None
        assert empty_target_result.source_head == commit.oid
        assert empty_target_result.head_after == commit.oid
        assert empty_target_result.created_commit is False
        assert [item.commit_id for item in api.list_repo_commits(revision="refs/heads/empty")] == [
            item.commit_id for item in api.list_repo_commits()
        ]

    def test_list_repo_reflog_returns_empty_when_ref_exists_but_log_file_is_missing(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_branch(branch="temp")

        _delete_reflog_rows(tmp_path / "repo", "branch", "temp")

        assert api.list_repo_reflog("refs/heads/temp") == []

    def test_branch_reflog_updates_survive_blank_and_malformed_last_records(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"payload")],
            commit_message="seed",
        )

        reflog_path = tmp_path / "repo" / "logs" / "refs" / "heads" / "temp.log"
        reflog_path.parent.mkdir(parents=True, exist_ok=True)

        def recreate_temp_branch():
            if "temp" not in [item.name for item in api.list_repo_refs().branches]:
                api.create_branch(branch="temp")

        recreate_temp_branch()
        reflog_path.write_text("\n\n", encoding="utf-8")
        api.delete_branch(branch="temp")
        assert "temp" not in [item.name for item in api.list_repo_refs().branches]

        recreate_temp_branch()
        reflog_path.write_text("[]\n", encoding="utf-8")
        api.delete_branch(branch="temp")
        assert "temp" not in [item.name for item in api.list_repo_refs().branches]

        recreate_temp_branch()
        reflog_path.write_text("{bad json\n", encoding="utf-8")
        api.delete_branch(branch="temp")
        assert "temp" not in [item.name for item in api.list_repo_refs().branches]

    def test_repo_supports_explicit_commit_description_and_hf_style_commit_fallbacks(self, tmp_path):
        api, repo_dir = _single_file_repo(tmp_path, repo_name="commit-fallbacks", payload=b"payload")

        second_commit = api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"payload-v2")],
            parent_commit=api.repo_info().head,
            commit_message="subject line",
            commit_description="body line",
        )

        assert second_commit.commit_message == "subject line"
        assert second_commit.commit_description == "body line"
        assert api.list_repo_commits()[0].title == "subject line"
        assert api.list_repo_commits()[0].message == "body line"

        commit_object_id = _head_commit_id(repo_dir)
        commit_payload = _object_payload(repo_dir, "commits", commit_object_id)
        del commit_payload["title"]
        del commit_payload["description"]
        _set_object_payload(repo_dir, "commits", commit_object_id, commit_payload)

        rebuilt_commit = api.reset_ref("main", to_revision=second_commit.oid)
        assert rebuilt_commit.commit_message == "subject line"
        assert rebuilt_commit.commit_description == "body line"

        history_after_fallback = api.list_repo_commits()
        assert history_after_fallback[0].title == "subject line"
        assert history_after_fallback[0].message == "body line"

        third_commit = api.create_commit(
            operations=[CommitOperationAdd("other.bin", b"payload-v3")],
            parent_commit=second_commit.oid,
            commit_message="empty description",
            commit_description="",
        )
        assert third_commit.commit_message == "empty description"
        assert third_commit.commit_description == ""

        commit_payload = _object_payload(repo_dir, "commits", commit_object_id)
        commit_payload["message"] = ""
        _set_object_payload(repo_dir, "commits", commit_object_id, commit_payload)

        empty_history = api.list_repo_commits(revision=second_commit.oid)
        assert empty_history[0].title == ""
        assert empty_history[0].message == ""

    def test_squash_history_falls_back_to_stored_message_when_title_and_description_are_missing(self, tmp_path):
        api, repo_dir = _single_file_repo(tmp_path, repo_name="squash-fallbacks", payload=b"payload")

        api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"payload-v2")],
            parent_commit=api.repo_info().head,
            commit_message="subject line",
            commit_description="body line",
        )

        commit_object_id = _head_commit_id(repo_dir)
        commit_payload = _object_payload(repo_dir, "commits", commit_object_id)
        del commit_payload["title"]
        del commit_payload["description"]
        _set_object_payload(repo_dir, "commits", commit_object_id, commit_payload)

        report = api.squash_history("main", run_gc=False)

        assert report.ref_name == "refs/heads/main"
        assert api.list_repo_commits()[0].title == "subject line"
        assert api.list_repo_commits()[0].message == "body line"

    def test_repo_only_writers_recover_transactions_and_verify_surfaces_leftovers(self, tmp_path):
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
        assert stale_dir.exists()

        lock_artifact = tmp_path / "repo" / "locks" / "orphaned.lock"
        lock_artifact.mkdir(parents=True)

        report = api.quick_verify()
        assert any("unexpected txn entry: note.txt" in warning for warning in report.warnings)
        assert any("pending transaction directory: stale" in warning for warning in report.warnings)
        assert any("unexpected lock artifact: orphaned.lock" in warning for warning in report.warnings)

        api.create_commit(
            operations=[CommitOperationAdd("recovered.bin", b"x")],
            commit_message="recover leftover txn",
        )

        assert stray_file.is_file()
        assert not stale_dir.exists()

    def test_repo_rolls_back_interrupted_ref_updates_before_serving_reads(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        first_commit = api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"v1")],
            commit_message="seed",
        )
        second_commit = api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"v2")],
            parent_commit=first_commit.oid,
            commit_message="advance",
        )
        api.reset_ref("main", to_revision=first_commit.oid)

        repo_dir = tmp_path / "repo"
        first_internal_head = _internal_ref_value(repo_dir, "branch", "main")
        api.reset_ref("main", to_revision=second_commit.oid)
        second_internal_head = _internal_ref_value(repo_dir, "branch", "main")
        api.reset_ref("main", to_revision=first_commit.oid)
        txdir = repo_dir / "txn" / "interrupted"
        txdir.mkdir(parents=True)
        _write_json(
            txdir / "REF_UPDATE.json",
            {
                "ref_kind": "branch",
                "ref_name": "main",
                "old_head": first_internal_head,
                "new_head": second_internal_head,
                "message": "interrupted advance",
                "ref_existed_before": True,
                "updated_at": "2026-04-07T00:00:00Z",
            },
        )
        _write_json(
            txdir / "STATE.json",
            {
                "state": "UPDATED_REF",
                "updated_at": "2026-04-07T00:00:00Z",
            },
        )

        info = api.repo_info()
        assert info.head == first_commit.oid
        assert api.read_bytes("file.bin") == b"v1"
        assert not txdir.exists()

    def test_public_runtime_failpoints_roll_back_ref_updates_and_history_rewrites(self, tmp_path, monkeypatch):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        base_commit = api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"base\n")],
            commit_message="base",
        )
        api.create_branch(branch="feature")
        _ = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("feature.txt", b"feature\n")],
            commit_message="feature",
        )
        main_commit = api.create_commit(
            operations=[CommitOperationAdd("main.txt", b"main\n")],
            commit_message="main",
        )
        api.create_branch(branch="ephemeral")
        api.create_tag(tag="stable", revision="main")
        api.create_branch(branch="empty-target")
        _set_internal_ref_value(tmp_path / "repo", "branch", "empty-target", None)

        def assert_runtime_failpoint(failpoint, callback):
            with monkeypatch.context() as env:
                env.setenv("HUBVAULT_FAILPOINT", failpoint)
                env.setenv("HUBVAULT_FAIL_ACTION", "raise-runtime")
                with pytest.raises(RuntimeError) as excinfo:
                    callback()
            assert failpoint in str(excinfo.value)

        merge_reflog_before = list(api.list_repo_reflog("main"))
        assert_runtime_failpoint("merge.after_reflog_append", lambda: api.merge("feature"))
        assert api.repo_info().head == main_commit.oid
        assert "feature.txt" not in api.list_repo_files()
        assert api.list_repo_reflog("main") == merge_reflog_before

        assert_runtime_failpoint(
            "merge.after_reflog_append",
            lambda: api.merge("main", target_revision="empty-target"),
        )
        assert api.list_repo_commits(revision="refs/heads/empty-target") == []

        assert_runtime_failpoint("create_branch.after_reflog_append", lambda: api.create_branch(branch="broken-branch"))
        assert "broken-branch" not in [item.name for item in api.list_repo_refs().branches]

        assert_runtime_failpoint("delete_branch.after_reflog_append", lambda: api.delete_branch(branch="ephemeral"))
        assert "ephemeral" in [item.name for item in api.list_repo_refs().branches]

        assert_runtime_failpoint("create_tag.after_reflog_append", lambda: api.create_tag(tag="broken-tag", revision="main"))
        assert "broken-tag" not in [item.name for item in api.list_repo_refs().tags]

        assert_runtime_failpoint("delete_tag.after_reflog_append", lambda: api.delete_tag(tag="stable"))
        assert "stable" in [item.name for item in api.list_repo_refs().tags]

        assert_runtime_failpoint("reset_ref.after_reflog_append", lambda: api.reset_ref("main", to_revision=base_commit.oid))
        assert api.repo_info().head == main_commit.oid

        api.create_branch(branch="ff")
        _ = api.create_commit(
            revision="ff",
            operations=[CommitOperationAdd("ff.txt", b"ff\n")],
            commit_message="ff",
        )
        ff_reflog_before = list(api.list_repo_reflog("main"))
        assert_runtime_failpoint("merge.after_reflog_append", lambda: api.merge("ff"))
        assert api.repo_info().head == main_commit.oid
        assert "ff.txt" not in api.list_repo_files()
        assert api.list_repo_reflog("main") == ff_reflog_before

        history_before_squash = [item.commit_id for item in api.list_repo_commits()]
        assert_runtime_failpoint("squash_history.after_reflog_append", lambda: api.squash_history("main", run_gc=False))
        assert [item.commit_id for item in api.list_repo_commits()] == history_before_squash
        assert api.quick_verify().ok is True

    def test_public_failpoints_support_non_runtime_actions_and_still_roll_back(self, tmp_path, monkeypatch):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"payload\n")],
            commit_message="seed",
        )

        def assert_failpoint(action, expected_exception, branch_name):
            with monkeypatch.context() as env:
                env.setenv("HUBVAULT_FAILPOINT", "create_branch.after_reflog_append")
                env.setenv("HUBVAULT_FAIL_ACTION", action)
                with pytest.raises(expected_exception) as excinfo:
                    api.create_branch(branch=branch_name)
            assert "hubvault failpoint triggered" in str(excinfo.value) or "unknown hubvault fail action" in str(excinfo.value)
            assert branch_name not in [item.name for item in api.list_repo_refs().branches]

        assert_failpoint("raise-oserror", OSError, "broken-oserror")
        assert_failpoint("raise-keyboard", KeyboardInterrupt, "broken-keyboard")
        assert_failpoint("unknown-action", ValueError, "broken-valueerror")

    def test_repo_write_lock_blocks_other_process_readers_and_writers(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("seed.txt", b"seed")],
            commit_message="seed",
        )

        control_dir = tmp_path / "control"
        control_dir.mkdir()
        writer_entered = control_dir / "writer-entered"
        release_writer = control_dir / "release-writer"
        writer_done = control_dir / "writer-done"
        reader_done = control_dir / "reader-done"
        second_writer_done = control_dir / "second-writer-done"

        blocking_writer_code = dedent(
            """
            import io
            import sys
            import time
            from pathlib import Path

            from hubvault import CommitOperationAdd, HubVaultApi

            class BlockingBytesIO(io.BytesIO):
                def __init__(self, payload, entered_path, release_path):
                    io.BytesIO.__init__(self, payload)
                    self._entered_path = Path(entered_path)
                    self._release_path = Path(release_path)

                def read(self, *args, **kwargs):
                    self._entered_path.write_text("entered", encoding="utf-8")
                    while not self._release_path.exists():
                        time.sleep(0.01)
                    return io.BytesIO.read(self, *args, **kwargs)

            repo_path, entered_path, release_path, done_path = sys.argv[1:5]
            api = HubVaultApi(repo_path)
            api.create_commit(
                operations=[CommitOperationAdd("blocked.bin", BlockingBytesIO(b"blocked", entered_path, release_path))],
                commit_message="blocked writer",
            )
            Path(done_path).write_text("done", encoding="utf-8")
            """
        )
        reader_code = dedent(
            """
            import sys
            from pathlib import Path

            from hubvault import HubVaultApi

            repo_path, done_path = sys.argv[1:3]
            data = HubVaultApi(repo_path).read_bytes("seed.txt")
            Path(done_path).write_bytes(data)
            """
        )
        second_writer_code = dedent(
            """
            import sys
            from pathlib import Path

            from hubvault import CommitOperationAdd, HubVaultApi

            repo_path, done_path = sys.argv[1:3]
            HubVaultApi(repo_path).create_commit(
                operations=[CommitOperationAdd("second.bin", b"second")],
                commit_message="second writer",
            )
            Path(done_path).write_text("done", encoding="utf-8")
            """
        )

        env = dict(os.environ)
        repo_root = str(_repo_root())
        env["PYTHONPATH"] = repo_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

        blocking_writer = subprocess.Popen(
            [
                sys.executable,
                "-c",
                blocking_writer_code,
                str(tmp_path / "repo"),
                str(writer_entered),
                str(release_writer),
                str(writer_done),
            ],
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _wait_for_path(writer_entered)

        reader = subprocess.Popen(
            [sys.executable, "-c", reader_code, str(tmp_path / "repo"), str(reader_done)],
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        second_writer = subprocess.Popen(
            [sys.executable, "-c", second_writer_code, str(tmp_path / "repo"), str(second_writer_done)],
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        time.sleep(0.3)
        assert not reader_done.exists()
        assert not second_writer_done.exists()
        assert not writer_done.exists()

        release_writer.write_text("release", encoding="utf-8")

        writer_stdout, writer_stderr = blocking_writer.communicate(timeout=10)
        reader_stdout, reader_stderr = reader.communicate(timeout=10)
        second_writer_stdout, second_writer_stderr = second_writer.communicate(timeout=10)

        assert blocking_writer.returncode == 0, writer_stdout + writer_stderr
        assert reader.returncode == 0, reader_stdout + reader_stderr
        assert second_writer.returncode == 0, second_writer_stdout + second_writer_stderr

        assert writer_done.read_text(encoding="utf-8") == "done"
        assert reader_done.read_bytes() == b"seed"
        assert second_writer_done.read_text(encoding="utf-8") == "done"
        assert api.read_bytes("blocked.bin") == b"blocked"
        assert api.read_bytes("second.bin") == b"second"

    def test_repo_detects_ref_and_config_corruption(self, tmp_path):
        api, repo_dir = _single_file_repo(tmp_path, repo_name="corrupt-refs")

        _set_internal_ref_value(repo_dir, "branch", "main", "broken")
        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files()

        _set_internal_ref_value(repo_dir, "branch", "main", "sha256:")
        with pytest.raises(RevisionNotFoundError):
            api.list_repo_files()

        _set_internal_ref_value(repo_dir, "branch", "main", "sha256:" + ("0" * 64))
        report = api.quick_verify()
        assert report.ok is False
        assert any(item.startswith("refs/heads/main:") for item in report.errors)

        healthy_api, healthy_repo_dir = _single_file_repo(tmp_path, repo_name="corrupt-config")
        _mutate_repo_meta(healthy_repo_dir, "format_version", lambda _value: 999)

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
        file_object_id = _first_object_id(repo_dir, "files")
        _set_object_payload(repo_dir, "files", file_object_id, {})
        with pytest.raises(IntegrityError):
            api.read_bytes("file.bin")

        api, repo_dir = _single_file_repo(tmp_path, repo_name="invalid-tree-entry", payload=b"payload")
        tree_object_id = _head_tree_id(repo_dir)
        tree_payload = _object_payload(repo_dir, "trees", tree_object_id)
        tree_payload["entries"][0]["entry_type"] = "weird"
        _set_object_payload(repo_dir, "trees", tree_object_id, tree_payload)
        with pytest.raises(IntegrityError):
            api.list_repo_files()
        with pytest.raises(IntegrityError):
            api.list_repo_tree()

        api, repo_dir = _single_file_repo(tmp_path, repo_name="missing-commit-object", payload=b"payload")
        _delete_object(repo_dir, "commits", _head_commit_id(repo_dir))
        report = api.quick_verify()
        assert report.ok is False
        assert any(item.startswith("refs/heads/main:") for item in report.errors)

    def test_repo_detects_verify_corruption_cases(self, tmp_path):
        api, repo_dir = _single_file_repo(tmp_path, repo_name="legacy-prefixed-public-sha", payload=b"payload")
        file_object_id = _first_object_id(repo_dir, "files")
        file_payload = _object_payload(repo_dir, "files", file_object_id)
        raw_sha256 = file_payload["sha256"]
        file_payload["sha256"] = "sha256:" + raw_sha256
        _set_object_payload(repo_dir, "files", file_object_id, file_payload)
        assert api.get_paths_info(["file.bin"])[0].sha256 == raw_sha256
        assert api.read_bytes("file.bin") == b"payload"
        assert api.quick_verify().ok is True

        api, repo_dir = _single_file_repo(tmp_path, repo_name="missing-blob-data", payload=b"payload")
        blob_data_path = _only_path(repo_dir / "objects" / "blobs" / "sha256", "*.data")
        blob_data_path.unlink()
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="wrong-file-sha", payload=b"payload")
        file_object_id = _first_object_id(repo_dir, "files")
        file_payload = _object_payload(repo_dir, "files", file_object_id)
        file_payload["sha256"] = "sha256:" + ("1" * 64)
        _set_object_payload(repo_dir, "files", file_object_id, file_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="wrong-blob-sha", payload=b"payload")
        blob_object_id = _first_object_id(repo_dir, "blobs")
        blob_meta = _object_payload(repo_dir, "blobs", blob_object_id)
        blob_meta["payload_sha256"] = "sha256:" + ("2" * 64)
        _set_object_payload(repo_dir, "blobs", blob_object_id, blob_meta)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="wrong-file-oid", payload=b"payload")
        file_object_id = _first_object_id(repo_dir, "files")
        file_payload = _object_payload(repo_dir, "files", file_object_id)
        file_payload["oid"] = "0" * 40
        _set_object_payload(repo_dir, "files", file_object_id, file_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="missing-file-key", payload=b"payload")
        file_object_id = _first_object_id(repo_dir, "files")
        file_payload = _object_payload(repo_dir, "files", file_object_id)
        del file_payload["content_object_id"]
        _set_object_payload(repo_dir, "files", file_object_id, file_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="duplicate-parent", payload=b"payload")
        first_head = _head_commit_id(repo_dir)
        api.create_commit(
            operations=[CommitOperationAdd("file.bin", b"payload-v2")],
            parent_commit=first_head,
            commit_message="second",
        )
        branch_head = _head_commit_id(repo_dir)
        commit_payload = _object_payload(repo_dir, "commits", branch_head)
        first_parent = commit_payload["parents"][0]
        commit_payload["parents"] = [first_parent, first_parent]
        _set_object_payload(repo_dir, "commits", branch_head, commit_payload)
        assert api.quick_verify().ok is True

        api, repo_dir = _single_file_repo(tmp_path, repo_name="weird-tree-entry", payload=b"payload")
        tree_object_id = _head_tree_id(repo_dir)
        tree_payload = _object_payload(repo_dir, "trees", tree_object_id)
        tree_payload["entries"][0]["entry_type"] = "weird"
        _set_object_payload(repo_dir, "trees", tree_object_id, tree_payload)
        report = api.quick_verify()
        assert report.ok is False

        api, repo_dir = _single_file_repo(tmp_path, repo_name="malformed-tree", payload=b"payload")
        tree_object_id = _head_tree_id(repo_dir)
        tree_payload = _object_payload(repo_dir, "trees", tree_object_id)
        tree_payload["entries"] = [{}]
        _set_object_payload(repo_dir, "trees", tree_object_id, tree_payload)
        report = api.quick_verify()
        assert report.ok is False

    def test_repo_conflict_and_missing_path_cases(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[
                    CommitOperationAdd("dup.txt", b"a"),
                    CommitOperationAdd("dup.txt/child.txt", b"b"),
                ],
                commit_message="invalid hierarchy",
            )

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[
                    CommitOperationAdd("Case.txt", b"a"),
                    CommitOperationAdd("case.txt", b"b"),
                ],
                commit_message="case clash",
            )

        baseline = api.create_commit(
            operations=[CommitOperationAdd("data/file.txt", b"v1")],
            commit_message="seed",
        )

        copied = api.create_commit(
            operations=[CommitOperationCopy("data/file.txt", "data/copied.txt", src_revision=baseline.oid)],
            parent_commit=baseline.oid,
            commit_message="copy single file",
        )
        assert _is_git_oid(copied.oid)
        assert api.read_bytes("data/copied.txt") == b"v1"

        deleted = api.create_commit(
            operations=[CommitOperationDelete("data/copied.txt", is_folder=False)],
            parent_commit=copied.oid,
            commit_message="delete single file",
        )
        assert _is_git_oid(deleted.oid)
        with pytest.raises(EntryNotFoundError):
            api.read_bytes("data/copied.txt")

        with pytest.raises(EntryNotFoundError):
            api.create_commit(
                operations=[CommitOperationDelete("missing.txt", is_folder=False)],
                parent_commit=deleted.oid,
                commit_message="missing delete",
            )

        with pytest.raises(EntryNotFoundError):
            api.create_commit(
                operations=[CommitOperationDelete("missing-folder/", is_folder=True)],
                parent_commit=deleted.oid,
                commit_message="missing folder delete",
            )

        with pytest.raises(EntryNotFoundError):
            api.create_commit(
                operations=[CommitOperationCopy("missing.txt", "copied.txt")],
                parent_commit=deleted.oid,
                commit_message="missing copy",
            )

        with pytest.raises(RevisionNotFoundError):
            api.reset_ref("main", to_revision="missing")

    def test_snapshot_views_are_rebuilt_and_reported_as_stale_when_modified(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        snapshot_dir = Path(api.snapshot_download())
        snapshot_file = snapshot_dir / "bundle" / "file.bin"
        assert snapshot_file.read_bytes() == b"payload-v1"

        snapshot_file.write_bytes(b"tampered")
        report = api.quick_verify()
        assert report.ok is True
        assert any("stale snapshot view" in warning for warning in report.warnings)

        rebuilt_snapshot_dir = Path(api.snapshot_download())
        rebuilt_snapshot_file = rebuilt_snapshot_dir / "bundle" / "file.bin"
        assert rebuilt_snapshot_dir == snapshot_dir
        assert rebuilt_snapshot_file.read_bytes() == b"payload-v1"

        rebuilt_snapshot_file.unlink()
        missing_report = api.quick_verify()
        assert any("stale snapshot view" in warning for warning in missing_report.warnings)

    def test_managed_snapshot_view_rebuilds_for_missing_mismatched_and_malformed_metadata(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        repo_dir = tmp_path / "repo"
        snapshot_dir = Path(api.snapshot_download())
        snapshot_file = snapshot_dir / "bundle" / "file.bin"
        meta_path = _only_path(repo_dir / "cache" / "views" / "snapshots", "*.json")

        def assert_snapshot_rebuilt(expected_warning=None):
            if expected_warning is None:
                rebuilt = Path(api.snapshot_download())
            else:
                with warnings.catch_warnings(record=True) as records:
                    warnings.simplefilter("always")
                    rebuilt = Path(api.snapshot_download())
                assert any(expected_warning in str(item.message) for item in records)
            assert rebuilt == snapshot_dir
            assert snapshot_file.read_bytes() == b"payload-v1"

        meta_path.unlink()
        assert_snapshot_rebuilt()

        for field, replacement in (
            ("allow_patterns", ["*.txt"]),
            ("ignore_patterns", ["*.bin"]),
        ):
            metadata = _read_json(meta_path)
            metadata[field] = replacement
            _write_json(meta_path, metadata)
            assert_snapshot_rebuilt()

        metadata = _read_json(meta_path)
        metadata["files"] = {}
        _write_json(meta_path, metadata)
        assert_snapshot_rebuilt("Ignoring malformed detached snapshot metadata")

        metadata = _read_json(meta_path)
        metadata["files"] = ["bad-entry"]
        _write_json(meta_path, metadata)
        assert_snapshot_rebuilt("Ignoring malformed detached snapshot metadata")

        metadata = _read_json(meta_path)
        metadata["files"][0]["size"] = "invalid"
        _write_json(meta_path, metadata)

        report = api.quick_verify()
        assert report.ok is True
        assert not any("stale snapshot view" in warning for warning in report.warnings)

        assert_snapshot_rebuilt()

    def test_snapshot_download_warns_when_detached_snapshot_metadata_is_malformed(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        snapshot_dir = tmp_path / "external-snapshot"
        metadata_path = snapshot_dir / ".cache" / "hubvault" / "snapshot.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text("{bad json", encoding="utf-8")

        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")
            exported = Path(api.snapshot_download(local_dir=snapshot_dir))

        assert exported == snapshot_dir
        assert (exported / "bundle" / "file.bin").read_bytes() == b"payload-v1"
        assert any("Ignoring malformed detached snapshot metadata" in str(item.message) for item in records)

    def test_repo_rejects_malformed_ref_update_journal_during_recovery(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        txdir = tmp_path / "repo" / "txn" / "broken"
        txdir.mkdir(parents=True)
        (txdir / "REF_UPDATE.json").write_text("{bad json", encoding="utf-8")

        assert api.read_bytes("bundle/file.bin") == b"payload-v1"
        assert not txdir.exists()
        assert api.quick_verify().ok is True

    def test_upload_folder_delete_patterns_and_deleted_ref_reflogs_work_via_public_api(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"root", path_in_repo="root.txt")

        initial_source = tmp_path / "source-v1"
        initial_source.mkdir()
        (initial_source / "keep.txt").write_bytes(b"keep-v1\n")
        (initial_source / "drop.txt").write_bytes(b"drop-v1\n")
        api.upload_folder(folder_path=initial_source, path_in_repo="bundle")

        updated_source = tmp_path / "source-v2"
        updated_source.mkdir()
        (updated_source / "keep.txt").write_bytes(b"keep-v2\n")
        (updated_source / "new.txt").write_bytes(b"new-v2\n")
        (updated_source / ".git").mkdir()
        (updated_source / ".git" / "ignored.txt").write_bytes(b"ignored\n")

        api.upload_folder(
            folder_path=updated_source,
            path_in_repo="bundle",
            delete_patterns="*.txt",
        )

        assert api.list_repo_files() == [
            "bundle/keep.txt",
            "bundle/new.txt",
            "root.txt",
        ]
        assert api.read_bytes("bundle/keep.txt") == b"keep-v2\n"
        assert api.read_bytes("bundle/new.txt") == b"new-v2\n"

        current_head = api.repo_info().head
        api.create_branch(branch="dev", revision=current_head)
        api.create_tag(tag="release", revision=current_head)
        api.delete_branch(branch="dev")
        api.delete_tag(tag="release")

        branch_reflog = api.list_repo_reflog("refs/heads/dev")
        tag_reflog = api.list_repo_reflog("refs/tags/release")

        assert [item.message for item in branch_reflog] == ["delete branch", "create branch"]
        assert branch_reflog[0].new_head is None
        assert branch_reflog[1].new_head == current_head
        assert [item.message for item in tag_reflog] == ["delete tag", "create tag"]
        assert tag_reflog[0].new_head is None
        assert api.list_repo_reflog("release")[0].ref_name == "refs/tags/release"

        with pytest.raises(UnsupportedPathError):
            api.hf_hub_download("root.txt", local_dir=tmp_path / "repo" / "unsafe")

        snapshot_dir = tmp_path / "managed-snapshot"
        first_snapshot = Path(api.snapshot_download(local_dir=snapshot_dir))
        assert (first_snapshot / "bundle" / "new.txt").read_bytes() == b"new-v2\n"

        api.delete_folder("bundle")
        rebuilt_snapshot = Path(api.snapshot_download(local_dir=snapshot_dir))
        assert rebuilt_snapshot == first_snapshot
        assert not (rebuilt_snapshot / "bundle" / "new.txt").exists()
        assert not (rebuilt_snapshot / "bundle").exists()

    def test_phase3_range_reads_can_succeed_without_rebuilding_missing_later_chunks(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo(large_file_threshold=64)

        large_payload = (
            (b"A" * DEFAULT_CHUNK_SIZE)
            + (b"B" * DEFAULT_CHUNK_SIZE)
            + (b"C" * DEFAULT_CHUNK_SIZE)
            + (b"D" * DEFAULT_CHUNK_SIZE)
            + (b"E" * DEFAULT_CHUNK_SIZE)
            + (b"F" * 1024)
        )
        api.create_commit(
            operations=[CommitOperationAdd("artifacts/large.bin", large_payload)],
            commit_message="seed chunked file",
        )

        pack_path = _only_path(tmp_path / "repo" / "chunks" / "packs", "*.pack")
        index_records = _load_index_records(tmp_path / "repo")
        assert len(index_records) >= 2
        first_index_record = index_records[0]
        first_chunk_limit = int(first_index_record["offset"]) + int(first_index_record["stored_size"])
        pack_path.write_bytes(pack_path.read_bytes()[:first_chunk_limit])

        assert api.read_range("artifacts/large.bin", start=0, length=1024) == b"A" * 1024

        with pytest.raises(IntegrityError):
            api.read_bytes("artifacts/large.bin")

        report = api.quick_verify()
        assert report.ok is False
        assert any("pack truncated" in item for item in report.errors)
