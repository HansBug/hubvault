"""Run the Phase 9 benchmark suite and print a JSON summary."""

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List

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
    run_hf_hub_download_cold_case,
    run_hf_hub_download_warm_case,
    run_history_listing_case,
    run_merge_non_fast_forward_case,
    run_squash_history_case,
    run_threshold_sweep_case,
    snapshot_file_manifest,
    to_mib,
)


def _measure_seconds(func: Callable[[], Dict[str, object]], rounds: int, warmup_rounds: int) -> Dict[str, object]:
    """Measure one callable for a fixed number of rounds."""

    for _ in range(max(0, int(warmup_rounds))):
        func()

    samples = []
    metrics = None
    for _ in range(max(1, int(rounds))):
        started = time.perf_counter()
        metrics = func()
        ended = time.perf_counter()
        samples.append(ended - started)

    median_seconds = statistics.median(samples)
    result = {
        "rounds": len(samples),
        "seconds": {
            "median": round(median_seconds, 6),
            "min": round(min(samples), 6),
            "max": round(max(samples), 6),
            "samples": [round(item, 6) for item in samples],
        },
        "metrics": metrics or {},
    }
    processed_bytes = int((metrics or {}).get("processed_bytes", 0))
    operation_seconds = float((metrics or {}).get("operation_seconds", median_seconds))
    if processed_bytes > 0 and operation_seconds > 0.0:
        result["throughput_mib_per_sec"] = round(to_mib(processed_bytes) / operation_seconds, 6)
    return result


def _small_batch_commit_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-small-write-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        overview = api.get_storage_overview()
        return {
            "processed_bytes": total_bytes,
            "repo_total_bytes": int(overview.total_size),
            "reachable_bytes": int(overview.reachable_size),
            "live_file_count": len(paths),
        }


def _small_read_all_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-small-read-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        processed = read_all_small_files(api, paths)
        finished = time.perf_counter()
        return {
            "processed_bytes": processed,
            "operation_seconds": round(finished - started, 6),
            "reported_read_seconds": round(finished - started, 6),
            "live_file_count": len(paths),
            "logical_live_bytes": total_bytes,
        }


def _snapshot_download_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-snapshot-") as tmpdir:
        api, paths, total_bytes = build_small_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        snapshot_root = Path(api.snapshot_download())
        finished = time.perf_counter()
        manifest = snapshot_file_manifest(snapshot_root)
        return {
            "processed_bytes": total_bytes,
            "operation_seconds": round(finished - started, 6),
            "reported_snapshot_seconds": round(finished - started, 6),
            "snapshot_file_count": len(manifest),
            "live_file_count": len(paths),
        }


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
            "operation_seconds": round(finished - started, 6),
            "repo_total_bytes": int(overview.total_size),
            "chunk_pack_bytes": next(section.total_size for section in overview.sections if section.name == "chunks.packs"),
            "chunk_index_bytes": next(section.total_size for section in overview.sections if section.name == "chunks.index"),
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
            "operation_seconds": round(finished - started, 6),
            "reported_range_read_seconds": round(finished - started, 6),
        }


def _hf_hub_download_cold_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_hf_hub_download_cold_case(workspace_root, config)


def _hf_hub_download_warm_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_hf_hub_download_warm_case(workspace_root, config)


def _history_listing_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_history_listing_case(workspace_root, config)


def _merge_non_fast_forward_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_merge_non_fast_forward_case(workspace_root, config)


def _threshold_sweep_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_threshold_sweep_case(workspace_root, config)


def _exact_duplicate_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-exact-") as tmpdir:
        api, logical_live_total, logical_unique = build_exact_duplicate_live_repo(Path(tmpdir) / "repo", config)
        return collect_space_profile(api, logical_live_total, logical_unique)


def _aligned_overlap_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-aligned-") as tmpdir:
        api, logical_live_total, logical_unique = build_aligned_overlap_live_repo(Path(tmpdir) / "repo", config)
        return collect_space_profile(api, logical_live_total, logical_unique)


def _shifted_overlap_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-shifted-") as tmpdir:
        api, logical_live_total, logical_unique = build_shifted_overlap_live_repo(Path(tmpdir) / "repo", config)
        return collect_space_profile(api, logical_live_total, logical_unique)


def _historical_duplicate_space_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-space-history-") as tmpdir:
        api, logical_live_total, logical_unique = build_historical_duplicate_repo(Path(tmpdir) / "repo", config)
        return collect_space_profile(api, logical_live_total, logical_unique)


def _full_verify_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    with benchmark_workspace(workspace_root, "phase9-run-verify-") as tmpdir:
        api, logical_live_total = build_maintenance_repo(Path(tmpdir) / "repo", config)
        started = time.perf_counter()
        report = api.full_verify()
        finished = time.perf_counter()
        return {
            "processed_bytes": logical_live_total,
            "operation_seconds": round(finished - started, 6),
            "reported_full_verify_seconds": round(finished - started, 6),
            "verify_ok": bool(report.ok),
        }


def _squash_history_scenario(workspace_root: Path, config: Phase9BenchmarkConfig) -> Dict[str, object]:
    return run_squash_history_case(workspace_root, config)


def main() -> int:
    """Run the benchmark suite."""

    parser = argparse.ArgumentParser(description="Run the Phase 9 hubvault benchmark suite.")
    parser.add_argument("--scale", default="standard", choices=("smoke", "standard", "stress", "pressure"))
    parser.add_argument(
        "--scenario-set",
        default="full",
        choices=("full", "pressure"),
        help="Choose the full baseline suite or the GB-scale pressure subset.",
    )
    parser.add_argument("--rounds", type=int, default=None, help="Override the configured benchmark rounds.")
    parser.add_argument("--warmup-rounds", type=int, default=None, help="Override warmup rounds.")
    parser.add_argument("--output", default=None, help="Optional JSON output path.")
    args = parser.parse_args()

    config = Phase9BenchmarkConfig.from_scale(args.scale)
    rounds = int(args.rounds) if args.rounds is not None else int(config.rounds)
    warmup_rounds = int(args.warmup_rounds) if args.warmup_rounds is not None else int(config.warmup_rounds)

    full_scenarios = [
        ("small_batch_commit", _small_batch_commit_scenario),
        ("small_read_all", _small_read_all_scenario),
        ("snapshot_download_small", _snapshot_download_scenario),
        ("large_upload", _large_upload_scenario),
        ("large_read_range", _large_read_range_scenario),
        ("hf_hub_download_cold", _hf_hub_download_cold_scenario),
        ("hf_hub_download_warm", _hf_hub_download_warm_scenario),
        ("history_listing", _history_listing_scenario),
        ("merge_non_fast_forward", _merge_non_fast_forward_scenario),
        ("threshold_sweep", _threshold_sweep_scenario),
        ("exact_duplicate_live_space", _exact_duplicate_space_scenario),
        ("aligned_overlap_live_space", _aligned_overlap_space_scenario),
        ("shifted_overlap_live_space", _shifted_overlap_space_scenario),
        ("historical_duplicate_space", _historical_duplicate_space_scenario),
        ("full_verify", _full_verify_scenario),
        ("squash_history", _squash_history_scenario),
    ]
    pressure_scenarios = [
        ("large_upload", _large_upload_scenario),
        ("large_read_range", _large_read_range_scenario),
        ("hf_hub_download_cold", _hf_hub_download_cold_scenario),
        ("exact_duplicate_live_space", _exact_duplicate_space_scenario),
        ("aligned_overlap_live_space", _aligned_overlap_space_scenario),
        ("shifted_overlap_live_space", _shifted_overlap_space_scenario),
    ]
    scenarios = full_scenarios if args.scenario_set == "full" else pressure_scenarios

    with tempfile.TemporaryDirectory(prefix="hubvault-phase9-run-") as tmpdir:
        workspace_root = Path(tmpdir)
        results = {}
        for name, scenario in scenarios:
            results[name] = _measure_seconds(
                lambda current=scenario: current(workspace_root, config),
                rounds=rounds,
                warmup_rounds=warmup_rounds,
            )

    summary = {
        "config": {
            "scale": config.scale,
            "scenario_set": args.scenario_set,
            "rounds": rounds,
            "warmup_rounds": warmup_rounds,
            "small_file_count": config.small_file_count,
            "small_file_size": config.small_file_size,
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
        "results": results,
    }
    summary["conclusions"] = infer_space_conclusions(results)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
