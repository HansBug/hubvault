import pytest
from pathlib import Path

from hubvault import RepoFile
from tools.benchmark.common import (
    build_nested_small_repo,
    build_small_repo,
    read_all_small_files,
    run_mixed_model_snapshot_case,
    run_small_batch_commit_case,
    snapshot_file_manifest,
)


@pytest.mark.benchmark
class TestPhase9SmallBenchmarks:
    def test_phase9_benchmark_small_batch_commit_end_to_end(self, benchmark, tmp_path, phase9_config):
        reference = run_small_batch_commit_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "small_batch_commit_end_to_end"
        benchmark.pedantic(
            lambda: run_small_batch_commit_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_small_read_all_files(self, benchmark, tmp_path, phase9_config):
        api, paths, total_bytes = build_small_repo(tmp_path / "small-read", phase9_config)
        processed = read_all_small_files(api, paths)
        assert processed == total_bytes

        def run_once():
            current_processed = read_all_small_files(api, paths)
            assert current_processed == total_bytes
            return current_processed

        benchmark.extra_info.update(
            {
                "scenario": "small_read_all_files",
                "processed_bytes": processed,
                "operation_count": len(paths),
                "live_file_count": len(paths),
                "logical_live_bytes": total_bytes,
            }
        )
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase12_benchmark_nested_tree_listing_recursive(self, benchmark, tmp_path, phase9_config):
        api, paths, total_bytes = build_nested_small_repo(tmp_path / "nested-tree", phase9_config)
        items = list(api.list_repo_tree(recursive=True))
        expected_paths = sorted(paths)
        assert sorted(item.path for item in items if isinstance(item, RepoFile)) == expected_paths

        def run_once():
            current_items = list(api.list_repo_tree(recursive=True))
            assert sorted(item.path for item in current_items if isinstance(item, RepoFile)) == expected_paths
            return current_items

        benchmark.extra_info.update(
            {
                "scenario": "nested_tree_listing_recursive",
                "processed_bytes": 0,
                "operation_count": len(items),
                "tree_entry_count": len(items),
                "live_file_count": len(paths),
                "logical_live_bytes": total_bytes,
            }
        )
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_snapshot_download_cold_small_tree(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = tmp_path / "snapshot-cold" / ("round-%08d" % len(list((tmp_path / "snapshot-cold").glob("*"))))
            api, paths, total_bytes = build_small_repo(repo_dir, phase9_config)
            snapshot_root = api.snapshot_download()
            manifest = snapshot_file_manifest(Path(snapshot_root))
            assert manifest == sorted(paths)
            return {
                "processed_bytes": total_bytes,
                "operation_count": len(manifest),
                "snapshot_file_count": len(manifest),
            }

        reference = run_once()
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "snapshot_download_cold_small_tree"
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase12_benchmark_mixed_model_snapshot_download(self, benchmark, tmp_path, phase9_config):
        reference = run_mixed_model_snapshot_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "mixed_model_snapshot_download"
        benchmark.pedantic(
            lambda: run_mixed_model_snapshot_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )
