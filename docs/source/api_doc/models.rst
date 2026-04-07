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


GitCommitInfo
-----------------------------------------------------

.. autoclass:: GitCommitInfo
    :members: commit_id,authors,created_at,title,message,formatted_title,formatted_message


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


