hubvault.models
========================================================

.. currentmodule:: hubvault.models

.. automodule:: hubvault.models


RepoInfo
-----------------------------------------------------

.. autoclass:: RepoInfo
    :members: repo_path,format_version,default_branch,head,refs


CommitInfo
-----------------------------------------------------

.. autoclass:: CommitInfo
    :members: __new__,__post_init__,commit_url,commit_message,commit_description,oid,pr_url,repo_url,pr_revision,pr_num


MergeConflict
-----------------------------------------------------

.. autoclass:: MergeConflict
    :members: path,conflict_type,message,base_oid,target_oid,source_oid,related_path


MergeResult
-----------------------------------------------------

.. autoclass:: MergeResult
    :members: status,target_revision,source_revision,base_commit,target_head_before,source_head,head_after,commit,conflicts,fast_forward,created_commit


GitCommitInfo
-----------------------------------------------------

.. autoclass:: GitCommitInfo
    :members: commit_id,authors,created_at,title,message,formatted_title,formatted_message


GitRefInfo
-----------------------------------------------------

.. autoclass:: GitRefInfo
    :members: name,ref,target_commit


GitRefs
-----------------------------------------------------

.. autoclass:: GitRefs
    :members: branches,converts,tags,pull_requests


ReflogEntry
-----------------------------------------------------

.. autoclass:: ReflogEntry
    :members: timestamp,ref_name,old_head,new_head,message,checksum


LastCommitInfo
-----------------------------------------------------

.. autoclass:: LastCommitInfo
    :members: oid,title,date


BlobSecurityInfo
-----------------------------------------------------

.. autoclass:: BlobSecurityInfo
    :members: safe,status,av_scan,pickle_import_scan


RepoFile
-----------------------------------------------------

.. autoclass:: RepoFile
    :members: rfilename,lastCommit,path,size,blob_id,lfs,last_commit,security,oid,sha256,etag


RepoFolder
-----------------------------------------------------

.. autoclass:: RepoFolder
    :members: lastCommit,path,tree_id,last_commit


BlobLfsInfo
-----------------------------------------------------

.. autoclass:: BlobLfsInfo
    :members: size,sha256,pointer_size


VerifyReport
-----------------------------------------------------

.. autoclass:: VerifyReport
    :members: ok,checked_refs,warnings,errors


StorageSectionInfo
-----------------------------------------------------

.. autoclass:: StorageSectionInfo
    :members: name,path,total_size,file_count,reclaimable_size,reclaim_strategy,notes


StorageOverview
-----------------------------------------------------

.. autoclass:: StorageOverview
    :members: total_size,reachable_size,historical_retained_size,reclaimable_gc_size,reclaimable_cache_size,reclaimable_temporary_size,sections,recommendations


GcReport
-----------------------------------------------------

.. autoclass:: GcReport
    :members: dry_run,checked_refs,reclaimed_size,reclaimed_object_size,reclaimed_chunk_size,reclaimed_cache_size,reclaimed_temporary_size,removed_file_count,notes


SquashReport
-----------------------------------------------------

.. autoclass:: SquashReport
    :members: ref_name,old_head,new_head,root_commit_before,rewritten_commit_count,dropped_ancestor_count,blocking_refs,gc_report


