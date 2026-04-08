import json
import tempfile
from pathlib import Path

from hubvault import CommitOperationAdd, HubVaultApi


def short(value):
    return None if value is None else value[:12]


with tempfile.TemporaryDirectory() as tmpdir:
    repo_dir = Path(tmpdir) / "repo"
    api = HubVaultApi(repo_dir)
    info = api.create_repo()
    api.upload_file(path_or_fileobj=b"weights-v1", path_in_repo="artifacts/model.safetensors")
    second = api.create_commit(
        operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
        commit_message="add readme",
    )
    download_path = Path(api.hf_hub_download("artifacts/model.safetensors"))
    snapshot_dir = Path(api.snapshot_download())
    result = {
        "commit_titles": [item.title for item in api.list_repo_commits(formatted=True)],
        "default_branch": info.default_branch,
        "download_suffix": "/".join(download_path.parts[-2:]),
        "files": list(api.list_repo_files()),
        "initial_head": short(info.head),
        "latest_commit": short(second.oid),
        "readme": api.read_bytes("README.md").decode("utf-8").strip(),
        "snapshot_files": sorted(
            str(path.relative_to(snapshot_dir)).replace("\\", "/")
            for path in snapshot_dir.rglob("*")
            if path.is_file()
        ),
        "verify_ok": api.quick_verify().ok,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
