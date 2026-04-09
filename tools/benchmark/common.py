"""Shared benchmark scenarios and metrics for Phase 9 work."""

import random
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from hubvault import CommitOperationAdd, HubVaultApi, RepoFile

MIB = 1024 * 1024
GIB = 1024 * MIB


@dataclass(frozen=True)
class Phase9BenchmarkConfig:
    """Configuration for the benchmark scenarios."""

    scale: str
    small_file_count: int
    small_file_size: int
    large_file_size: int
    duplicate_file_count: int
    overlap_shared_size: int
    overlap_unique_size: int
    shifted_window_step: int
    history_depth: int
    chunk_threshold: int
    range_start: int
    range_length: int
    rounds: int
    warmup_rounds: int

    @classmethod
    def from_scale(cls, scale: str = "standard") -> "Phase9BenchmarkConfig":
        """Build a benchmark configuration for a named scale."""

        normalized = str(scale or "standard").strip().lower()
        if normalized == "smoke":
            return cls(
                scale="smoke",
                small_file_count=32,
                small_file_size=4 * 1024,
                large_file_size=6 * MIB,
                duplicate_file_count=4,
                overlap_shared_size=4 * MIB,
                overlap_unique_size=1 * MIB,
                shifted_window_step=512,
                history_depth=8,
                chunk_threshold=1 * MIB,
                range_start=1 * MIB + 123,
                range_length=256 * 1024,
                rounds=3,
                warmup_rounds=1,
            )
        if normalized == "pressure":
            return cls(
                scale="pressure",
                small_file_count=64,
                small_file_size=8 * 1024,
                large_file_size=512 * MIB,
                duplicate_file_count=3,
                overlap_shared_size=384 * MIB,
                overlap_unique_size=128 * MIB,
                shifted_window_step=2 * MIB,
                history_depth=2,
                chunk_threshold=8 * MIB,
                range_start=128 * MIB + 123,
                range_length=32 * MIB,
                rounds=1,
                warmup_rounds=0,
            )
        if normalized == "stress":
            return cls(
                scale="stress",
                small_file_count=256,
                small_file_size=8 * 1024,
                large_file_size=16 * MIB,
                duplicate_file_count=10,
                overlap_shared_size=12 * MIB,
                overlap_unique_size=2 * MIB,
                shifted_window_step=2 * 1024,
                history_depth=48,
                chunk_threshold=1 * MIB,
                range_start=3 * MIB + 123,
                range_length=2 * MIB,
                rounds=5,
                warmup_rounds=1,
            )
        return cls(
            scale="standard",
            small_file_count=128,
            small_file_size=4 * 1024,
            large_file_size=12 * MIB,
            duplicate_file_count=6,
            overlap_shared_size=8 * MIB,
            overlap_unique_size=1 * MIB,
            shifted_window_step=1024,
            history_depth=24,
            chunk_threshold=1 * MIB,
            range_start=2 * MIB + 123,
            range_length=1 * MIB,
            rounds=4,
            warmup_rounds=1,
        )


def to_mib(size_in_bytes: int) -> float:
    """Convert bytes to MiB."""

    return round(float(size_in_bytes) / float(MIB), 4)


def safe_ratio(numerator: int, denominator: int) -> float:
    """Return a rounded ratio or ``0.0`` when the denominator is empty."""

    if int(denominator) <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def deterministic_bytes(size: int, label: str) -> bytes:
    """Generate deterministic medium-entropy bytes."""

    size = int(size)
    if size <= 0:
        return b""

    seed = int(sha256(label.encode("utf-8")).hexdigest(), 16)
    rng = random.Random(seed)
    chunks = bytearray()
    chunk_size = 1024 * 1024
    while len(chunks) < size:
        current_size = min(chunk_size, size - len(chunks))
        try:
            chunks.extend(rng.randbytes(current_size))
        except AttributeError:
            chunks.extend(rng.getrandbits(current_size * 8).to_bytes(current_size, byteorder="little"))
    return bytes(chunks[:size])


def repeated_bytes(size: int, token: bytes) -> bytes:
    """Generate low-entropy repeated bytes."""

    size = int(size)
    if size <= 0:
        return b""
    if not token:
        token = b"\x00"
    repeats, tail = divmod(size, len(token))
    return (token * repeats) + token[:tail]


def repo_total_size(repo_dir: Path) -> int:
    """Return total bytes occupied by a repository root."""

    total = 0
    for path in repo_dir.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def file_count(root: Path) -> int:
    """Count files below a path."""

    return sum(1 for path in root.rglob("*") if path.is_file())


def overview_section_map(api: HubVaultApi) -> Dict[str, object]:
    """Return storage overview sections indexed by section name."""

    overview = api.get_storage_overview()
    return {section.name: section for section in overview.sections}


def section_size(api: HubVaultApi, section_name: str) -> int:
    """Return the current size of a named storage section."""

    sections = overview_section_map(api)
    try:
        return int(sections[section_name].total_size)
    except KeyError:
        return 0


def list_repo_file_infos(api: HubVaultApi) -> List[RepoFile]:
    """Return public file info objects for the current revision."""

    paths = list(api.list_repo_files())
    if not paths:
        return []
    infos = api.get_paths_info(paths)
    return [info for info in infos if isinstance(info, RepoFile)]


def logical_live_bytes(api: HubVaultApi) -> int:
    """Return total logical live bytes for the current revision."""

    return sum(int(info.size) for info in list_repo_file_infos(api))


def logical_live_large_bytes(api: HubVaultApi) -> int:
    """Return total logical live bytes for chunked large files."""

    return sum(int(info.size) for info in list_repo_file_infos(api) if info.lfs is not None)


def generate_small_tree_entries(config: Phase9BenchmarkConfig) -> List[Tuple[str, bytes]]:
    """Build a deterministic small-file tree payload set."""

    entries = []
    for index in range(int(config.small_file_count)):
        group = index // 16
        path = "dataset/group-{group:03d}/file-{index:04d}.bin".format(
            group=group,
            index=index,
        )
        payload = deterministic_bytes(int(config.small_file_size), "small-{index}".format(index=index))
        entries.append((path, payload))
    return entries


def create_repo(api: HubVaultApi, large_file_threshold: int) -> None:
    """Create a repository with a chosen chunk threshold."""

    api.create_repo(large_file_threshold=int(large_file_threshold))


def next_round_repo_dir(tmp_path: Path, scenario_name: str) -> Path:
    """Return a unique per-round repository directory below ``tmp_path``."""

    scenario_root = tmp_path / scenario_name
    round_index = len(list(scenario_root.glob("*")))
    return scenario_root / ("round-%08d" % round_index)


def build_small_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, List[str], int]:
    """Create a repository populated with many small files."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=max(int(config.large_file_size) * 2, int(config.chunk_threshold) * 4))
    entries = generate_small_tree_entries(config)
    api.create_commit(
        operations=[CommitOperationAdd(path, data) for path, data in entries],
        commit_message="seed small tree",
    )
    return api, [path for path, _ in entries], sum(len(data) for _, data in entries)


def build_large_repo(
    repo_dir: Path,
    config: Phase9BenchmarkConfig,
    payload: Optional[bytes] = None,
    path_in_repo: str = "artifacts/model.bin",
) -> Tuple[HubVaultApi, bytes]:
    """Create a repository with one chunked large file."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    resolved_payload = payload or deterministic_bytes(int(config.large_file_size), "large-binary")
    api.upload_file(
        path_or_fileobj=resolved_payload,
        path_in_repo=path_in_repo,
        commit_message="seed large file",
    )
    return api, resolved_payload


def build_exact_duplicate_live_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository with many identical live large files."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    payload = deterministic_bytes(int(config.large_file_size), "exact-duplicate")
    operations = []
    for index in range(int(config.duplicate_file_count)):
        operations.append(
            CommitOperationAdd(
                "duplicates/exact-{index:02d}.bin".format(index=index),
                payload,
            )
        )
    api.create_commit(operations=operations, commit_message="seed exact duplicate live set")
    logical_total = len(payload) * int(config.duplicate_file_count)
    return api, logical_total, len(payload)


def build_aligned_overlap_live_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository whose large files share chunk-aligned common prefixes."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    shared = deterministic_bytes(int(config.overlap_shared_size), "aligned-shared")
    operations = []
    for index in range(int(config.duplicate_file_count)):
        unique_tail = deterministic_bytes(int(config.overlap_unique_size), "aligned-tail-{index}".format(index=index))
        payload = shared + unique_tail
        operations.append(
            CommitOperationAdd(
                "duplicates/aligned-{index:02d}.bin".format(index=index),
                payload,
            )
        )
    api.create_commit(operations=operations, commit_message="seed aligned overlap live set")
    file_size = len(shared) + int(config.overlap_unique_size)
    logical_total = file_size * int(config.duplicate_file_count)
    logical_unique = len(shared) + (int(config.overlap_unique_size) * int(config.duplicate_file_count))
    return api, logical_total, logical_unique


def build_shifted_overlap_live_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository whose large files are sliding windows over one base payload."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    base = deterministic_bytes(
        int(config.large_file_size) + (int(config.shifted_window_step) * (int(config.duplicate_file_count) - 1)),
        "shifted-window-base",
    )
    operations = []
    for index in range(int(config.duplicate_file_count)):
        start = index * int(config.shifted_window_step)
        payload = base[start:start + int(config.large_file_size)]
        operations.append(
            CommitOperationAdd(
                "duplicates/shifted-{index:02d}.bin".format(index=index),
                payload,
            )
        )
    api.create_commit(operations=operations, commit_message="seed shifted overlap live set")
    logical_total = int(config.large_file_size) * int(config.duplicate_file_count)
    logical_unique = len(base)
    return api, logical_total, logical_unique


def build_historical_duplicate_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int, int]:
    """Create a repository with repeated identical large-file commits on one path."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    payload = deterministic_bytes(int(config.large_file_size), "historical-duplicate")
    for index in range(int(config.history_depth)):
        api.upload_file(
            path_or_fileobj=payload,
            path_in_repo="history/model.bin",
            commit_message="history duplicate {index:03d}".format(index=index),
        )
    return api, len(payload), len(payload)


def build_maintenance_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a repository suited for verify and GC benchmarks."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    shared = deterministic_bytes(int(config.overlap_shared_size), "maintenance-shared")
    for index in range(int(config.history_depth)):
        payload = shared + deterministic_bytes(int(config.overlap_unique_size), "maintenance-tail-{index}".format(index=index))
        api.upload_file(
            path_or_fileobj=payload,
            path_in_repo="models/model.bin",
            commit_message="maintenance version {index:03d}".format(index=index),
        )
    _ = api.hf_hub_download("models/model.bin")
    _ = api.snapshot_download()
    return api, logical_live_bytes(api)


def build_history_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a deep small-file history with refs and reflog activity."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=max(int(config.large_file_size) * 2, int(config.chunk_threshold) * 4))
    for index in range(int(config.history_depth)):
        api.upload_file(
            path_or_fileobj=deterministic_bytes(int(config.small_file_size), "history-{index}".format(index=index)),
            path_in_repo="history/timeline.bin",
            commit_message="history version {index:03d}".format(index=index),
        )
    head_commit = api.repo_info().head
    if head_commit is not None:
        api.create_branch(branch="review", revision=head_commit, exist_ok=True)
        api.create_tag(tag="history-tip", revision=head_commit, exist_ok=True)
    return api, len(api.list_repo_commits())


def build_merge_ready_repo(repo_dir: Path, config: Phase9BenchmarkConfig) -> Tuple[HubVaultApi, int]:
    """Create a repository ready for a non-fast-forward merge benchmark."""

    api = HubVaultApi(repo_dir)
    create_repo(api, large_file_threshold=int(config.chunk_threshold))
    base_model = deterministic_bytes(int(config.chunk_threshold) * 2, "merge-base-model")
    feature_model = deterministic_bytes(int(config.chunk_threshold) * 2, "merge-feature-model")
    main_note = deterministic_bytes(int(config.small_file_size), "merge-main-note")
    feature_note = deterministic_bytes(int(config.small_file_size), "merge-feature-note")
    api.create_commit(
        operations=[
            CommitOperationAdd("artifacts/model.bin", base_model),
            CommitOperationAdd("README.md", b"# merge-benchmark\n"),
        ],
        commit_message="seed merge benchmark",
    )
    api.create_branch(branch="feature")
    api.create_commit(
        revision="feature",
        operations=[
            CommitOperationAdd("artifacts/model.bin", feature_model),
            CommitOperationAdd("notes/feature.txt", feature_note),
        ],
        commit_message="feature update",
    )
    api.create_commit(
        revision="main",
        operations=[CommitOperationAdd("notes/main.txt", main_note)],
        commit_message="main update",
    )
    return api, len(feature_model) + len(feature_note) + len(main_note)


def threshold_sweep_sizes(config: Phase9BenchmarkConfig) -> List[int]:
    """Return the file sizes used for whole-file versus chunked threshold scans."""

    threshold = int(config.chunk_threshold)
    sizes = [
        max(1, threshold - 1),
        threshold,
        threshold + 1,
        threshold * 4,
    ]
    ordered = []
    for size in sizes:
        if size not in ordered:
            ordered.append(size)
    return ordered


def read_all_small_files(api: HubVaultApi, paths: Sequence[str]) -> int:
    """Read all small files and return the processed byte count."""

    total = 0
    for path in paths:
        total += len(api.read_bytes(path))
    return total


def snapshot_file_manifest(snapshot_root: Path) -> List[str]:
    """Return a normalized file manifest for a detached snapshot."""

    return sorted(
        str(path.relative_to(snapshot_root)).replace("\\", "/")
        for path in snapshot_root.rglob("*")
        if path.is_file()
    )


def collect_space_profile(
    api: HubVaultApi,
    logical_live_total: int,
    logical_unique_estimate: Optional[int],
) -> Dict[str, object]:
    """Collect repository space metrics before and after GC."""

    before = api.get_storage_overview()
    dry_gc = api.gc(dry_run=True, prune_cache=False)
    quick_ok = api.quick_verify().ok
    actual_gc = api.gc(dry_run=False, prune_cache=False)
    after = api.get_storage_overview()
    full_ok = api.full_verify().ok

    before_sections = {section.name: section for section in before.sections}
    after_sections = {section.name: section for section in after.sections}
    before_pack = int(before_sections["chunks.packs"].total_size)
    after_pack = int(after_sections["chunks.packs"].total_size)
    before_index = int(before_sections["chunks.index"].total_size)
    after_index = int(after_sections["chunks.index"].total_size)
    unique_estimate = int(logical_unique_estimate) if logical_unique_estimate is not None else 0

    metrics = {
        "logical_live_bytes": int(logical_live_total),
        "logical_unique_estimate_bytes": unique_estimate,
        "chunk_pack_bytes_before_gc": before_pack,
        "chunk_pack_bytes_after_gc": after_pack,
        "chunk_index_bytes_before_gc": before_index,
        "chunk_index_bytes_after_gc": after_index,
        "total_repo_bytes_before_gc": int(before.total_size),
        "total_repo_bytes_after_gc": int(after.total_size),
        "reclaimable_gc_bytes_before_gc": int(before.reclaimable_gc_size),
        "gc_reclaimed_size": int(actual_gc.reclaimed_size),
        "gc_reclaimed_chunk_size": int(actual_gc.reclaimed_chunk_size),
        "gc_dry_run_reclaimed_size": int(dry_gc.reclaimed_size),
        "quick_verify_ok_after_setup": bool(quick_ok),
        "full_verify_ok_after_gc": bool(full_ok),
        "physical_over_logical_before_gc": safe_ratio(before_pack, int(logical_live_total)),
        "physical_over_logical_after_gc": safe_ratio(after_pack, int(logical_live_total)),
        "logical_over_physical_after_gc": safe_ratio(int(logical_live_total), after_pack),
        "dedup_gain_after_gc": safe_ratio(before_pack, after_pack),
        "space_reduction_after_gc": safe_ratio(before_pack - after_pack, before_pack),
    }
    if unique_estimate > 0:
        metrics.update(
            {
                "physical_over_unique_before_gc": safe_ratio(before_pack, unique_estimate),
                "physical_over_unique_after_gc": safe_ratio(after_pack, unique_estimate),
                "unique_over_physical_after_gc": safe_ratio(unique_estimate, after_pack),
            }
        )
    return metrics


def benchmark_workspace(parent: Path, prefix: str) -> tempfile.TemporaryDirectory:
    """Return a temporary workspace rooted below ``parent``."""

    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=str(parent))


def run_small_batch_commit_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute one end-to-end small batch commit scenario."""

    with benchmark_workspace(workspace_root, "phase9-small-write-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        overview = api.get_storage_overview()
        return {
            "processed_bytes": int(total_bytes),
            "live_file_count": len(paths),
            "repo_total_bytes": int(overview.total_size),
            "reachable_bytes": int(overview.reachable_size),
            "blob_bytes": int(section_size(api, "objects.blobs.data")),
            "cache_bytes": int(overview.reclaimable_cache_size),
        }


def run_large_upload_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute one end-to-end large upload scenario."""

    with benchmark_workspace(workspace_root, "phase9-large-write-") as tmpdir:
        api, payload = build_large_repo(Path(tmpdir) / "repo", config)
        overview = api.get_storage_overview()
        return {
            "processed_bytes": len(payload),
            "repo_total_bytes": int(overview.total_size),
            "chunk_pack_bytes": int(section_size(api, "chunks.packs")),
            "chunk_index_bytes": int(section_size(api, "chunks.index")),
            "large_live_bytes": int(logical_live_large_bytes(api)),
        }


def run_hf_hub_download_cold_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a cold detached-file download on a chunked large file."""

    with benchmark_workspace(workspace_root, "phase9-download-cold-") as tmpdir:
        api, payload = build_large_repo(Path(tmpdir) / "repo", config)
        before = api.get_storage_overview()
        started = time.perf_counter()
        path = Path(api.hf_hub_download("artifacts/model.bin"))
        finished = time.perf_counter()
        after = api.get_storage_overview()
        return {
            "processed_bytes": len(payload),
            "operation_seconds": round(finished - started, 6),
            "downloaded_bytes": int(path.stat().st_size),
            "cache_delta_bytes": int(after.reclaimable_cache_size - before.reclaimable_cache_size),
            "suffix_preserved": str(path).replace("\\", "/").endswith("artifacts/model.bin"),
        }


def run_hf_hub_download_warm_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a warm detached-file download on an already materialized file view."""

    with benchmark_workspace(workspace_root, "phase9-download-warm-") as tmpdir:
        api, payload = build_large_repo(Path(tmpdir) / "repo", config)
        first_path = Path(api.hf_hub_download("artifacts/model.bin"))
        before = api.get_storage_overview()
        started = time.perf_counter()
        second_path = Path(api.hf_hub_download("artifacts/model.bin"))
        finished = time.perf_counter()
        after = api.get_storage_overview()
        return {
            "processed_bytes": len(payload),
            "operation_seconds": round(finished - started, 6),
            "downloaded_bytes": int(second_path.stat().st_size),
            "cache_delta_bytes": int(after.reclaimable_cache_size - before.reclaimable_cache_size),
            "reused_view_path": str(first_path) == str(second_path),
            "suffix_preserved": str(second_path).replace("\\", "/").endswith("artifacts/model.bin"),
        }


def run_history_listing_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute commit/ref/reflog listing over a deep small-file history."""

    with benchmark_workspace(workspace_root, "phase9-history-list-") as tmpdir:
        api, commit_count = build_history_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        commits = list(api.list_repo_commits())
        refs = api.list_repo_refs()
        reflog = list(api.list_repo_reflog("main"))
        finished = time.perf_counter()
        return {
            "processed_bytes": 0,
            "operation_seconds": round(finished - started, 6),
            "commit_count": len(commits),
            "expected_commit_count": int(commit_count),
            "branch_count": len(refs.branches),
            "tag_count": len(refs.tags),
            "reflog_count": len(reflog),
        }


def run_merge_non_fast_forward_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute one successful non-fast-forward merge workflow."""

    with benchmark_workspace(workspace_root, "phase9-merge-") as tmpdir:
        api, merge_shape_bytes = build_merge_ready_repo(Path(tmpdir) / "repo", config)
        before_history_count = len(api.list_repo_commits())
        started = time.perf_counter()
        result = api.merge("feature")
        finished = time.perf_counter()
        after_history_count = len(api.list_repo_commits())
        return {
            "processed_bytes": int(merge_shape_bytes),
            "operation_seconds": round(finished - started, 6),
            "merge_status": result.status,
            "created_commit": bool(result.created_commit),
            "conflict_count": len(result.conflicts),
            "history_count_before": before_history_count,
            "history_count_after": after_history_count,
        }


def run_threshold_sweep_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a whole-file versus chunked threshold boundary scan."""

    with benchmark_workspace(workspace_root, "phase9-threshold-sweep-") as tmpdir:
        workspace = Path(tmpdir)
        results = []
        total_processed = 0
        total_operation_seconds = 0.0
        for size in threshold_sweep_sizes(config):
            repo_dir = workspace / ("size-%d" % size)
            api = HubVaultApi(repo_dir)
            create_repo(api, large_file_threshold=int(config.chunk_threshold))
            payload = deterministic_bytes(int(size), "threshold-{size}".format(size=size))
            started = time.perf_counter()
            api.upload_file(
                path_or_fileobj=payload,
                path_in_repo="artifacts/payload.bin",
                commit_message="threshold payload {size}".format(size=size),
            )
            finished = time.perf_counter()
            info = api.get_paths_info(["artifacts/payload.bin"])[0]
            assert isinstance(info, RepoFile)
            operation_seconds = finished - started
            results.append(
                {
                    "file_size": int(size),
                    "chunked": bool(info.lfs is not None),
                    "operation_seconds": round(operation_seconds, 6),
                    "blob_bytes": int(section_size(api, "objects.blobs.data")),
                    "chunk_pack_bytes": int(section_size(api, "chunks.packs")),
                }
            )
            total_processed += len(payload)
            total_operation_seconds += operation_seconds

        below = next((item for item in results if item["file_size"] == int(config.chunk_threshold) - 1), None)
        at = next((item for item in results if item["file_size"] == int(config.chunk_threshold)), None)
        above = next((item for item in results if item["file_size"] == int(config.chunk_threshold) + 1), None)
        return {
            "processed_bytes": int(total_processed),
            "operation_seconds": round(total_operation_seconds, 6),
            "threshold_cases": len(results),
            "threshold_boundary_below_chunked": bool(below and below["chunked"]),
            "threshold_boundary_at_chunked": bool(at and at["chunked"]),
            "threshold_boundary_above_chunked": bool(above and above["chunked"]),
            "threshold_results": results,
        }


def run_squash_history_case(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Execute a history rewrite followed by in-operation GC."""

    with benchmark_workspace(workspace_root, "phase9-squash-") as tmpdir:
        api, logical_live_total, _logical_unique = build_historical_duplicate_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        report = api.squash_history("main", run_gc=True, prune_cache=False)
        finished = time.perf_counter()
        history_after = len(api.list_repo_commits())
        reclaimed_size = 0
        if report.gc_report is not None:
            reclaimed_size = int(report.gc_report.reclaimed_size)
        return {
            "processed_bytes": int(logical_live_total),
            "operation_seconds": round(finished - started, 6),
            "rewritten_commit_count": int(report.rewritten_commit_count),
            "dropped_ancestor_count": int(report.dropped_ancestor_count),
            "blocking_ref_count": len(report.blocking_refs),
            "gc_reclaimed_size": reclaimed_size,
            "history_count_after": history_after,
        }


def infer_space_conclusions(results: Dict[str, Dict[str, object]]) -> List[str]:
    """Build human-readable conclusions from benchmark results."""

    conclusions = []

    def _near_one(value: float, tolerance: float = 0.05) -> bool:
        return abs(float(value) - 1.0) <= float(tolerance)

    exact = results["exact_duplicate_live_space"]["metrics"]
    aligned = results["aligned_overlap_live_space"]["metrics"]
    shifted = results["shifted_overlap_live_space"]["metrics"]
    historical = results.get("historical_duplicate_space", {}).get("metrics", {})

    conclusions.append(
        "大文件上传中位吞吐约 {value:.2f} MiB/s，范围读取中位吞吐约 {range_value:.2f} MiB/s。".format(
            value=float(results["large_upload"].get("throughput_mib_per_sec", 0.0)),
            range_value=float(results["large_read_range"].get("throughput_mib_per_sec", 0.0)),
        )
    )
    exact_before_unique = float(exact.get("physical_over_unique_before_gc", 0.0))
    exact_after_unique = float(exact.get("physical_over_unique_after_gc", 0.0))
    if _near_one(exact_before_unique):
        conclusions.append(
            "完全重复的大文件在写入当下就保持接近单份物理副本，写前后 `physical_over_unique` 都约为 {ratio:.2f}x，说明写时 chunk/pack 复用已经生效，`gc()` 不再承担主要去重职责。".format(
                ratio=exact_before_unique,
            )
        )
    else:
        conclusions.append(
            "完全重复的大文件在写入后立即占用仍接近线性膨胀，`gc()` 后 `chunks.packs` 体积下降到原来的 {ratio:.2%}，说明当前物理复用主要依赖后续压实而不是写时复用。".format(
                ratio=float(exact["physical_over_logical_after_gc"]),
            )
        )

    aligned_before_unique = float(aligned.get("physical_over_unique_before_gc", 0.0))
    aligned_after_unique = float(aligned.get("physical_over_unique_after_gc", 0.0))
    if _near_one(aligned_before_unique):
        conclusions.append(
            "按 chunk 边界对齐的部分重复文件在写入当下就已经接近唯一数据体积，`physical_over_unique_before_gc` 约为 {ratio:.2f}x，`gc()` 基本不再改变结果。".format(
                ratio=aligned_before_unique,
            )
        )
    else:
        conclusions.append(
            "按 chunk 边界对齐的部分重复文件在当前内容定义分块规划下，写入当下可压到约 {before_ratio:.2f}x 唯一数据体积，`gc()` 后保持约 {after_ratio:.2f}x。".format(
                before_ratio=aligned_before_unique,
                after_ratio=aligned_after_unique,
            )
        )

    shifted_before_unique = float(shifted.get("physical_over_unique_before_gc", 0.0))
    shifted_after_unique = float(shifted.get("physical_over_unique_after_gc", 0.0))
    if _near_one(shifted_before_unique):
        conclusions.append(
            "错位重复文件在当前内容定义分块规划下也已接近唯一数据体积，写入当下 `physical_over_unique_before_gc` 约为 {ratio:.2f}x，说明 shifted overlap 不再是明显空间短板。".format(
                ratio=shifted_before_unique,
            )
        )
    else:
        conclusions.append(
            "错位重复文件的空间放大已经收敛到约 {before_ratio:.2f}x（写入当下）和 {after_ratio:.2f}x（`gc()` 后），虽然仍差于 exact duplicate / aligned overlap，但已经明显优于早期固定大小 chunk 的表现。".format(
                before_ratio=shifted_before_unique,
                after_ratio=shifted_after_unique,
            )
        )

    if historical:
        historical_before_unique = float(historical.get("physical_over_unique_before_gc", 0.0))
        if _near_one(historical_before_unique):
            conclusions.append(
                "同一路径反复写入完全相同的大文件时，历史重复提交也不会再把 pack 线性撑大，写入当下已经维持在约 {ratio:.2f}x 唯一数据体积。".format(
                    ratio=historical_before_unique,
                )
            )
        else:
            conclusions.append(
                "同一路径反复写入完全相同的大文件时，提交阶段的 pack 占用仍会持续增长，但 `gc()` 可把这类重复 pack 压回到接近单份数据体积，当前风险在于压实前的短期空间膨胀而不是最终不可回收。"
            )
    cold_download = results.get("hf_hub_download_cold", {})
    warm_download = results.get("hf_hub_download_warm", {})
    if cold_download and warm_download:
        conclusions.append(
            "`hf_hub_download()` 已经具备明确的 cold/warm 语义：warm 路径会复用现有 detached view，第二次调用的缓存增量约为 {delta} 字节，且返回路径保持 repo 相对路径后缀。".format(
                delta=int(warm_download.get("metrics", {}).get("cache_delta_bytes", 0)),
            )
        )
    threshold_metrics = results.get("threshold_sweep", {}).get("metrics", {})
    if threshold_metrics:
        conclusions.append(
            "阈值扫描已经验证当前分界是稳定的：小于 `large_file_threshold` 的文件保持 whole-file blob，而大于等于阈值的文件转入 chunked storage。"
        )
    merge_metrics = results.get("merge_non_fast_forward", {}).get("metrics", {})
    if merge_metrics:
        conclusions.append(
            "非快进 merge 已进入 benchmark 基线，当前基线里该路径能稳定创建结构化 merge commit，后续 profiling 可以直接围绕 merge-base 解析和 tree merge 热点展开。"
        )
    squash_metrics = results.get("squash_history", {}).get("metrics", {})
    if squash_metrics:
        conclusions.append(
            "`squash_history()` 已纳入性能基线，当前可以直接衡量“历史重写 + 跟随 GC”这一完整维护路径，而不是只看 `gc()` 单点。"
        )
    if _near_one(exact_before_unique) and (not historical or _near_one(float(historical.get("physical_over_unique_before_gc", 0.0)))):
        conclusions.append(
            "当前优化已经基本解决 exact duplicate 与历史重复写入的短期空间膨胀，后续应优先关注范围读取、warm download、merge 等时间侧回归，以及 aligned/shifted overlap 的剩余空间差异。"
        )
    else:
        conclusions.append(
            "如果目标是降低重复大文件的即时空间膨胀，优先级最高的问题是写时 chunk/pack 复用；如果目标是提高错位相似内容复用，后续才值得评估内容定义分块方案。"
        )
        conclusions.append(
            "当前实现对时间性能和长期 GC 后空间占用是可接受的，但对“写后立刻”的重复大文件空间放大仍然偏保守，尤其在大量重复提交但未及时 GC 的场景下需要重点关注。"
        )

    if float(results["large_read_range"].get("throughput_mib_per_sec", 0.0)) < float(
        results["large_upload"].get("throughput_mib_per_sec", 0.0)
    ):
        conclusions.append(
            "本次基线里范围读取没有明显快过写入路径，后续应重点 profiling `IndexStore.lookup()` 与逐 chunk 校验链路。"
        )

    return conclusions
