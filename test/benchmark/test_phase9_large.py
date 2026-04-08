import pytest

from tools.benchmark.common import (
    build_aligned_overlap_live_repo,
    build_exact_duplicate_live_repo,
    build_large_repo,
    build_shifted_overlap_live_repo,
    collect_space_profile,
    section_size,
)


@pytest.mark.benchmark
class TestPhase9LargeBenchmarks:
    def test_phase9_benchmark_large_upload_end_to_end(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = tmp_path / "large-upload" / ("round-%08d" % len(list((tmp_path / "large-upload").glob("*"))))
            api, payload = build_large_repo(repo_dir, phase9_config)
            return {
                "processed_bytes": len(payload),
                "chunk_pack_bytes": section_size(api, "chunks.packs"),
                "chunk_index_bytes": section_size(api, "chunks.index"),
            }

        reference = run_once()
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "large_upload_end_to_end"
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_large_read_range(self, benchmark, tmp_path, phase9_config):
        api, payload = build_large_repo(tmp_path / "large-read-range", phase9_config)
        path_in_repo = "artifacts/model.bin"
        expected = payload[phase9_config.range_start:phase9_config.range_start + phase9_config.range_length]

        benchmark.extra_info.update(
            {
                "scenario": "large_read_range",
                "processed_bytes": len(expected),
                "range_start": phase9_config.range_start,
                "range_length": phase9_config.range_length,
                "file_size": len(payload),
            }
        )
        benchmark.pedantic(
            api.read_range,
            kwargs={
                "path_in_repo": path_in_repo,
                "start": phase9_config.range_start,
                "length": phase9_config.range_length,
            },
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_exact_duplicate_large_live_space(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = tmp_path / "exact-duplicates" / ("round-%08d" % len(list((tmp_path / "exact-duplicates").glob("*"))))
            api, logical_live_total, logical_unique = build_exact_duplicate_live_repo(repo_dir, phase9_config)
            return collect_space_profile(api, logical_live_total, logical_unique)

        reference = run_once()
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "exact_duplicate_large_live_space"
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_aligned_overlap_large_live_space(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = tmp_path / "aligned-overlap" / ("round-%08d" % len(list((tmp_path / "aligned-overlap").glob("*"))))
            api, logical_live_total, logical_unique = build_aligned_overlap_live_repo(repo_dir, phase9_config)
            return collect_space_profile(api, logical_live_total, logical_unique)

        reference = run_once()
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "aligned_overlap_large_live_space"
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_shifted_overlap_large_live_space(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = tmp_path / "shifted-overlap" / ("round-%08d" % len(list((tmp_path / "shifted-overlap").glob("*"))))
            api, logical_live_total, logical_unique = build_shifted_overlap_live_repo(repo_dir, phase9_config)
            return collect_space_profile(api, logical_live_total, logical_unique)

        reference = run_once()
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "shifted_overlap_large_live_space"
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )
