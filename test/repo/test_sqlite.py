import pytest

from hubvault import IntegrityError, RevisionNotFoundError
from hubvault.repo.sqlite import SQLiteMetadataStore
from hubvault.storage import IndexEntry


def _sqlite_store(tmp_path, repo_name="repo"):
    repo_dir = tmp_path / repo_name
    store = SQLiteMetadataStore(repo_dir)
    store.initialize_empty()
    return store


@pytest.mark.unittest
class TestSQLiteMetadataStore:
    def test_schema_validation_and_invalid_object_types_are_rejected(self, tmp_path):
        broken_store = _sqlite_store(tmp_path, "broken")
        connection = broken_store.open_connection()
        try:
            connection.execute("UPDATE schema_info SET value = ? WHERE key = ?", ("999", "schema_version"))
            connection.commit()
            with pytest.raises(IntegrityError, match="unsupported sqlite schema version"):
                broken_store.ensure_schema(connection)
        finally:
            connection.close()

        valid_store = _sqlite_store(tmp_path, "valid")
        connection = valid_store.open_connection()
        try:
            with pytest.raises(ValueError, match="unknown object type"):
                valid_store.object_exists(connection, "unknown", "oid")
        finally:
            connection.close()

    def test_refs_and_reflog_round_trip_with_full_and_filtered_queries(self, tmp_path):
        store = _sqlite_store(tmp_path)
        connection = store.open_connection()
        try:
            store.set_ref(connection, "branch", "main", "sha256:" + ("1" * 64), "2026-04-13T00:00:00Z")
            store.set_ref(connection, "tag", "v1", "sha256:" + ("2" * 64), "2026-04-13T00:00:01Z")

            all_refs = store.list_refs(connection)
            assert [item[:2] for item in all_refs] == [("branch", "main"), ("tag", "v1")]
            assert store.list_refs(connection, "branch")[0][1] == "main"

            store.append_reflog(
                connection,
                "branch",
                "main",
                "2026-04-13T00:00:00Z",
                None,
                "sha256:" + ("1" * 64),
                "seed",
                "sha256:" + ("a" * 64),
            )
            store.append_reflog(
                connection,
                "branch",
                "main",
                "2026-04-13T00:00:02Z",
                "sha256:" + ("1" * 64),
                "sha256:" + ("3" * 64),
                "advance",
                "sha256:" + ("b" * 64),
            )

            assert store.last_reflog_entry(connection, "branch", "main")["message"] == "advance"
            store.truncate_reflog(connection, "branch", "main", 0)
            assert store.list_reflog(connection, "branch", "main") == []

            store.delete_ref(connection, "tag", "v1")
            with pytest.raises(RevisionNotFoundError, match="tag not found"):
                store.get_ref(connection, "tag", "v1")
        finally:
            connection.close()

    def test_tx_logs_and_truth_clear_round_trip(self, tmp_path):
        store = _sqlite_store(tmp_path)
        connection = store.open_connection()
        try:
            store.set_repo_meta(connection, {"default_branch": "main"})
            store.set_ref(connection, "branch", "main", None, "2026-04-13T00:00:00Z")
            store.append_reflog(
                connection,
                "branch",
                "main",
                "2026-04-13T00:00:00Z",
                None,
                None,
                "seed",
                "sha256:" + ("c" * 64),
            )
            store.replace_tx_log(
                connection,
                {
                    "txid": "tx-demo",
                    "tx_kind": "ref_update",
                    "state": "PREPARING",
                    "ref_kind": "branch",
                    "ref_name": "main",
                    "old_head": None,
                    "new_head": None,
                    "message": "seed",
                    "ref_existed_before": True,
                    "payload": {"kind": "demo"},
                    "metadata": {"reflog_seq_before": 0},
                    "updated_at": "2026-04-13T00:00:00Z",
                },
            )
            store.set_chunk_entries(
                connection,
                [
                    IndexEntry(
                        chunk_id="sha256:" + ("d" * 64),
                        pack_id="pack-1",
                        offset=16,
                        stored_size=4,
                        logical_size=4,
                        compression="none",
                        checksum="sha256:" + ("d" * 64),
                    )
                ],
            )
            store.set_object_payload(connection, "commits", "sha256:" + ("e" * 64), {"message": "seed"})

            assert store.get_tx_log(connection, "tx-demo")["payload"] == {"kind": "demo"}
            assert store.list_tx_logs(connection)[0]["txid"] == "tx-demo"

            store.clear_truth_tables(connection)

            assert store.get_repo_meta(connection) == {}
            assert store.list_refs(connection) == []
            assert store.list_reflog(connection, "branch", "main") == []
            assert store.list_tx_logs(connection) == []
            assert store.list_chunk_entries(connection) == []
            assert store.list_object_ids(connection, "commits") == []
        finally:
            connection.close()

    def test_chunk_entries_support_delete_and_missing_lookup(self, tmp_path):
        store = _sqlite_store(tmp_path)
        connection = store.open_connection()
        try:
            entries = [
                IndexEntry(
                    chunk_id="sha256:" + ("1" * 64),
                    pack_id="pack-1",
                    offset=16,
                    stored_size=4,
                    logical_size=4,
                    compression="none",
                    checksum="sha256:" + ("1" * 64),
                ),
                IndexEntry(
                    chunk_id="sha256:" + ("2" * 64),
                    pack_id="pack-1",
                    offset=20,
                    stored_size=8,
                    logical_size=8,
                    compression="none",
                    checksum="sha256:" + ("2" * 64),
                ),
            ]
            store.set_chunk_entries(connection, entries)

            assert store.get_chunk_entry(connection, entries[0].chunk_id).pack_id == "pack-1"

            store.delete_chunk_entries(connection, [entries[0].chunk_id, "sha256:" + ("9" * 64)])

            assert store.get_chunk_entry(connection, entries[0].chunk_id) is None
            assert [entry.chunk_id for entry in store.list_chunk_entries(connection)] == [entries[1].chunk_id]
        finally:
            connection.close()
