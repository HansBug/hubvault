import json
import warnings
from pathlib import Path

import pytest

from hubvault import (
    CommitOperationAdd,
    EntryNotFoundError,
    HubVaultApi,
    IntegrityError,
    RepositoryAlreadyExistsError,
)
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
    return _only_path(repo_dir / "objects" / "files" / "sha256", "*.json")


def _mutate_file_payload(repo_dir, mutator):
    path = _file_object_path(repo_dir)
    payload = _read_json(path)
    mutator(payload["payload"])
    _write_json(path, payload)


def _load_index_records(repo_dir):
    path = _only_path(repo_dir / "chunks" / "index" / "L0", "*.idx")
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records
    return path, records


def _mutate_first_index_record(repo_dir, mutator):
    path, records = _load_index_records(repo_dir)
    mutator(records[0])
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


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
        head_commit = api.upload_file(path_or_fileobj=b"payload-v1", path_in_repo="bundle/file.bin")

        repo_dir = tmp_path / "repo"
        ref_path = repo_dir.joinpath(*ref_path_parts)
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(head_commit.oid + "\n", encoding="utf-8")

        txdir = repo_dir / "txn" / ("recover-" + ref_kind)
        txdir.mkdir(parents=True)
        _write_json(
            txdir / "REF_UPDATE.json",
            {
                "ref_kind": ref_kind,
                "ref_name": ref_name,
                "old_head": None,
                "new_head": head_commit.oid,
                "message": "create %s" % ref_kind,
                "ref_existed_before": False,
            },
        )

        assert api.read_bytes("bundle/file.bin") == b"payload-v1"
        assert not ref_path.exists()
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

        with pytest.raises(IntegrityError, match=expected_message):
            api.read_bytes("bundle/file.bin")

    @pytest.mark.parametrize("state_text", ["{bad json", "[]"])
    def test_backend_ref_recovery_rolls_back_when_state_file_is_not_usable(self, tmp_path, state_text):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        first_commit = api.upload_file(path_or_fileobj=b"v1", path_in_repo="bundle/file.bin")
        second_commit = api.upload_file(path_or_fileobj=b"v2", path_in_repo="bundle/file.bin")

        repo_dir = tmp_path / "repo"
        api.reset_ref("main", to_revision=first_commit.oid)

        txdir = repo_dir / "txn" / "broken-state"
        txdir.mkdir(parents=True)
        _write_json(
            txdir / "REF_UPDATE.json",
            {
                "ref_kind": "branch",
                "ref_name": "main",
                "old_head": first_commit.oid,
                "new_head": second_commit.oid,
                "message": "advance with broken state",
                "ref_existed_before": True,
            },
        )
        (txdir / "STATE.json").write_text(state_text, encoding="utf-8")
        (repo_dir / "refs" / "heads" / "main").write_text(second_commit.oid + "\n", encoding="utf-8")

        assert api.repo_info().head == first_commit.oid
        assert api.read_bytes("bundle/file.bin") == b"v1"
        assert not txdir.exists()
