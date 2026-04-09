"""Run the hubvault benchmark suite and emit a curated JSON summary."""

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Sequence

from hubvault import HubVaultApi

from tools.benchmark.common import (
    Phase9BenchmarkConfig,
    benchmark_workspace,
    build_aligned_overlap_live_repo,
    build_exact_duplicate_live_repo,
    build_historical_duplicate_repo,
    build_large_repo,
    build_maintenance_repo,
    build_shifted_overlap_live_repo,
    build_small_repo,
    collect_space_profile,
    create_repo,
    deterministic_bytes,
    infer_space_conclusions,
    read_all_small_files,
    run_cache_heavy_warm_download_case,
    run_hf_hub_download_cold_case,
    run_hf_hub_download_warm_case,
    run_history_deep_listing_case,
    run_history_listing_case,
    run_merge_heavy_case,
    run_merge_non_fast_forward_case,
    run_mixed_model_snapshot_case,
    run_nested_tree_listing_case,
    run_squash_history_case,
    run_threshold_sweep_case,
    run_verify_heavy_case,
    snapshot_file_manifest,
    to_mib,
)


def _percentile(samples: Sequence[float], percentile: float) -> float:
    """Return a percentile using linear interpolation."""

    ordered = sorted(float(sample) for sample in samples)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (float(percentile) / 100.0) * float(len(ordered) - 1)
    lower_index = int(math.floor(rank))
    upper_index = int(math.ceil(rank))
    if lower_index == upper_index:
        return ordered[lower_index]
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    weight = rank - float(lower_index)
    return lower_value + ((upper_value - lower_value) * weight)


def _machine_signature() -> Dict[str, object]:
    """Return environment metadata for one benchmark run."""

    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "platform_processor": platform.processor(),
        "platform": platform.platform(),
        "python_executable": sys.executable,
    }


def _git_value(repo_root: Path, args: Sequence[str]) -> str:
    """Return one git command value or an empty string when unavailable."""

    try:
        output = subprocess.check_output(
            list(args),
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return output.strip()


def _git_metadata() -> Dict[str, object]:
    """Return reproducibility metadata for the current repository checkout."""

    repo_root = Path(__file__).resolve().parents[2]
    head = _git_value(repo_root, ("git", "rev-parse", "HEAD"))
    short_head = _git_value(repo_root, ("git", "rev-parse", "--short", "HEAD"))
    branch = _git_value(repo_root, ("git", "symbolic-ref", "--quiet", "--short", "HEAD"))
    describe = _git_value(repo_root, ("git", "describe", "--always", "--tags", "--dirty"))

    dirty = False
    try:
        status = subprocess.run(
            ["git", "diff", "--quiet", "--ignore-submodules", "HEAD", "--"],
            cwd=str(repo_root),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dirty = status.returncode == 1
    except FileNotFoundError:
        dirty = False

    return {
        "head": head,
        "short_head": short_head,
        "branch": branch,
        "describe": describe,
        "dirty": bool(dirty),
        "repo_root": str(repo_root),
    }


def _dataset_shapes(config: Phase9BenchmarkConfig) -> Dict[str, Dict[str, object]]:
    """Return stable dataset-shape metadata for the configured scale."""

    small_tree_count = int(config.small_file_count)
    nested_file_count = int(config.nested_directory_count) * int(config.nested_files_per_directory)
    return {
        "small-tree": {
            "file_count": small_tree_count,
            "file_size_bytes": int(config.small_file_size),
            "logical_bytes": small_tree_count * int(config.small_file_size),
        },
        "nested-small": {
            "directory_count": int(config.nested_directory_count),
            "files_per_directory": int(config.nested_files_per_directory),
            "file_count": nested_file_count,
            "file_size_bytes": int(config.small_file_size),
            "logical_bytes": nested_file_count * int(config.small_file_size),
        },
        "mixed-model": {
            "large_file_count": 2,
            "large_file_size_bytes": int(config.mixed_large_file_size),
            "small_descriptor_count": 7,
            "small_file_size_bytes": int(config.small_file_size),
        },
        "large-single": {
            "large_file_count": 1,
            "large_file_size_bytes": int(config.large_file_size),
            "chunk_threshold_bytes": int(config.chunk_threshold),
            "range_start_bytes": int(config.range_start),
            "range_length_bytes": int(config.range_length),
        },
        "host-seq-io": {
            "file_size_bytes": int(max(config.large_file_size, config.mixed_large_file_size)),
            "chunk_size_bytes": 4 * 1024 * 1024,
        },
        "history": {
            "commit_depth": int(config.history_depth),
            "branch_count": 2,
            "tag_count": 1,
        },
        "history-deep": {
            "commit_depth": int(config.history_deep_depth),
            "branch_count": 3,
            "tag_count": 1,
            "metadata_path_count": 16,
        },
        "merge-ready": {
            "side_commit_count": 1,
            "large_model_bytes": int(config.chunk_threshold) * 2,
        },
        "merge-heavy": {
            "side_commit_count": int(config.merge_side_commit_count),
            "large_model_bytes": int(config.chunk_threshold) * 2,
            "note_file_size_bytes": int(config.small_file_size),
        },
        "threshold-sweep": {
            "chunk_threshold_bytes": int(config.chunk_threshold),
            "cases": 4,
        },
        "historical-duplicate": {
            "history_depth": int(config.history_depth),
            "large_file_size_bytes": int(config.large_file_size),
        },
        "cache-heavy": {
            "warm_rounds": int(config.cache_warm_rounds),
            "large_file_count": 2,
            "large_file_size_bytes": int(config.mixed_large_file_size),
        },
        "verify-heavy": {
            "large_file_count": 2,
            "large_file_size_bytes": int(config.mixed_large_file_size),
            "extra_note_count": int(config.merge_side_commit_count),
        },
        "maintenance-heavy": {
            "history_depth": int(config.history_depth),
            "shared_prefix_bytes": int(config.overlap_shared_size),
            "unique_tail_bytes": int(config.overlap_unique_size),
        },
        "exact-duplicate-live": {
            "duplicate_file_count": int(config.duplicate_file_count),
            "large_file_size_bytes": int(config.large_file_size),
        },
        "aligned-overlap-live": {
            "duplicate_file_count": int(config.duplicate_file_count),
            "shared_prefix_bytes": int(config.overlap_shared_size),
            "unique_tail_bytes": int(config.overlap_unique_size),
        },
        "shifted-overlap-live": {
            "duplicate_file_count": int(config.duplicate_file_count),
            "window_step_bytes": int(config.shifted_window_step),
            "large_file_size_bytes": int(config.large_file_size),
        },
    }


def _scenario_contracts() -> Dict[str, Dict[str, object]]:
    """Return per-scenario workload semantics for the curated summary."""

    return {
        "small_batch_commit": {
            "category": "bandwidth",
            "temperature": "cold",
            "public_surface": "HubVaultApi.create_commit",
        },
        "host_io_write_baseline": {
            "category": "reference",
            "temperature": "reference",
            "public_surface": "local filesystem sequential write baseline",
            "reference_only": True,
        },
        "host_io_read_baseline": {
            "category": "reference",
            "temperature": "reference",
            "public_surface": "local filesystem sequential read baseline",
            "reference_only": True,
        },
        "small_read_all": {
            "category": "bandwidth",
            "temperature": "cold",
            "public_surface": "HubVaultApi.read_bytes",
        },
        "nested_tree_listing": {
            "category": "metadata",
            "temperature": "cold",
            "public_surface": "HubVaultApi.list_repo_tree(recursive=True)",
        },
        "snapshot_download_small": {
            "category": "bandwidth",
            "temperature": "cold",
            "public_surface": "HubVaultApi.snapshot_download",
        },
        "mixed_model_snapshot": {
            "category": "bandwidth",
            "temperature": "cold",
            "public_surface": "HubVaultApi.snapshot_download",
        },
        "large_upload": {
            "category": "bandwidth",
            "temperature": "cold",
            "public_surface": "HubVaultApi.upload_file",
        },
        "large_read_range": {
            "category": "bandwidth",
            "temperature": "cold",
            "public_surface": "HubVaultApi.read_range",
        },
        "hf_hub_download_cold": {
            "category": "bandwidth",
            "temperature": "cold",
            "public_surface": "HubVaultApi.hf_hub_download",
        },
        "hf_hub_download_warm": {
            "category": "bandwidth",
            "temperature": "warm",
            "public_surface": "HubVaultApi.hf_hub_download",
        },
        "cache_heavy_warm_download": {
            "category": "bandwidth",
            "temperature": "warm",
            "public_surface": "HubVaultApi.hf_hub_download",
        },
        "history_listing": {
            "category": "metadata",
            "temperature": "cold",
            "public_surface": "HubVaultApi.list_repo_commits/list_repo_refs/list_repo_reflog",
        },
        "history_deep_listing": {
            "category": "metadata",
            "temperature": "cold",
            "public_surface": "HubVaultApi.list_repo_commits/list_repo_refs/list_repo_reflog",
        },
        "merge_non_fast_forward": {
            "category": "metadata",
            "temperature": "cold",
            "public_surface": "HubVaultApi.merge",
        },
        "merge_heavy_non_fast_forward": {
            "category": "metadata",
            "temperature": "cold",
            "public_surface": "HubVaultApi.merge",
        },
        "threshold_sweep": {
            "category": "stability",
            "temperature": "cold",
            "public_surface": "HubVaultApi.upload_file + HubVaultApi.get_paths_info",
        },
        "exact_duplicate_live_space": {
            "category": "amplification",
            "temperature": "cold",
            "public_surface": "HubVaultApi.gc/full_verify/get_storage_overview",
        },
        "aligned_overlap_live_space": {
            "category": "amplification",
            "temperature": "cold",
            "public_surface": "HubVaultApi.gc/full_verify/get_storage_overview",
        },
        "shifted_overlap_live_space": {
            "category": "amplification",
            "temperature": "cold",
            "public_surface": "HubVaultApi.gc/full_verify/get_storage_overview",
        },
        "historical_duplicate_space": {
            "category": "amplification",
            "temperature": "cold",
            "public_surface": "HubVaultApi.gc/full_verify/get_storage_overview",
        },
        "full_verify": {
            "category": "maintenance",
            "temperature": "cold",
            "public_surface": "HubVaultApi.full_verify",
        },
        "verify_heavy_full_verify": {
            "category": "maintenance",
            "temperature": "cold",
            "public_surface": "HubVaultApi.full_verify",
        },
        "squash_history": {
            "category": "maintenance",
            "temperature": "cold",
            "public_surface": "HubVaultApi.squash_history",
        },
    }


def _category_map() -> Dict[str, List[str]]:
    """Return the category-to-scenarios mapping for Phase 12 summaries."""

    contracts = _scenario_contracts()
    category_map = {
        "bandwidth": [],
        "metadata": [],
        "maintenance": [],
        "amplification": [],
        "reference": [],
        "stability": sorted(contracts),
    }
    for name, metadata in contracts.items():
        category = str(metadata["category"])
        if category == "stability":
            continue
        category_map[category].append(name)
    for category, names in category_map.items():
        category_map[category] = sorted(names)
    return category_map


def _threshold_policy() -> Dict[str, object]:
    """Return the current alert-versus-trend interpretation policy."""

    return {
        "same_machine_required_for_alerts": True,
        "same_config_required_for_alerts": True,
        "latency_p50_regression_ratio": {
            "bandwidth": 0.20,
            "metadata": 0.15,
            "maintenance": 0.20,
        },
        "throughput_regression_ratio": {
            "bandwidth": 0.20,
        },
        "operations_regression_ratio": {
            "metadata": 0.15,
        },
        "amplification_growth_ratio": {
            "write_amplification": 0.10,
            "cache_amplification": 0.15,
            "space_amplification_live_after_gc": 0.10,
            "space_amplification_unique_after_gc": 0.10,
        },
        "trend_only_metrics": [
            "latency_p95_seconds",
            "latency_p99_seconds",
            "latency_iqr_seconds",
            "latency_stddev_seconds",
            "throughput_stddev_mib_per_sec",
        ],
    }


def _round_metric(value: float) -> float:
    """Round metric values to the curated summary precision."""

    return round(float(value), 6)


def _median_or_zero(values: Sequence[float]) -> float:
    """Return the median of numeric values or ``0.0`` when empty."""

    numeric = [float(value) for value in values]
    if not numeric:
        return 0.0
    return float(statistics.median(numeric))


def _measure_seconds(func: Callable[[], Dict[str, object]], rounds: int, warmup_rounds: int) -> Dict[str, object]:
    """Measure one callable for a fixed number of rounds."""

    for _ in range(max(0, int(warmup_rounds))):
        func()

    samples = []
    round_metrics = []
    metrics = {}
    for _ in range(max(1, int(rounds))):
        started = time.perf_counter()
        current_metrics = dict(func() or {})
        ended = time.perf_counter()
        samples.append(ended - started)
        round_metrics.append(current_metrics)
        metrics = current_metrics

    median_seconds = statistics.median(samples)
    p25_seconds = _percentile(samples, 25.0)
    p50_seconds = _percentile(samples, 50.0)
    p75_seconds = _percentile(samples, 75.0)
    p95_seconds = _percentile(samples, 95.0)
    p99_seconds = _percentile(samples, 99.0)
    latency_stddev_seconds = statistics.pstdev(samples) if len(samples) > 1 else 0.0

    metrics = dict(metrics or {})
    metrics["sample_count"] = len(samples)
    metrics["wall_clock_seconds"] = _round_metric(median_seconds)

    throughput_samples = []
    operations_samples = []
    for current_metrics in round_metrics:
        processed_bytes = int(current_metrics.get("processed_bytes", 0))
        operation_seconds = float(current_metrics.get("operation_seconds", 0.0))
        operation_count = int(current_metrics.get("operation_count", 0))
        if processed_bytes > 0 and operation_seconds > 0.0:
            throughput_samples.append(to_mib(processed_bytes) / operation_seconds)
        if operation_count > 0 and operation_seconds > 0.0:
            operations_samples.append(float(operation_count) / operation_seconds)

    processed_bytes = int(metrics.get("processed_bytes", 0))
    operation_seconds = float(metrics.get("operation_seconds", median_seconds))
    operation_count = int(metrics.get("operation_count", 0))

    throughput_mib_per_sec = 0.0
    if processed_bytes > 0 and operation_seconds > 0.0:
        throughput_mib_per_sec = to_mib(processed_bytes) / operation_seconds
        metrics["throughput_mib_per_sec"] = _round_metric(throughput_mib_per_sec)
    operations_per_sec = 0.0
    if operation_count > 0 and operation_seconds > 0.0:
        operations_per_sec = float(operation_count) / operation_seconds
        metrics["operations_per_sec"] = _round_metric(operations_per_sec)

    files_materialized = int(metrics.get("files_materialized", metrics.get("snapshot_file_count", 0)))
    if files_materialized > 0 and operation_seconds > 0.0:
        metrics["files_materialized_per_sec"] = _round_metric(float(files_materialized) / operation_seconds)

    repo_total_bytes = metrics.get("repo_total_bytes")
    if repo_total_bytes is not None and processed_bytes > 0:
        metrics["write_amplification"] = _round_metric(float(int(repo_total_bytes)) / float(processed_bytes))

    cache_delta_bytes = metrics.get("cache_delta_bytes")
    if cache_delta_bytes is not None and processed_bytes > 0:
        metrics["cache_amplification"] = _round_metric(float(int(cache_delta_bytes)) / float(processed_bytes))

    result = {
        "rounds": len(samples),
        "sample_count": len(samples),
        "seconds": {
            "median": _round_metric(median_seconds),
            "min": _round_metric(min(samples)),
            "max": _round_metric(max(samples)),
            "p25": _round_metric(p25_seconds),
            "p50": _round_metric(p50_seconds),
            "p75": _round_metric(p75_seconds),
            "p95": _round_metric(p95_seconds),
            "p99": _round_metric(p99_seconds),
            "iqr": _round_metric(p75_seconds - p25_seconds),
            "samples": [_round_metric(item) for item in samples],
        },
        "wall_clock_seconds": _round_metric(median_seconds),
        "latency_p50_seconds": _round_metric(p50_seconds),
        "latency_p95_seconds": _round_metric(p95_seconds),
        "latency_p99_seconds": _round_metric(p99_seconds),
        "latency_iqr_seconds": _round_metric(p75_seconds - p25_seconds),
        "latency_stddev_seconds": _round_metric(latency_stddev_seconds),
        "metrics": metrics,
    }
    if throughput_mib_per_sec > 0.0:
        result["throughput_mib_per_sec"] = _round_metric(throughput_mib_per_sec)
    if throughput_samples:
        result["throughput_stddev_mib_per_sec"] = _round_metric(
            statistics.pstdev(throughput_samples) if len(throughput_samples) > 1 else 0.0
        )
    if operations_per_sec > 0.0:
        result["operations_per_sec"] = _round_metric(operations_per_sec)
    if operations_samples:
        result["operations_stddev_per_sec"] = _round_metric(
            statistics.pstdev(operations_samples) if len(operations_samples) > 1 else 0.0
        )
    return result


def _small_batch_commit_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-small-write-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        overview = api.get_storage_overview()
        return {
            "processed_bytes": total_bytes,
            "repo_total_bytes": int(overview.total_size),
            "reachable_bytes": int(overview.reachable_size),
            "operation_count": len(paths),
            "live_file_count": len(paths),
            "dataset_family": "small-tree",
        }


def _stream_write_file(path: Path, total_bytes: int, chunk_size: int, label_prefix: str) -> int:
    """Write deterministic bytes to ``path`` in bounded chunks."""

    written = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fileobj:
        chunk_index = 0
        while written < int(total_bytes):
            current_size = min(int(chunk_size), int(total_bytes) - written)
            payload = deterministic_bytes(current_size, "{prefix}-{index}".format(prefix=label_prefix, index=chunk_index))
            fileobj.write(payload)
            written += len(payload)
            chunk_index += 1
        fileobj.flush()
        os.fsync(fileobj.fileno())
    return written


def _stream_read_file(path: Path, chunk_size: int) -> int:
    """Read a file sequentially in bounded chunks and return byte count."""

    total = 0
    with path.open("rb") as fileobj:
        while True:
            chunk = fileobj.read(int(chunk_size))
            if not chunk:
                break
            total += len(chunk)
    return total


def _host_io_write_baseline_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Measure a simple sequential local-filesystem write baseline."""

    with benchmark_workspace(workspace_root, "phase12-host-write-") as tmpdir:
        payload_size = int(max(config.large_file_size, config.mixed_large_file_size))
        chunk_size = 4 * 1024 * 1024
        target = Path(tmpdir) / "host-io-write.bin"
        started = time.perf_counter()
        written = _stream_write_file(target, payload_size, chunk_size, "host-io-write")
        finished = time.perf_counter()
        return {
            "processed_bytes": written,
            "operation_seconds": _round_metric(finished - started),
            "operation_count": 1,
            "dataset_family": "host-seq-io",
            "baseline_kind": "write",
        }


def _host_io_read_baseline_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    """Measure a simple sequential local-filesystem read baseline."""

    with benchmark_workspace(workspace_root, "phase12-host-read-") as tmpdir:
        payload_size = int(max(config.large_file_size, config.mixed_large_file_size))
        chunk_size = 4 * 1024 * 1024
        target = Path(tmpdir) / "host-io-read.bin"
        written = _stream_write_file(target, payload_size, chunk_size, "host-io-read-setup")
        started = time.perf_counter()
        read_bytes = _stream_read_file(target, chunk_size)
        finished = time.perf_counter()
        return {
            "processed_bytes": read_bytes,
            "operation_seconds": _round_metric(finished - started),
            "operation_count": 1,
            "dataset_family": "host-seq-io",
            "baseline_kind": "read",
            "prepared_bytes": written,
        }


def _small_read_all_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-small-read-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        processed = read_all_small_files(api, paths)
        finished = time.perf_counter()
        return {
            "processed_bytes": processed,
            "operation_seconds": _round_metric(finished - started),
            "operation_count": len(paths),
            "reported_read_seconds": _round_metric(finished - started),
            "live_file_count": len(paths),
            "logical_live_bytes": total_bytes,
            "dataset_family": "small-tree",
        }


def _snapshot_download_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-snapshot-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        before = api.get_storage_overview()
        started = time.perf_counter()
        snapshot_root = Path(api.snapshot_download())
        finished = time.perf_counter()
        after = api.get_storage_overview()
        manifest = snapshot_file_manifest(snapshot_root)
        return {
            "processed_bytes": total_bytes,
            "operation_seconds": _round_metric(finished - started),
            "operation_count": len(manifest),
            "reported_snapshot_seconds": _round_metric(finished - started),
            "snapshot_file_count": len(manifest),
            "files_materialized": len(manifest),
            "live_file_count": len(paths),
            "cache_delta_bytes": int(after.reclaimable_cache_size - before.reclaimable_cache_size),
            "dataset_family": "small-tree",
        }


def _nested_tree_listing_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_nested_tree_listing_case(workspace_root, config)


def _mixed_model_snapshot_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_mixed_model_snapshot_case(workspace_root, config)


def _large_upload_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-large-write-") as tmpdir:
        repo_dir = Path(tmpdir) / "repo"
        api = HubVaultApi(repo_dir)
        create_repo(api, large_file_threshold=int(config.chunk_threshold))
        payload = deterministic_bytes(int(config.large_file_size), "large-binary")
        started = time.perf_counter()
        api.upload_file(
            path_or_fileobj=payload,
            path_in_repo="artifacts/model.bin",
            commit_message="seed large file",
        )
        finished = time.perf_counter()
        overview = api.get_storage_overview()
        return {
            "processed_bytes": len(payload),
            "operation_seconds": _round_metric(finished - started),
            "repo_total_bytes": int(overview.total_size),
            "chunk_pack_bytes": next(section.total_size for section in overview.sections if section.name == "chunks.packs"),
            "chunk_index_bytes": next(section.total_size for section in overview.sections if section.name == "chunks.index"),
            "operation_count": 1,
            "dataset_family": "large-single",
        }


def _large_read_range_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-large-read-") as tmpdir:
        api, _payload = build_large_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        data = api.read_range(
            "artifacts/model.bin",
            start=int(config.range_start),
            length=int(config.range_length),
        )
        finished = time.perf_counter()
        return {
            "processed_bytes": len(data),
            "operation_seconds": _round_metric(finished - started),
            "operation_count": 1,
            "reported_range_read_seconds": _round_metric(finished - started),
            "dataset_family": "large-single",
        }


def _hf_hub_download_cold_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_hf_hub_download_cold_case(workspace_root, config)


def _hf_hub_download_warm_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_hf_hub_download_warm_case(workspace_root, config)


def _cache_heavy_warm_download_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_cache_heavy_warm_download_case(workspace_root, config)


def _history_listing_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_history_listing_case(workspace_root, config)


def _history_deep_listing_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_history_deep_listing_case(workspace_root, config)


def _merge_non_fast_forward_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_merge_non_fast_forward_case(workspace_root, config)


def _merge_heavy_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_merge_heavy_case(workspace_root, config)


def _threshold_sweep_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_threshold_sweep_case(workspace_root, config)


def _exact_duplicate_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-exact-") as tmpdir:
        api, logical_live_total, logical_unique = build_exact_duplicate_live_repo(Path(tmpdir) / "repo", config)
        metrics = collect_space_profile(api, logical_live_total, logical_unique)
        metrics["dataset_family"] = "exact-duplicate-live"
        return metrics


def _aligned_overlap_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-aligned-") as tmpdir:
        api, logical_live_total, logical_unique = build_aligned_overlap_live_repo(Path(tmpdir) / "repo", config)
        metrics = collect_space_profile(api, logical_live_total, logical_unique)
        metrics["dataset_family"] = "aligned-overlap-live"
        return metrics


def _shifted_overlap_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-shifted-") as tmpdir:
        api, logical_live_total, logical_unique = build_shifted_overlap_live_repo(Path(tmpdir) / "repo", config)
        metrics = collect_space_profile(api, logical_live_total, logical_unique)
        metrics["dataset_family"] = "shifted-overlap-live"
        return metrics


def _historical_duplicate_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-history-") as tmpdir:
        api, logical_live_total, logical_unique = build_historical_duplicate_repo(Path(tmpdir) / "repo", config)
        metrics = collect_space_profile(api, logical_live_total, logical_unique)
        metrics["dataset_family"] = "historical-duplicate"
        return metrics


def _full_verify_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-verify-") as tmpdir:
        api, logical_live_total = build_maintenance_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        report = api.full_verify()
        finished = time.perf_counter()
        return {
            "processed_bytes": logical_live_total,
            "operation_seconds": _round_metric(finished - started),
            "reported_full_verify_seconds": _round_metric(finished - started),
            "verify_ok": bool(report.ok),
            "operation_count": max(1, len(list(api.list_repo_files()))),
            "dataset_family": "maintenance-heavy",
        }


def _verify_heavy_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_verify_heavy_case(workspace_root, config)


def _squash_history_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_squash_history_case(workspace_root, config)


def _decorate_result(name: str, result: Dict[str, object]) -> Dict[str, object]:
    """Attach scenario contracts to one measured result."""

    contracts = _scenario_contracts().get(name, {})
    decorated = dict(result)
    metrics = dict(decorated.get("metrics", {}))
    dataset_family = metrics.get("dataset_family")
    if dataset_family is not None:
        decorated["dataset_family"] = dataset_family
    if "category" in contracts:
        decorated["category"] = contracts["category"]
    if "temperature" in contracts:
        decorated["temperature"] = contracts["temperature"]
    if "public_surface" in contracts:
        decorated["public_surface"] = contracts["public_surface"]
    if "reference_only" in contracts:
        decorated["reference_only"] = bool(contracts["reference_only"])
    decorated["metrics"] = metrics
    return decorated


def _build_io_reference_summary(results: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    """Compare hubvault large-file paths against the host sequential IO baseline."""

    write_baseline = results.get("host_io_write_baseline", {})
    read_baseline = results.get("host_io_read_baseline", {})
    write_throughput = float(write_baseline.get("throughput_mib_per_sec", 0.0))
    read_throughput = float(read_baseline.get("throughput_mib_per_sec", 0.0))
    summary = {
        "write_baseline_throughput_mib_per_sec": _round_metric(write_throughput),
        "read_baseline_throughput_mib_per_sec": _round_metric(read_throughput),
    }
    comparisons = (
        ("large_upload", "large_upload_vs_write_baseline_ratio", write_throughput),
        ("large_read_range", "large_read_range_vs_read_baseline_ratio", read_throughput),
        ("hf_hub_download_cold", "hf_hub_download_cold_vs_read_baseline_ratio", read_throughput),
        ("hf_hub_download_warm", "hf_hub_download_warm_vs_read_baseline_ratio", read_throughput),
        ("cache_heavy_warm_download", "cache_heavy_warm_download_vs_read_baseline_ratio", read_throughput),
    )
    for scenario_name, ratio_key, baseline in comparisons:
        scenario = results.get(scenario_name, {})
        throughput = float(scenario.get("throughput_mib_per_sec", 0.0))
        if baseline > 0.0 and throughput > 0.0:
            summary[ratio_key] = _round_metric(throughput / baseline)
    return summary


def _build_category_summaries(results: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    """Build per-category summaries without collapsing everything into one score."""

    category_map = _category_map()
    category_summaries = {}
    for category, scenario_names in category_map.items():
        names = [name for name in scenario_names if name in results]
        rows = [results[name] for name in names]
        latencies = [float(row.get("latency_p50_seconds", 0.0)) for row in rows if "latency_p50_seconds" in row]
        latency_iqrs = [float(row.get("latency_iqr_seconds", 0.0)) for row in rows if "latency_iqr_seconds" in row]
        throughputs = [float(row.get("throughput_mib_per_sec", 0.0)) for row in rows if "throughput_mib_per_sec" in row]
        ops = [float(row.get("operations_per_sec", 0.0)) for row in rows if "operations_per_sec" in row]
        file_rates = [
            float(row.get("metrics", {}).get("files_materialized_per_sec", 0.0))
            for row in rows
            if "files_materialized_per_sec" in row.get("metrics", {})
        ]
        write_amps = [
            float(row.get("metrics", {}).get("write_amplification", 0.0))
            for row in rows
            if "write_amplification" in row.get("metrics", {})
        ]
        cache_amps = [
            float(row.get("metrics", {}).get("cache_amplification", 0.0))
            for row in rows
            if "cache_amplification" in row.get("metrics", {})
        ]
        live_space_amps = [
            float(row.get("metrics", {}).get("space_amplification_live_after_gc", 0.0))
            for row in rows
            if "space_amplification_live_after_gc" in row.get("metrics", {})
        ]
        unique_space_amps = [
            float(row.get("metrics", {}).get("space_amplification_unique_after_gc", 0.0))
            for row in rows
            if "space_amplification_unique_after_gc" in row.get("metrics", {})
        ]
        summary = {
            "scenario_count": len(names),
            "scenarios": names,
        }
        if latencies:
            summary["median_latency_p50_seconds"] = _round_metric(_median_or_zero(latencies))
        if latency_iqrs:
            summary["median_latency_iqr_seconds"] = _round_metric(_median_or_zero(latency_iqrs))
            summary["max_latency_iqr_seconds"] = _round_metric(max(latency_iqrs))
        if throughputs:
            summary["median_throughput_mib_per_sec"] = _round_metric(_median_or_zero(throughputs))
        if ops:
            summary["median_operations_per_sec"] = _round_metric(_median_or_zero(ops))
        if file_rates:
            summary["median_files_materialized_per_sec"] = _round_metric(_median_or_zero(file_rates))
        if write_amps:
            summary["median_write_amplification"] = _round_metric(_median_or_zero(write_amps))
        if cache_amps:
            summary["median_cache_amplification"] = _round_metric(_median_or_zero(cache_amps))
        if live_space_amps:
            summary["median_space_amplification_live_after_gc"] = _round_metric(_median_or_zero(live_space_amps))
        if unique_space_amps:
            summary["median_space_amplification_unique_after_gc"] = _round_metric(_median_or_zero(unique_space_amps))
        category_summaries[category] = summary
    return category_summaries


def main() -> int:
    """Run the benchmark suite."""

    parser = argparse.ArgumentParser(description="Run the hubvault benchmark suite.")
    parser.add_argument(
        "--scale",
        default="standard",
        choices=("smoke", "standard", "nightly", "stress", "pressure"),
    )
    parser.add_argument(
        "--scenario-set",
        default="full",
        choices=("full", "pressure"),
        help="Choose the full benchmark suite or the large-file pressure subset.",
    )
    parser.add_argument("--rounds", type=int, default=None, help="Override the configured benchmark rounds.")
    parser.add_argument("--warmup-rounds", type=int, default=None, help="Override warmup rounds.")
    parser.add_argument("--output", default=None, help="Optional summary JSON output path.")
    parser.add_argument("--manifest-output", default=None, help="Optional manifest JSON output path.")
    args = parser.parse_args()

    config = Phase9BenchmarkConfig.from_scale(args.scale)
    rounds = int(args.rounds) if args.rounds is not None else int(config.rounds)
    warmup_rounds = int(args.warmup_rounds) if args.warmup_rounds is not None else int(config.warmup_rounds)

    full_scenarios = [
        ("small_batch_commit", _small_batch_commit_scenario),
        ("host_io_write_baseline", _host_io_write_baseline_scenario),
        ("host_io_read_baseline", _host_io_read_baseline_scenario),
        ("small_read_all", _small_read_all_scenario),
        ("nested_tree_listing", _nested_tree_listing_scenario),
        ("snapshot_download_small", _snapshot_download_scenario),
        ("mixed_model_snapshot", _mixed_model_snapshot_scenario),
        ("large_upload", _large_upload_scenario),
        ("host_io_write_baseline", _host_io_write_baseline_scenario),
        ("host_io_read_baseline", _host_io_read_baseline_scenario),
        ("large_read_range", _large_read_range_scenario),
        ("hf_hub_download_cold", _hf_hub_download_cold_scenario),
        ("hf_hub_download_warm", _hf_hub_download_warm_scenario),
        ("cache_heavy_warm_download", _cache_heavy_warm_download_scenario),
        ("history_listing", _history_listing_scenario),
        ("history_deep_listing", _history_deep_listing_scenario),
        ("merge_non_fast_forward", _merge_non_fast_forward_scenario),
        ("merge_heavy_non_fast_forward", _merge_heavy_scenario),
        ("threshold_sweep", _threshold_sweep_scenario),
        ("exact_duplicate_live_space", _exact_duplicate_space_scenario),
        ("aligned_overlap_live_space", _aligned_overlap_space_scenario),
        ("shifted_overlap_live_space", _shifted_overlap_space_scenario),
        ("historical_duplicate_space", _historical_duplicate_space_scenario),
        ("full_verify", _full_verify_scenario),
        ("verify_heavy_full_verify", _verify_heavy_scenario),
        ("squash_history", _squash_history_scenario),
    ]
    pressure_scenarios = [
        ("large_upload", _large_upload_scenario),
        ("large_read_range", _large_read_range_scenario),
        ("hf_hub_download_cold", _hf_hub_download_cold_scenario),
        ("hf_hub_download_warm", _hf_hub_download_warm_scenario),
        ("cache_heavy_warm_download", _cache_heavy_warm_download_scenario),
        ("exact_duplicate_live_space", _exact_duplicate_space_scenario),
        ("aligned_overlap_live_space", _aligned_overlap_space_scenario),
        ("shifted_overlap_live_space", _shifted_overlap_space_scenario),
        ("historical_duplicate_space", _historical_duplicate_space_scenario),
    ]
    scenarios = full_scenarios if args.scenario_set == "full" else pressure_scenarios

    with tempfile.TemporaryDirectory(prefix="hubvault-phase12-run-") as tmpdir:
        workspace_root = Path(tmpdir)
        results = {}
        for name, scenario in scenarios:
            measured = _measure_seconds(
                lambda current=scenario: current(workspace_root, config),
                rounds=rounds,
                warmup_rounds=warmup_rounds,
            )
            results[name] = _decorate_result(name, measured)

    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    category_summaries = _build_category_summaries(results)
    summary = {
        "generated_at_utc": generated_at_utc,
        "git": _git_metadata(),
        "config": {
            "scale": config.scale,
            "scenario_set": args.scenario_set,
            "rounds": rounds,
            "warmup_rounds": warmup_rounds,
            "small_file_count": config.small_file_count,
            "small_file_size": config.small_file_size,
            "nested_directory_count": config.nested_directory_count,
            "nested_files_per_directory": config.nested_files_per_directory,
            "mixed_large_file_size": config.mixed_large_file_size,
            "history_deep_depth": config.history_deep_depth,
            "merge_side_commit_count": config.merge_side_commit_count,
            "cache_warm_rounds": config.cache_warm_rounds,
            "large_file_size": config.large_file_size,
            "duplicate_file_count": config.duplicate_file_count,
            "overlap_shared_size": config.overlap_shared_size,
            "overlap_unique_size": config.overlap_unique_size,
            "shifted_window_step": config.shifted_window_step,
            "history_depth": config.history_depth,
            "chunk_threshold": config.chunk_threshold,
            "range_start": config.range_start,
            "range_length": config.range_length,
        },
        "dataset_shapes": _dataset_shapes(config),
        "machine": _machine_signature(),
        "categories": _category_map(),
        "category_summaries": category_summaries,
        "io_reference": _build_io_reference_summary(results),
        "threshold_policy": _threshold_policy(),
        "results": results,
    }
    summary["conclusions"] = infer_space_conclusions(results)
    upload_ratio = float(summary["io_reference"].get("large_upload_vs_write_baseline_ratio", 0.0))
    read_ratio = float(summary["io_reference"].get("large_read_range_vs_read_baseline_ratio", 0.0))
    if upload_ratio > 0.0 or read_ratio > 0.0:
        summary["conclusions"].append(
            "当前大文件路径和 host local sequential IO baseline 的相对比值也会一起记录：本次 `large_upload` 约为本机顺序写基线的 {upload:.2%}，`large_read_range` 约为顺序读基线的 {read:.2%}。".format(
                upload=upload_ratio,
                read=read_ratio,
            )
        )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    else:
        output_path = None

    if args.manifest_output:
        manifest = {
            "generated_at_utc": generated_at_utc,
            "git": summary["git"],
            "machine": summary["machine"],
            "config": summary["config"],
            "dataset_shapes": summary["dataset_shapes"],
            "categories": summary["categories"],
            "threshold_policy": summary["threshold_policy"],
            "summary_output": str(output_path) if output_path is not None else "",
        }
        manifest_path = Path(args.manifest_output)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
