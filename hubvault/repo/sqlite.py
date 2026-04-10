"""
SQLite truth-store helpers for :mod:`hubvault.repo`.

This module centralizes the conservative stdlib-``sqlite3`` repository metadata
store used by Phase 15. The database keeps repo metadata, refs, reflog,
transaction journals, visible chunk locations, and object metadata inside one
repo-local file while blob/pack payload bytes remain in the filesystem.

The module contains:

* :class:`SQLiteMetadataStore` - Repo-local SQLite metadata/object store

Example::

    >>> from pathlib import Path
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmpdir:
    ...     store = SQLiteMetadataStore(Path(tmpdir))
    ...     store.initialize_empty()
    ...     conn = store.open_connection()
    ...     store.set_repo_meta(conn, {"default_branch": "main"})
    ...     store.get_repo_meta(conn)["default_branch"]
    'main'
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from ..errors import IntegrityError, RevisionNotFoundError
from ..storage import IndexEntry

SQLITE_METADATA_FILENAME = "metadata.sqlite3"
SQLITE_SCHEMA_VERSION = 1
REQUIRED_REPO_META_KEYS = (
    "format_version",
    "default_branch",
    "object_hash",
    "file_mode",
    "large_file_threshold",
    "metadata",
)


def _stable_json_text(data: object) -> str:
    """
    Encode JSON using the repository's canonical serialization rules.

    :param data: JSON-serializable value
    :type data: object
    :return: Canonical JSON text
    :rtype: str
    """

    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decode_json_text(text: str) -> object:
    """
    Decode JSON text stored in SQLite.

    :param text: Canonical JSON text
    :type text: str
    :return: Decoded JSON payload
    :rtype: object
    """

    return json.loads(str(text))


class SQLiteMetadataStore:
    """
    Manage the repo-local SQLite metadata and object truth-store.

    :param repo_path: Repository root path
    :type repo_path: Union[str, pathlib.Path]
    """

    def __init__(self, repo_path: Union[str, Path]) -> None:
        """
        Initialize the metadata store wrapper.

        :param repo_path: Repository root path
        :type repo_path: Union[str, pathlib.Path]
        :return: ``None``.
        :rtype: None
        """

        self.repo_path = Path(repo_path)

    @property
    def db_path(self) -> Path:
        """
        Return the metadata database path.

        :return: Absolute SQLite database path
        :rtype: pathlib.Path
        """

        return self.repo_path / SQLITE_METADATA_FILENAME

    def exists(self) -> bool:
        """
        Return whether the SQLite metadata database already exists.

        :return: Whether the database file exists
        :rtype: bool
        """

        return self.db_path.is_file()

    def initialize_empty(self) -> None:
        """
        Create the metadata database and schema if missing.

        :return: ``None``.
        :rtype: None
        """

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self.open_connection(readonly=False)
        try:
            self.ensure_schema(connection)
            connection.commit()
        finally:
            connection.close()

    def open_connection(self, readonly: bool = False) -> sqlite3.Connection:
        """
        Open one SQLite connection configured for the repository baseline.

        :param readonly: Whether to open the database in read-only mode
        :type readonly: bool, optional
        :return: Configured SQLite connection
        :rtype: sqlite3.Connection
        """

        path = str(self.db_path)
        if readonly:
            uri = "file:%s?mode=ro" % path
            connection = sqlite3.connect(uri, uri=True, timeout=30.0, check_same_thread=False)
            self._configure_connection(connection, readonly=True)
            return connection

        connection = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
        self._configure_connection(connection, readonly=False)
        return connection

    def _configure_connection(self, connection: sqlite3.Connection, readonly: bool) -> None:
        """
        Apply the repository's conservative SQLite PRAGMA baseline.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param readonly: Whether the connection is read-only
        :type readonly: bool
        :return: ``None``.
        :rtype: None
        """

        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        if readonly:
            return
        cursor.execute("PRAGMA journal_mode=DELETE")
        cursor.execute("PRAGMA synchronous=EXTRA")
        value = cursor.execute("PRAGMA synchronous").fetchone()[0]
        text = str(value).strip().lower()
        if text not in ("3", "extra"):
            cursor.execute("PRAGMA synchronous=FULL")
            value = cursor.execute("PRAGMA synchronous").fetchone()[0]
            text = str(value).strip().lower()
            if text not in ("2", "full"):
                raise IntegrityError("failed to configure sqlite synchronous mode")

    def ensure_schema(self, connection: sqlite3.Connection) -> None:
        """
        Ensure the metadata schema exists and matches the expected version.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :return: ``None``.
        :rtype: None
        :raises IntegrityError: Raised when the on-disk schema version is not
            supported.
        """

        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        current = cursor.execute(
            "SELECT value FROM schema_info WHERE key = ?",
            ("schema_version",),
        ).fetchone()
        if current is None:
            cursor.execute(
                "INSERT INTO schema_info (key, value) VALUES (?, ?)",
                ("schema_version", str(SQLITE_SCHEMA_VERSION)),
            )
        elif int(current["value"]) != SQLITE_SCHEMA_VERSION:
            raise IntegrityError("unsupported sqlite schema version")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS repo_meta (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS refs (
                ref_kind TEXT NOT NULL,
                ref_name TEXT NOT NULL,
                commit_id TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (ref_kind, ref_name)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reflog (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_kind TEXT NOT NULL,
                ref_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                old_head TEXT,
                new_head TEXT,
                message TEXT NOT NULL,
                checksum TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS reflog_ref_seq_idx
            ON reflog (ref_kind, ref_name, seq)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS txn_log (
                txid TEXT PRIMARY KEY,
                tx_kind TEXT NOT NULL,
                state TEXT NOT NULL,
                ref_kind TEXT,
                ref_name TEXT,
                old_head TEXT,
                new_head TEXT,
                message TEXT NOT NULL,
                ref_existed_before INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chunk_visible (
                chunk_id TEXT PRIMARY KEY,
                pack_id TEXT NOT NULL,
                offset INTEGER NOT NULL,
                stored_size INTEGER NOT NULL,
                logical_size INTEGER NOT NULL,
                compression TEXT NOT NULL,
                checksum TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS chunk_visible_pack_idx
            ON chunk_visible (pack_id)
            """
        )
        for table_name in ("objects_commits", "objects_trees", "objects_files", "objects_blobs"):
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS %s (
                    object_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """ % table_name
            )

    @staticmethod
    def _object_table_name(object_type: str) -> str:
        """
        Resolve the SQLite table name for one logical object type.

        :param object_type: Object collection name
        :type object_type: str
        :return: SQLite table name
        :rtype: str
        :raises ValueError: Raised when ``object_type`` is unknown.
        """

        mapping = {
            "commits": "objects_commits",
            "trees": "objects_trees",
            "files": "objects_files",
            "blobs": "objects_blobs",
        }
        if object_type not in mapping:
            raise ValueError("unknown object type: %s" % object_type)
        return mapping[object_type]

    def get_repo_meta(self, connection: sqlite3.Connection) -> Dict[str, object]:
        """
        Load the full repository metadata mapping.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :return: Repository metadata mapping
        :rtype: Dict[str, object]
        """

        cursor = connection.execute("SELECT key, value_json FROM repo_meta ORDER BY key")
        return dict((str(row["key"]), _decode_json_text(str(row["value_json"]))) for row in cursor.fetchall())

    def has_required_repo_meta(self, connection: sqlite3.Connection) -> bool:
        """
        Return whether the repo metadata store is fully bootstrapped.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :return: Whether all required repo metadata keys are present
        :rtype: bool
        """

        cursor = connection.execute("SELECT key FROM repo_meta")
        keys = set(str(row["key"]) for row in cursor.fetchall())
        return all(key in keys for key in REQUIRED_REPO_META_KEYS)

    def set_repo_meta(self, connection: sqlite3.Connection, values: Dict[str, object]) -> None:
        """
        Replace selected repository metadata keys.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param values: Key/value mapping to persist
        :type values: Dict[str, object]
        :return: ``None``.
        :rtype: None
        """

        for key in sorted(values):
            connection.execute(
                "INSERT OR REPLACE INTO repo_meta (key, value_json) VALUES (?, ?)",
                (str(key), _stable_json_text(values[key])),
            )

    def get_ref(self, connection: sqlite3.Connection, ref_kind: str, ref_name: str) -> Optional[str]:
        """
        Load one ref target.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized ref name
        :type ref_name: str
        :return: Commit object ID or ``None``
        :rtype: Optional[str]
        :raises RevisionNotFoundError: Raised when the ref does not exist.
        """

        row = connection.execute(
            "SELECT commit_id FROM refs WHERE ref_kind = ? AND ref_name = ?",
            (str(ref_kind), str(ref_name)),
        ).fetchone()
        if row is None:
            raise RevisionNotFoundError("%s not found: %s" % (str(ref_kind), str(ref_name)))
        commit_id = row["commit_id"]
        if commit_id is None:
            return None
        return str(commit_id)

    def set_ref(
        self,
        connection: sqlite3.Connection,
        ref_kind: str,
        ref_name: str,
        commit_id: Optional[str],
        updated_at: str,
    ) -> None:
        """
        Upsert one ref target.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized ref name
        :type ref_name: str
        :param commit_id: New target commit ID or ``None``
        :type commit_id: Optional[str]
        :param updated_at: UTC timestamp string
        :type updated_at: str
        :return: ``None``.
        :rtype: None
        """

        connection.execute(
            """
            INSERT OR REPLACE INTO refs (ref_kind, ref_name, commit_id, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(ref_kind), str(ref_name), commit_id, str(updated_at)),
        )

    def delete_ref(self, connection: sqlite3.Connection, ref_kind: str, ref_name: str) -> None:
        """
        Delete one persisted ref.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized ref name
        :type ref_name: str
        :return: ``None``.
        :rtype: None
        """

        connection.execute(
            "DELETE FROM refs WHERE ref_kind = ? AND ref_name = ?",
            (str(ref_kind), str(ref_name)),
        )

    def list_refs(
        self,
        connection: sqlite3.Connection,
        ref_kind: Optional[str] = None,
    ) -> List[Tuple[str, str, Optional[str]]]:
        """
        List refs stored in the metadata database.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: Optional ref-kind filter
        :type ref_kind: Optional[str], optional
        :return: ``(ref_kind, ref_name, commit_id)`` tuples
        :rtype: List[Tuple[str, str, Optional[str]]]
        """

        if ref_kind is None:
            cursor = connection.execute(
                "SELECT ref_kind, ref_name, commit_id FROM refs ORDER BY ref_kind, ref_name"
            )
        else:
            cursor = connection.execute(
                """
                SELECT ref_kind, ref_name, commit_id
                FROM refs
                WHERE ref_kind = ?
                ORDER BY ref_name
                """,
                (str(ref_kind),),
            )
        rows = []
        for row in cursor.fetchall():
            commit_id = row["commit_id"]
            rows.append((str(row["ref_kind"]), str(row["ref_name"]), None if commit_id is None else str(commit_id)))
        return rows

    def append_reflog(
        self,
        connection: sqlite3.Connection,
        ref_kind: str,
        ref_name: str,
        timestamp: str,
        old_head: Optional[str],
        new_head: Optional[str],
        message: str,
        checksum: str,
    ) -> None:
        """
        Append one reflog record.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized ref name
        :type ref_name: str
        :param timestamp: UTC timestamp string
        :type timestamp: str
        :param old_head: Previous head
        :type old_head: Optional[str]
        :param new_head: New head
        :type new_head: Optional[str]
        :param message: Reflog message
        :type message: str
        :param checksum: Reflog checksum
        :type checksum: str
        :return: ``None``.
        :rtype: None
        """

        connection.execute(
            """
            INSERT INTO reflog (
                ref_kind,
                ref_name,
                timestamp,
                old_head,
                new_head,
                message,
                checksum
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ref_kind),
                str(ref_name),
                str(timestamp),
                old_head,
                new_head,
                str(message),
                str(checksum),
            ),
        )

    def last_reflog_entry(
        self,
        connection: sqlite3.Connection,
        ref_kind: str,
        ref_name: str,
    ) -> Optional[Dict[str, object]]:
        """
        Return the newest reflog entry for one ref.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized ref name
        :type ref_name: str
        :return: Reflog entry mapping, or ``None``
        :rtype: Optional[Dict[str, object]]
        """

        row = connection.execute(
            """
            SELECT seq, timestamp, old_head, new_head, message, checksum
            FROM reflog
            WHERE ref_kind = ? AND ref_name = ?
            ORDER BY seq DESC
            LIMIT 1
            """,
            (str(ref_kind), str(ref_name)),
        ).fetchone()
        if row is None:
            return None
        return {
            "seq": int(row["seq"]),
            "timestamp": str(row["timestamp"]),
            "old_head": None if row["old_head"] is None else str(row["old_head"]),
            "new_head": None if row["new_head"] is None else str(row["new_head"]),
            "message": str(row["message"]),
            "checksum": str(row["checksum"]),
        }

    def list_reflog(
        self,
        connection: sqlite3.Connection,
        ref_kind: str,
        ref_name: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, object]]:
        """
        List reflog records for one ref ordered from newest to oldest.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized ref name
        :type ref_name: str
        :param limit: Optional maximum result count
        :type limit: Optional[int], optional
        :return: Reflog entry mappings
        :rtype: List[Dict[str, object]]
        """

        sql = (
            "SELECT seq, timestamp, old_head, new_head, message, checksum "
            "FROM reflog WHERE ref_kind = ? AND ref_name = ? "
            "ORDER BY seq DESC"
        )
        params = [str(ref_kind), str(ref_name)]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        cursor = connection.execute(sql, tuple(params))
        return [
            {
                "seq": int(row["seq"]),
                "timestamp": str(row["timestamp"]),
                "old_head": None if row["old_head"] is None else str(row["old_head"]),
                "new_head": None if row["new_head"] is None else str(row["new_head"]),
                "message": str(row["message"]),
                "checksum": str(row["checksum"]),
            }
            for row in cursor.fetchall()
        ]

    def truncate_reflog(
        self,
        connection: sqlite3.Connection,
        ref_kind: str,
        ref_name: str,
        keep_through_seq: int,
    ) -> None:
        """
        Remove reflog rows newer than one retained sequence number.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param ref_kind: ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized ref name
        :type ref_name: str
        :param keep_through_seq: Highest sequence number to keep, or ``0`` to
            delete the whole reflog
        :type keep_through_seq: int
        :return: ``None``.
        :rtype: None
        """

        keep_through_seq = int(keep_through_seq)
        if keep_through_seq <= 0:
            connection.execute(
                "DELETE FROM reflog WHERE ref_kind = ? AND ref_name = ?",
                (str(ref_kind), str(ref_name)),
            )
            return
        connection.execute(
            """
            DELETE FROM reflog
            WHERE ref_kind = ? AND ref_name = ? AND seq > ?
            """,
            (str(ref_kind), str(ref_name), keep_through_seq),
        )

    def replace_tx_log(self, connection: sqlite3.Connection, payload: Dict[str, object]) -> None:
        """
        Insert or replace one transaction-journal row.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param payload: Journal payload mapping
        :type payload: Dict[str, object]
        :return: ``None``.
        :rtype: None
        """

        connection.execute(
            """
            INSERT OR REPLACE INTO txn_log (
                txid,
                tx_kind,
                state,
                ref_kind,
                ref_name,
                old_head,
                new_head,
                message,
                ref_existed_before,
                payload_json,
                metadata_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload["txid"]),
                str(payload["tx_kind"]),
                str(payload["state"]),
                payload.get("ref_kind"),
                payload.get("ref_name"),
                payload.get("old_head"),
                payload.get("new_head"),
                str(payload.get("message", "")),
                1 if bool(payload.get("ref_existed_before", True)) else 0,
                _stable_json_text(payload.get("payload", {})),
                _stable_json_text(payload.get("metadata", {})),
                str(payload["updated_at"]),
            ),
        )

    def get_tx_log(self, connection: sqlite3.Connection, txid: str) -> Optional[Dict[str, object]]:
        """
        Load one transaction-journal row.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param txid: Transaction identifier
        :type txid: str
        :return: Transaction payload mapping, or ``None``
        :rtype: Optional[Dict[str, object]]
        """

        row = connection.execute(
            """
            SELECT
                txid,
                tx_kind,
                state,
                ref_kind,
                ref_name,
                old_head,
                new_head,
                message,
                ref_existed_before,
                payload_json,
                metadata_json,
                updated_at
            FROM txn_log
            WHERE txid = ?
            """,
            (str(txid),),
        ).fetchone()
        if row is None:
            return None
        return self._decode_tx_log_row(row)

    def list_tx_logs(self, connection: sqlite3.Connection) -> List[Dict[str, object]]:
        """
        List all persisted transaction-journal rows.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :return: Transaction payload mappings ordered by txid
        :rtype: List[Dict[str, object]]
        """

        cursor = connection.execute(
            """
            SELECT
                txid,
                tx_kind,
                state,
                ref_kind,
                ref_name,
                old_head,
                new_head,
                message,
                ref_existed_before,
                payload_json,
                metadata_json,
                updated_at
            FROM txn_log
            ORDER BY txid
            """
        )
        return [self._decode_tx_log_row(row) for row in cursor.fetchall()]

    @staticmethod
    def _decode_tx_log_row(row: sqlite3.Row) -> Dict[str, object]:
        """
        Decode one SQLite txn-log row into a plain mapping.

        :param row: SQLite row
        :type row: sqlite3.Row
        :return: Transaction payload mapping
        :rtype: Dict[str, object]
        """

        return {
            "txid": str(row["txid"]),
            "tx_kind": str(row["tx_kind"]),
            "state": str(row["state"]),
            "ref_kind": None if row["ref_kind"] is None else str(row["ref_kind"]),
            "ref_name": None if row["ref_name"] is None else str(row["ref_name"]),
            "old_head": None if row["old_head"] is None else str(row["old_head"]),
            "new_head": None if row["new_head"] is None else str(row["new_head"]),
            "message": str(row["message"]),
            "ref_existed_before": bool(int(row["ref_existed_before"])),
            "payload": _decode_json_text(str(row["payload_json"])),
            "metadata": _decode_json_text(str(row["metadata_json"])),
            "updated_at": str(row["updated_at"]),
        }

    def delete_tx_log(self, connection: sqlite3.Connection, txid: str) -> None:
        """
        Delete one transaction-journal row.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param txid: Transaction identifier
        :type txid: str
        :return: ``None``.
        :rtype: None
        """

        connection.execute("DELETE FROM txn_log WHERE txid = ?", (str(txid),))

    def clear_truth_tables(self, connection: sqlite3.Connection) -> None:
        """
        Remove all persisted truth rows while preserving the schema.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :return: ``None``.
        :rtype: None
        """

        for table_name in (
            "repo_meta",
            "refs",
            "reflog",
            "txn_log",
            "chunk_visible",
            "objects_commits",
            "objects_trees",
            "objects_files",
            "objects_blobs",
        ):
            connection.execute("DELETE FROM %s" % table_name)

    def set_chunk_entries(self, connection: sqlite3.Connection, entries: Sequence[IndexEntry]) -> None:
        """
        Replace the full visible chunk-entry set.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param entries: Visible chunk entries to persist
        :type entries: Sequence[IndexEntry]
        :return: ``None``.
        :rtype: None
        """

        connection.execute("DELETE FROM chunk_visible")
        for entry in entries:
            connection.execute(
                """
                INSERT OR REPLACE INTO chunk_visible (
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
                (
                    str(entry.chunk_id),
                    str(entry.pack_id),
                    int(entry.offset),
                    int(entry.stored_size),
                    int(entry.logical_size),
                    str(entry.compression),
                    str(entry.checksum),
                ),
            )

    def delete_chunk_entries(self, connection: sqlite3.Connection, chunk_ids: Iterable[str]) -> None:
        """
        Delete selected chunk-visible entries.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param chunk_ids: Chunk identifiers to remove
        :type chunk_ids: Iterable[str]
        :return: ``None``.
        :rtype: None
        """

        for chunk_id in chunk_ids:
            connection.execute("DELETE FROM chunk_visible WHERE chunk_id = ?", (str(chunk_id),))

    def list_chunk_entries(self, connection: sqlite3.Connection) -> List[IndexEntry]:
        """
        List all visible chunk entries.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :return: Visible chunk entries ordered by chunk ID
        :rtype: List[IndexEntry]
        """

        cursor = connection.execute(
            """
            SELECT chunk_id, pack_id, offset, stored_size, logical_size, compression, checksum
            FROM chunk_visible
            ORDER BY chunk_id
            """
        )
        return [
            IndexEntry(
                chunk_id=str(row["chunk_id"]),
                pack_id=str(row["pack_id"]),
                offset=int(row["offset"]),
                stored_size=int(row["stored_size"]),
                logical_size=int(row["logical_size"]),
                compression=str(row["compression"]),
                checksum=str(row["checksum"]),
            )
            for row in cursor.fetchall()
        ]

    def get_chunk_entry(self, connection: sqlite3.Connection, chunk_id: str) -> Optional[IndexEntry]:
        """
        Load one visible chunk entry.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param chunk_id: Chunk identifier
        :type chunk_id: str
        :return: Visible chunk entry, or ``None``
        :rtype: Optional[IndexEntry]
        """

        row = connection.execute(
            """
            SELECT chunk_id, pack_id, offset, stored_size, logical_size, compression, checksum
            FROM chunk_visible
            WHERE chunk_id = ?
            """,
            (str(chunk_id),),
        ).fetchone()
        if row is None:
            return None
        return IndexEntry(
            chunk_id=str(row["chunk_id"]),
            pack_id=str(row["pack_id"]),
            offset=int(row["offset"]),
            stored_size=int(row["stored_size"]),
            logical_size=int(row["logical_size"]),
            compression=str(row["compression"]),
            checksum=str(row["checksum"]),
        )

    def set_object_payload(
        self,
        connection: sqlite3.Connection,
        object_type: str,
        object_id: str,
        payload: object,
    ) -> None:
        """
        Upsert one object payload row.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param object_type: Object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :param payload: Logical object payload
        :type payload: object
        :return: ``None``.
        :rtype: None
        """

        connection.execute(
            "INSERT OR REPLACE INTO %s (object_id, payload_json) VALUES (?, ?)"
            % self._object_table_name(object_type),
            (str(object_id), _stable_json_text(payload)),
        )

    def get_object_payload(
        self,
        connection: sqlite3.Connection,
        object_type: str,
        object_id: str,
    ) -> Dict[str, object]:
        """
        Load one stored object payload.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param object_type: Object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: Logical object payload
        :rtype: Dict[str, object]
        :raises RevisionNotFoundError: Raised when the object is absent.
        """

        row = connection.execute(
            "SELECT payload_json FROM %s WHERE object_id = ?" % self._object_table_name(object_type),
            (str(object_id),),
        ).fetchone()
        if row is None:
            raise RevisionNotFoundError("object not found: %s" % object_id)
        payload = _decode_json_text(str(row["payload_json"]))
        return dict(payload)

    def object_exists(self, connection: sqlite3.Connection, object_type: str, object_id: str) -> bool:
        """
        Return whether one object payload row exists.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param object_type: Object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: Whether the object exists
        :rtype: bool
        """

        row = connection.execute(
            "SELECT 1 FROM %s WHERE object_id = ? LIMIT 1" % self._object_table_name(object_type),
            (str(object_id),),
        ).fetchone()
        return row is not None

    def list_object_ids(self, connection: sqlite3.Connection, object_type: str) -> List[str]:
        """
        List all persisted object identifiers for one logical type.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param object_type: Object collection name
        :type object_type: str
        :return: Object identifiers ordered lexicographically
        :rtype: List[str]
        """

        cursor = connection.execute(
            "SELECT object_id FROM %s ORDER BY object_id" % self._object_table_name(object_type)
        )
        return [str(row["object_id"]) for row in cursor.fetchall()]

    def delete_object(self, connection: sqlite3.Connection, object_type: str, object_id: str) -> None:
        """
        Delete one object payload row.

        :param connection: Open SQLite connection
        :type connection: sqlite3.Connection
        :param object_type: Object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: ``None``.
        :rtype: None
        """

        connection.execute(
            "DELETE FROM %s WHERE object_id = ?" % self._object_table_name(object_type),
            (str(object_id),),
        )
