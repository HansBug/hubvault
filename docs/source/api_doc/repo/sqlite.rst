hubvault.repo.sqlite
========================================================

.. currentmodule:: hubvault.repo.sqlite

.. automodule:: hubvault.repo.sqlite


SQLITE\_METADATA\_FILENAME
-----------------------------------------------------

.. autodata:: SQLITE_METADATA_FILENAME


SQLITE\_SCHEMA\_VERSION
-----------------------------------------------------

.. autodata:: SQLITE_SCHEMA_VERSION


REQUIRED\_REPO\_META\_KEYS
-----------------------------------------------------

.. autodata:: REQUIRED_REPO_META_KEYS


SQLiteMetadataStore
-----------------------------------------------------

.. autoclass:: SQLiteMetadataStore
    :members: __init__,db_path,exists,initialize_empty,open_connection,ensure_schema,get_repo_meta,has_required_repo_meta,set_repo_meta,get_ref,set_ref,delete_ref,list_refs,append_reflog,last_reflog_entry,list_reflog,truncate_reflog,replace_tx_log,get_tx_log,list_tx_logs,delete_tx_log,clear_truth_tables,set_chunk_entries,delete_chunk_entries,list_chunk_entries,get_chunk_entry,set_object_payload,get_object_payload,object_exists,list_object_ids,delete_object


