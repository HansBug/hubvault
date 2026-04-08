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
        path_or_fileobj=b"A" * 64,
        path_in_repo="bundle/model.bin",
        commit_message="upload v1",
    )
    api.upload_file(
        path_or_fileobj=b"B" * 64,
        path_in_repo="bundle/model.bin",
        commit_message="upload v2",
    )
    api.hf_hub_download("bundle/model.bin")
    api.snapshot_download()
    before = api.get_storage_overview()
    quick = api.quick_verify()
    full = api.full_verify()
    dry_gc = api.gc(dry_run=True, prune_cache=True)
    actual_gc = api.gc(dry_run=False, prune_cache=True)
    squash = api.squash_history(
        "main",
        commit_message="squash main history",
        run_gc=True,
        prune_cache=True,
    )
    after = api.get_storage_overview()
    payload = {
        "actual_gc": {
            "reclaimed_cache_size": actual_gc.reclaimed_cache_size,
            "reclaimed_size": actual_gc.reclaimed_size,
            "removed_file_count": actual_gc.removed_file_count,
        },
        "after": {
            "historical_retained_size": after.historical_retained_size,
            "reclaimable_cache_size": after.reclaimable_cache_size,
            "reclaimable_gc_size": after.reclaimable_gc_size,
        },
        "before": {
            "historical_retained_size": before.historical_retained_size,
            "reclaimable_cache_size": before.reclaimable_cache_size,
            "reclaimable_gc_size": before.reclaimable_gc_size,
            "reclaimable_temporary_size": before.reclaimable_temporary_size,
        },
        "dry_gc": {
            "dry_run": dry_gc.dry_run,
            "notes": dry_gc.notes[:2],
        },
        "full_verify_ok": full.ok,
        "quick_verify_ok": quick.ok,
        "squash": {
            "dropped_ancestor_count": squash.dropped_ancestor_count,
            "new_head": short(squash.new_head),
            "rewritten_commit_count": squash.rewritten_commit_count,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
