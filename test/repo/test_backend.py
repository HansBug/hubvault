import json
import sqlite3
import shutil
import warnings
from pathlib import Path

import pytest

from hubvault import (
    CommitOperationAdd,
    ConflictError,
    EntryNotFoundError,
    HubVaultApi,
    IntegrityError,
    RepositoryAlreadyExistsError,
    RevisionNotFoundError,
    UnsupportedPathError,
    VerificationError,
)
from hubvault.repo.sqlite import SQLITE_METADATA_FILENAME
from hubvault.storage.chunk import DEFAULT_CHUNK_SIZE


def _only_path(root, pattern):
    matches = sorted(Path(root).rglob(pattern))
    assert len(matches) == 1
    return matches[0]


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _chunked_repo(tmp_path, repo_name):
    repo_dir = tmp_path / repo_name
    api = HubVaultApi(repo_dir)
    api.create_repo(large_file_threshold=64)
    payload = (b"A" * DEFAULT_CHUNK_SIZE) + (b"B" * 512)
    api.create_commit(
        operations=[CommitOperationAdd("artifacts/large.bin", payload)],
        commit_message="seed chunked backend test",
    )
    return api, repo_dir, payload


def _file_object_path(repo_dir):
    with sqlite3.connect(str(Path(repo_dir) / SQLITE_METADATA_FILENAME)) as conn:
        row = conn.execute("SELECT object_id FROM objects_files ORDER BY object_id LIMIT 1").fetchone()
    assert row is not None
    return str(row[0])


def _first_object_path(repo_dir, object_type):
    table = {
        "commits": "objects_commits",
        "trees": "objects_trees",
        "files": "objects_files",
        "blobs": "objects_blobs",
    }[object_type]
    with sqlite3.connect(str(Path(repo_dir) / SQLITE_METADATA_FILENAME)) as conn:
        row = conn.execute("SELECT object_id FROM %s ORDER BY object_id LIMIT 1" % table).fetchone()
    assert row is not None
    return str(row[0])


def _repo_db_path(repo_dir):
    return Path(repo_dir) / SQLITE_METADATA_FILENAME


def _object_table(object_type):
    return {
        "commits": "objects_commits",
        "trees": "objects_trees",
        "files": "objects_files",
        "blobs": "objects_blobs",
    }[object_type]


def _mutate_object_payload(repo_dir, object_type, object_id, mutator):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        row = conn.execute(
            "SELECT payload_json FROM %s WHERE object_id = ?" % _object_table(object_type),
            (object_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        mutator(payload)
        conn.execute(
            "UPDATE %s SET payload_json = ? WHERE object_id = ?" % _object_table(object_type),
            (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), object_id),
        )
        conn.commit()


def _mutate_file_payload(repo_dir, mutator):
    _mutate_object_payload(repo_dir, "files", _file_object_path(repo_dir), mutator)


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


def _mutate_first_index_record(repo_dir, mutator):
    records = _load_index_records(repo_dir)
    mutator(records[0])
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        conn.execute("DELETE FROM chunk_visible")
        conn.executemany(
            """
            INSERT INTO chunk_visible (
                chunk_id,
                pack_id,
                offset,
                stored_size,
                logical_size,
                compression,
                checksum
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record["chunk_id"],
                    record["pack_id"],
                    record["offset"],
                    record["stored_size"],
                    record["logical_size"],
                    record["compression"],
                    record["checksum"],
                )
                for record in records
            ],
        )
        conn.commit()


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
            "UPDATE refs SET commit_id = ? WHERE ref_kind = ? AND ref_name = ?",
            (commit_id, ref_kind, ref_name),
        )
        conn.commit()


def _mutate_repo_meta(repo_dir, key, mutator):
    with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
        row = conn.execute("SELECT value_json FROM repo_meta WHERE key = ?", (key,)).fetchone()
        assert row is not None
        value = json.loads(row[0])
        value = mutator(value)
        conn.execute(
            "UPDATE repo_meta SET value_json = ? WHERE key = ?",
            (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False), key),
        )
        conn.commit()


def _remove_tree(path):
    def handle_readonly(func, failing_path, _exc_info):
        Path(failing_path).chmod(0o700)
        func(failing_path)

    shutil.rmtree(path, onerror=handle_readonly)


@pytest.mark.unittest
class TestRepoBackendPackage:
    def test_repo_backend_split_preserves_public_api_behavior(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo(large_file_threshold=32)
        api.create_commit(
            operations=[CommitOperationAdd("folder/demo.txt", b"hello from backend package")],
            commit_message="seed backend package",
        )

        assert api.list_repo_files() == ["folder/demo.txt"]
        assert api.read_bytes("folder/demo.txt") == b"hello from backend package"
        assert api.quick_verify().ok is True

    def test_backend_create_repo_validates_threshold_and_lock_artifacts(self, tmp_path):
        with pytest.raises(ValueError):
            HubVaultApi(tmp_path / "bad-threshold").create_repo(large_file_threshold=0)

        occupied_dir = tmp_path / "occupied"
        (occupied_dir / "locks" / "orphaned.lock").mkdir(parents=True)
        with pytest.raises(RepositoryAlreadyExistsError):
            HubVaultApi(occupied_dir).create_repo()

    def test_backend_public_range_reads_cover_boundaries_and_missing_paths(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo(large_file_threshold=64)
        payload = (b"A" * DEFAULT_CHUNK_SIZE) + (b"B" * 512)
        api.create_commit(
            operations=[CommitOperationAdd("artifacts/large.bin", payload)],
            commit_message="seed range edges",
        )

        with pytest.raises(ValueError):
            api.read_range("artifacts/large.bin", start=-1, length=1)

        with pytest.raises(ValueError):
            api.read_range("artifacts/large.bin", start=0, length=-1)

        with pytest.raises(EntryNotFoundError):
            api.read_range("artifacts/missing.bin", start=0, length=1)

        assert api.read_range("artifacts/large.bin", start=len(payload), length=64) == b""
        assert api.read_range("artifacts/large.bin", start=0, length=0) == b""

    def test_backend_public_range_reads_cover_whole_blob_files(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("notes.txt", b"hello")],
            commit_message="seed whole blob",
        )

        assert api.read_range("notes.txt", start=1, length=3) == b"ell"

    @pytest.mark.parametrize(
        ("main_path", "feature_path", "expected_type", "expected_related_path"),
        [
            ("artifact", "artifact/model.bin", "file/directory", "artifact/model.bin"),
            ("Model.bin", "model.bin", "case-fold", "model.bin"),
        ],
    )
    def test_backend_merge_reports_structural_conflicts_without_partial_state(
        self,
        tmp_path,
        main_path,
        feature_path,
        expected_type,
        expected_related_path,
    ):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("seed.txt", b"seed")],
            commit_message="seed structural merge",
        )
        api.create_branch(branch="feature")
        api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd(feature_path, b"feature")],
            commit_message="feature path",
        )
        main_commit = api.create_commit(
            operations=[CommitOperationAdd(main_path, b"main")],
            commit_message="main path",
        )

        result = api.merge("feature")

        assert result.status == "conflict"
        assert result.commit is None
        assert result.head_after == main_commit.oid
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == expected_type
        assert result.conflicts[0].related_path == expected_related_path
        assert api.repo_info().head == main_commit.oid

    @pytest.mark.parametrize(
        ("case_name", "expected_message"),
        [
            ("missing-index", "chunk missing from index"),
            ("logical-size", "chunk logical size mismatch"),
            ("unsupported-compression", "unsupported chunk compression"),
            ("stored-size", "chunk size mismatch"),
            ("chunk-checksum", "chunk checksum mismatch"),
            ("index-checksum", "chunk index checksum mismatch"),
        ],
    )
    def test_backend_chunked_reads_detect_index_and_pack_corruption(
        self,
        tmp_path,
        case_name,
        expected_message,
    ):
        api, repo_dir, _ = _chunked_repo(tmp_path, case_name)

        if case_name == "missing-index":
            _mutate_file_payload(
                repo_dir,
                lambda payload: payload["chunks"][0].__setitem__("chunk_id", "sha256:" + ("0" * 64)),
            )
        elif case_name == "logical-size":
            _mutate_first_index_record(
                repo_dir,
                lambda record: record.__setitem__("logical_size", int(record["logical_size"]) - 1),
            )
        elif case_name == "unsupported-compression":
            _mutate_first_index_record(
                repo_dir,
                lambda record: record.__setitem__("compression", "gzip"),
            )
        elif case_name == "stored-size":
            _mutate_first_index_record(
                repo_dir,
                lambda record: record.__setitem__("stored_size", int(record["stored_size"]) - 1),
            )
        elif case_name == "chunk-checksum":
            _mutate_file_payload(
                repo_dir,
                lambda payload: payload["chunks"][0].__setitem__("checksum", "sha256:" + ("1" * 64)),
            )
        else:
            _mutate_first_index_record(
                repo_dir,
                lambda record: record.__setitem__("checksum", "sha256:" + ("2" * 64)),
            )

        with pytest.raises(IntegrityError, match=expected_message):
            api.read_range("artifacts/large.bin", start=0, length=128)

    @pytest.mark.parametrize(
        ("field_name", "field_value", "expected_message"),
        [
            ("sha256", "0" * 64, "file sha256 mismatch"),
            ("oid", "0" * 40, "file oid mismatch"),
            ("etag", "1" * 64, "file etag mismatch"),
        ],
    )
    def test_backend_chunked_reads_detect_file_metadata_corruption(
        self,
        tmp_path,
        field_name,
        field_value,
        expected_message,
    ):
        api, repo_dir, _ = _chunked_repo(tmp_path, field_name)

        _mutate_file_payload(
            repo_dir,
            lambda payload: payload.__setitem__(field_name, field_value),
        )

        with pytest.raises(IntegrityError, match=expected_message):
            api.read_bytes("artifacts/large.bin")

    @pytest.mark.parametrize(
        ("field_name", "field_mutator", "expected_message"),
        [
            ("logical_size", lambda payload, data_length: payload.__setitem__("logical_size", data_length + 1), "file logical size mismatch"),
            ("pointer_size", lambda payload, _data_length: payload.__setitem__("pointer_size", int(payload["pointer_size"]) + 1), "file pointer size mismatch"),
        ],
    )
    def test_backend_quick_verify_reports_chunked_file_metadata_mismatches(
        self,
        tmp_path,
        field_name,
        field_mutator,
        expected_message,
    ):
        api, repo_dir, payload = _chunked_repo(tmp_path, "verify-" + field_name)

        _mutate_file_payload(
            repo_dir,
            lambda file_payload: field_mutator(file_payload, len(payload)),
        )

        report = api.quick_verify()
        assert report.ok is False
        assert any(expected_message in item for item in report.errors)

    def test_backend_snapshot_metadata_warning_and_gitattributes_preservation(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(
            path_or_fileobj=b"*.bin filter=lfs diff=lfs merge=lfs -text\n",
            path_in_repo=".gitattributes",
        )

        initial_source = tmp_path / "source-v1"
        initial_source.mkdir()
        (initial_source / "old.txt").write_text("old\n", encoding="utf-8")
        api.upload_folder(folder_path=initial_source)

        snapshot_dir = tmp_path / "snapshot"
        metadata_path = snapshot_dir / ".cache" / "hubvault" / "snapshot.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text('{"files":{}}', encoding="utf-8")

        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")
            exported = Path(api.snapshot_download(local_dir=snapshot_dir))

        assert exported == snapshot_dir
        assert (exported / ".gitattributes").read_bytes().startswith(b"*.bin")
        assert any("Ignoring malformed detached snapshot metadata" in str(item.message) for item in records)

        metadata_path.write_text("[]", encoding="utf-8")
        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")
            exported = Path(api.snapshot_download(local_dir=snapshot_dir))

        assert exported == snapshot_dir
        assert any("Ignoring malformed detached snapshot metadata" in str(item.message) for item in records)

        updated_source = tmp_path / "source-v2"
        updated_source.mkdir()
        (updated_source / "new.txt").write_text("new\n", encoding="utf-8")
        api.upload_folder(folder_path=updated_source, delete_patterns="*")

        assert api.list_repo_files() == [".gitattributes", "new.txt"]

    @pytest.mark.parametrize(
        ("ref_kind", "ref_name", "ref_path_parts"),
        [
            ("branch", "temp", ("refs", "heads", "temp")),
            ("tag", "release", ("refs", "tags", "release")),
        ],
    )
    def test_backend_ref_recovery_removes_created_branch_and_tag_refs(
        self,
        tmp_path,
        ref_kind,
        ref_name,
        ref_path_parts,
    ):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        repo_dir = tmp_path / "repo"
        internal_head = _internal_ref_value(repo_dir, "branch", "main")
        ref_path = repo_dir.joinpath(*ref_path_parts)
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(internal_head + "\n", encoding="utf-8")

        txdir = repo_dir / "txn" / ("recover-" + ref_kind)
        txdir.mkdir(parents=True)
        _write_json(
            txdir / "REF_UPDATE.json",
            {
                "ref_kind": ref_kind,
                "ref_name": ref_name,
                "old_head": None,
                "new_head": internal_head,
                "message": "create %s" % ref_kind,
                "ref_existed_before": False,
            },
        )

        assert api.read_bytes("bundle/file.bin") == b"payload-v1"
        refs = api.list_repo_refs()
        if ref_kind == "tag":
            assert refs.tags == []
        else:
            assert [item.name for item in refs.branches] == ["main"]
        assert not txdir.exists()

    def test_backend_write_paths_clean_empty_transaction_directory(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        txdir = tmp_path / "repo" / "txn" / "empty"
        txdir.mkdir(parents=True)

        assert api.read_bytes("bundle/file.bin") == b"payload-v1"
        assert any("pending transaction directory: empty" in item for item in api.quick_verify().warnings)

        api.upload_file(path_or_fileobj=b"payload-v2", path_in_repo="bundle/second.bin")
        assert not txdir.exists()

    @pytest.mark.parametrize(
        ("journal_payload", "expected_message"),
        [
            ([], "expected JSON object"),
            ({"ref_kind": "branch"}, "missing ref_name"),
            (
                {
                    "ref_kind": "branch",
                    "ref_name": "main",
                    "old_head": 1,
                    "ref_existed_before": True,
                },
                "old_head must be a string or null",
            ),
            (
                {
                    "ref_kind": "branch",
                    "ref_name": "main",
                    "old_head": None,
                    "ref_existed_before": "yes",
                },
                "ref_existed_before must be a boolean",
            ),
            (
                {
                    "ref_kind": "weird",
                    "ref_name": "main",
                    "old_head": None,
                    "ref_existed_before": False,
                },
                "ref_kind must be 'branch' or 'tag'",
            ),
        ],
    )
    def test_backend_ref_recovery_rejects_malformed_journals(
        self,
        tmp_path,
        journal_payload,
        expected_message,
    ):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        txdir = tmp_path / "repo" / "txn" / "broken"
        txdir.mkdir(parents=True)
        _write_json(txdir / "REF_UPDATE.json", journal_payload)

        assert api.read_bytes("bundle/file.bin") == b"payload-v1"
        assert not txdir.exists()

    @pytest.mark.parametrize("state_text", ["{bad json", "[]"])
    def test_backend_ref_recovery_rolls_back_when_state_file_is_not_usable(self, tmp_path, state_text):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        first_commit = api.upload_file(path_or_fileobj=b"v1", path_in_repo="bundle/file.bin")
        second_commit = api.upload_file(path_or_fileobj=b"v2", path_in_repo="bundle/file.bin")

        repo_dir = tmp_path / "repo"
        api.reset_ref("main", to_revision=first_commit.oid)
        first_internal_head = _internal_ref_value(repo_dir, "branch", "main")
        api.reset_ref("main", to_revision=second_commit.oid)
        second_internal_head = _internal_ref_value(repo_dir, "branch", "main")
        api.reset_ref("main", to_revision=first_commit.oid)

        txdir = repo_dir / "txn" / "broken-state"
        txdir.mkdir(parents=True)
        _write_json(
            txdir / "REF_UPDATE.json",
            {
                "ref_kind": "branch",
                "ref_name": "main",
                "old_head": first_internal_head,
                "new_head": second_internal_head,
                "message": "advance with broken state",
                "ref_existed_before": True,
            },
        )
        (txdir / "STATE.json").write_text(state_text, encoding="utf-8")

        assert api.repo_info().head == first_commit.oid
        assert api.read_bytes("bundle/file.bin") == b"v1"
        assert not txdir.exists()

    def test_backend_full_verify_surfaces_corruption_recovery_and_view_warnings(self, tmp_path):
        api, repo_dir, _ = _chunked_repo(tmp_path, "full-verify")
        api.create_tag(tag="v1")

        download_path = Path(api.hf_hub_download("artifacts/large.bin"))
        snapshot_dir = Path(api.snapshot_download())
        download_path.write_bytes(b"corrupted detached view")
        (snapshot_dir / "artifacts" / "large.bin").unlink()

        broken_txdir = repo_dir / "txn" / "broken-recovery"
        broken_txdir.mkdir(parents=True)
        _write_json(
            broken_txdir / "REF_UPDATE.json",
            {
                "ref_kind": "branch",
                "ref_name": "main",
                "old_head": 1,
                "new_head": None,
                "message": "broken recovery journal",
                "ref_existed_before": True,
            },
        )

        pending_txdir = repo_dir / "txn" / "pending-dir"
        pending_txdir.mkdir(parents=True)
        (repo_dir / "txn" / "manual-note.txt").write_text("leftover", encoding="utf-8")
        (repo_dir / "locks" / "unexpected.lock").write_text("lock", encoding="utf-8")
        with sqlite3.connect(str(_repo_db_path(repo_dir))) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO refs (ref_kind, ref_name, commit_id, updated_at) VALUES (?, ?, ?, ?)",
                ("branch", "broken", "sha256:" + ("0" * 64), "2024-01-01T00:00:00Z"),
            )
            conn.commit()

        _mutate_repo_meta(repo_dir, "format_version", lambda _value: 999)

        tree_object_id = _first_object_path(repo_dir, "trees")
        _mutate_object_payload(
            repo_dir,
            "trees",
            tree_object_id,
            lambda payload: payload.__setitem__("git_oid", "invalid-tree-oid"),
        )

        _mutate_first_index_record(
            repo_dir,
            lambda record: record.__setitem__("compression", "gzip"),
        )

        report = api.full_verify()

        assert report.ok is False
        assert any("unsupported format version" in item for item in report.errors)
        assert any("refs/heads/broken:" in item for item in report.errors)
        assert any("tree " in item for item in report.errors)
        assert any("chunk storage: unsupported chunk compression: gzip" in item for item in report.errors)
        assert any("stale file view:" in item for item in report.warnings)
        assert any("stale snapshot view:" in item for item in report.warnings)
        assert any("unexpected txn entry: manual-note.txt" in item for item in report.warnings)
        assert any("unexpected lock artifact: unexpected.lock" in item for item in report.warnings)
        assert not pending_txdir.exists()

    def test_backend_storage_overview_and_gc_cover_blob_only_and_manual_areas(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        _ = api.upload_file(path_or_fileobj=b"v1", path_in_repo="bundle/file.bin")
        _ = api.upload_file(path_or_fileobj=b"v2", path_in_repo="bundle/file.bin")
        _ = api.hf_hub_download("bundle/file.bin")

        _remove_tree(repo_dir / "quarantine")
        _remove_tree(repo_dir / "cache")
        (repo_dir / "txn" / "manual-note.txt").write_text("manual", encoding="utf-8")
        (repo_dir / "quarantine" / "objects" / "manual" / "old.bin").parent.mkdir(parents=True, exist_ok=True)
        (repo_dir / "quarantine" / "objects" / "manual" / "old.bin").write_bytes(b"old")

        overview = api.get_storage_overview()

        assert overview.historical_retained_size > 0
        assert any("squash_history" in item for item in overview.recommendations)
        assert any("txn/" in item for item in overview.recommendations)
        assert any("quarantine/" in item for item in overview.recommendations)

        preview = api.gc(dry_run=True, prune_cache=True)
        assert preview.dry_run is True
        assert any("Rollback history still retains" in item for item in preview.notes)

        actual = api.gc(dry_run=False, prune_cache=True)
        assert actual.dry_run is False
        assert actual.reclaimed_temporary_size > 0
        assert (repo_dir / "txn" / "manual-note.txt").exists()
        assert api.full_verify().ok is True

    def test_backend_gc_rejects_corrupted_repositories_before_reclaiming(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload", path_in_repo="bundle/file.bin")

        tree_object_id = _first_object_path(tmp_path / "repo", "trees")
        _mutate_object_payload(
            tmp_path / "repo",
            "trees",
            tree_object_id,
            lambda payload: payload.__setitem__("git_oid", "broken-git-oid"),
        )

        with pytest.raises(VerificationError, match="repository verification failed"):
            api.gc(dry_run=True)

    def test_backend_squash_history_covers_public_edge_cases_and_custom_root_metadata(self, tmp_path):
        empty_repo_dir = tmp_path / "empty-repo"
        empty_api = HubVaultApi(empty_repo_dir)
        empty_api.create_repo()
        empty_api.create_branch(branch="empty")
        _set_internal_ref_value(empty_repo_dir, "branch", "empty", None)

        with pytest.raises(RevisionNotFoundError, match="revision has no commits yet: empty"):
            empty_api.squash_history("empty", run_gc=False)

        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        first = api.create_commit(
            operations=[CommitOperationAdd("bundle/file.bin", b"v1")],
            commit_message="seed v1",
        )
        second = api.create_commit(
            operations=[CommitOperationAdd("bundle/file.bin", b"v2")],
            commit_message="seed v2",
        )
        third = api.create_commit(
            operations=[CommitOperationAdd("bundle/file.bin", b"v3")],
            commit_message="seed v3",
        )
        api.create_branch(branch="side", revision=first.oid)
        side_commit = api.create_commit(
            revision="side",
            operations=[CommitOperationAdd("bundle/side.bin", b"side")],
            commit_message="side branch",
        )
        api.create_tag(tag="v1", revision=first.oid)

        with pytest.raises(UnsupportedPathError, match="only supports branch refs"):
            api.squash_history("refs/tags/v1", run_gc=False)

        with pytest.raises(ConflictError, match="root_revision is not an ancestor"):
            api.squash_history("main", root_revision=side_commit.oid, run_gc=False)

        report = api.squash_history(
            "refs/heads/main",
            root_revision=first.oid,
            commit_message="squashed root",
            commit_description="manual body",
            run_gc=False,
        )

        history = list(api.list_repo_commits())
        assert report.ref_name == "refs/heads/main"
        assert report.old_head == third.oid
        assert report.new_head != third.oid
        assert report.root_commit_before == first.oid
        assert report.rewritten_commit_count == 3
        assert report.dropped_ancestor_count == 1
        assert history[-1].title == "squashed root"
        assert history[-1].message == "manual body"
        assert api.read_bytes("bundle/file.bin") == b"v3"

    def test_backend_nested_ref_cleanup_and_missing_explicit_reflog_queries(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload", path_in_repo="bundle/file.bin")
        api.create_branch(branch="team/one")
        api.create_branch(branch="team/two")

        api.delete_branch(branch="team/one")

        assert [ref.name for ref in api.list_repo_refs().branches] == ["main", "team/two"]

        with pytest.raises(RevisionNotFoundError, match="reflog not found: refs/heads/missing"):
            api.list_repo_reflog("refs/heads/missing")
        with pytest.raises(RevisionNotFoundError, match="reflog not found: refs/tags/missing"):
            api.list_repo_reflog("refs/tags/missing")

    def test_backend_tag_recovery_restores_previous_tag_head(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        first = api.upload_file(path_or_fileobj=b"v1", path_in_repo="bundle/file.bin")
        api.create_tag(tag="release", revision=first.oid)
        second = api.upload_file(path_or_fileobj=b"v2", path_in_repo="bundle/file.bin")

        repo_dir = tmp_path / "repo"
        first_tag_internal = _internal_ref_value(repo_dir, "tag", "release")
        second_internal_head = _internal_ref_value(repo_dir, "branch", "main")
        _set_internal_ref_value(repo_dir, "tag", "release", second_internal_head)
        txdir = repo_dir / "txn" / "tag-rollback"
        txdir.mkdir(parents=True)
        _write_json(
            txdir / "REF_UPDATE.json",
            {
                "ref_kind": "tag",
                "ref_name": "release",
                "old_head": first_tag_internal,
                "new_head": second_internal_head,
                "message": "retag release",
                "ref_existed_before": True,
            },
        )

        assert api.read_bytes("bundle/file.bin") == b"v2"
        assert api.list_repo_refs().tags[0].target_commit == second.oid
        assert not txdir.exists()

    def test_backend_public_pattern_filters_and_blank_reflog_lines_work(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[
                CommitOperationAdd("nested/keep.txt", b"keep"),
                CommitOperationAdd("nested/ignore.txt", b"ignore"),
                CommitOperationAdd("root.txt", b"root"),
            ],
            commit_message="seed pattern filters",
        )

        snapshot_dir = Path(
            api.snapshot_download(
                allow_patterns="nested/",
                ignore_patterns="nested/ignore.txt",
            )
        )
        assert (snapshot_dir / "nested" / "keep.txt").read_bytes() == b"keep"
        assert not (snapshot_dir / "nested" / "ignore.txt").exists()
        assert not (snapshot_dir / "root.txt").exists()

        assert api.list_repo_reflog("main")[0].message == "seed pattern filters"

    def test_backend_full_verify_handles_empty_heads_and_stale_snapshot_content(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_branch(branch="empty")

        empty_report = api.full_verify()
        assert empty_report.ok is True
        assert "refs/heads/empty" in empty_report.checked_refs

        api.upload_file(path_or_fileobj=b"payload", path_in_repo="bundle/file.bin")
        snapshot_dir = Path(api.snapshot_download())
        (snapshot_dir / "bundle" / "file.bin").write_bytes(b"mutated snapshot")

        stale_report = api.full_verify()
        assert stale_report.ok is True
        assert any("stale snapshot view:" in item for item in stale_report.warnings)

    def test_backend_missing_ref_and_txn_roots_do_not_break_public_operations(self, tmp_path):
        empty_repo_dir = tmp_path / "empty-repo"
        empty_api = HubVaultApi(empty_repo_dir)
        empty_api.create_repo()
        _remove_tree(empty_repo_dir / "refs" / "heads")
        _remove_tree(empty_repo_dir / "refs" / "tags")

        refs = empty_api.list_repo_refs()
        assert [item.name for item in refs.branches] == ["main"]
        assert refs.tags == []

        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")
        _remove_tree(repo_dir / "txn")

        assert api.read_bytes("bundle/file.bin") == b"payload-v1"
        second = api.upload_file(path_or_fileobj=b"payload-v2", path_in_repo="bundle/second.bin")
        assert second.commit_message == "Upload bundle/second.bin with hubvault"
        assert sorted(api.list_repo_files()) == ["bundle/file.bin", "bundle/second.bin"]
