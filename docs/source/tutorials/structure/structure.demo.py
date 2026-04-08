import json
import tempfile
from pathlib import Path

from hubvault import HubVaultApi


def short(value):
    return None if value is None else value[:12]


with tempfile.TemporaryDirectory() as tmpdir:
    repo_dir = Path(tmpdir) / "repo"
    api = HubVaultApi(repo_dir)
    api.create_repo(large_file_threshold=16)
    api.upload_file(
        path_or_fileobj=b"small",
        path_in_repo="artifacts/small.bin",
        commit_message="add small file",
    )
    api.upload_file(
        path_or_fileobj=b"X" * 64,
        path_in_repo="artifacts/large.bin",
        commit_message="add large file",
    )
    small, large = api.get_paths_info(["artifacts/small.bin", "artifacts/large.bin"])
    payload = {
        "chunk_index_files": len(list((repo_dir / "chunks").rglob("*.idx"))),
        "chunk_pack_files": len(list((repo_dir / "chunks").rglob("*.pack"))),
        "download_suffix": "/".join(Path(api.hf_hub_download("artifacts/large.bin")).parts[-2:]),
        "file_objects": len(list((repo_dir / "objects" / "files" / "sha256").rglob("*.json"))),
        "large_file": {
            "oid": short(large.oid),
            "pointer_size": None if large.lfs is None else large.lfs.pointer_size,
            "sha256": short(large.sha256),
            "size": large.size,
            "uses_lfs_metadata": large.lfs is not None,
        },
        "repo_root_dirs": sorted(path.name for path in repo_dir.iterdir() if path.is_dir()),
        "small_file": {
            "oid": short(small.oid),
            "sha256": short(small.sha256),
            "size": small.size,
            "uses_lfs_metadata": small.lfs is not None,
        },
        "tree_objects": len(list((repo_dir / "objects" / "trees" / "sha256").rglob("*.json"))),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
