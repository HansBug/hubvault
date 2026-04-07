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
    :members: commit_id,revision,tree_id,parents,message


PathInfo
-----------------------------------------------------

.. autoclass:: PathInfo
    :members: path,path_type,size,oid,blob_id,sha256,etag


BlobLfsInfo
-----------------------------------------------------

.. autoclass:: BlobLfsInfo
    :members: size,sha256,pointer_size


VerifyReport
-----------------------------------------------------

.. autoclass:: VerifyReport
    :members: ok,checked_refs,warnings,errors


