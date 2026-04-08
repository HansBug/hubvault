import json
import tempfile
from pathlib import Path

from hubvault import HubVaultApi


def short(value):
    return None if value is None else value[:12]


with tempfile.TemporaryDirectory() as tmpdir:
    repo_dir = Path(tmpdir) / "repo"
    api = HubVaultApi(repo_dir)
    api.create_repo()
    api.upload_file(
        path_or_fileobj=b"base-model",
        path_in_repo="weights/model.bin",
        commit_message="seed main",
    )
    api.create_branch(branch="feature")
    api.upload_file(
        path_or_fileobj=b"feature-notes",
        path_in_repo="notes/feature.txt",
        revision="feature",
        commit_message="add feature note",
    )
    api.create_tag(tag="v0.1.0", revision="feature", tag_message="feature preview")
    api.upload_file(
        path_or_fileobj=b"main-doc",
        path_in_repo="docs/main.txt",
        revision="main",
        commit_message="add main doc",
    )
    result = api.merge("feature", target_revision="main", commit_message="merge feature branch")
    refs = api.list_repo_refs()
    commits = api.list_repo_commits(revision="main", formatted=True)
    payload = {
        "branches": {ref.name: short(ref.target_commit) for ref in refs.branches},
        "created_commit": result.created_commit,
        "fast_forward": result.fast_forward,
        "head_after": short(result.head_after),
        "main_commit_titles": [item.title for item in commits[:4]],
        "main_files": list(api.list_repo_files(revision="main")),
        "main_reflog_titles": [item.message for item in api.list_repo_reflog("main")[:4]],
        "merge_status": result.status,
        "tags": {ref.name: short(ref.target_commit) for ref in refs.tags},
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
