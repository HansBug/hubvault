import pytest

from tools.benchmark.common import (
    build_aligned_overlap_live_repo,
    build_exact_duplicate_live_repo,
    build_large_repo,
    build_shifted_overlap_live_repo,
    collect_space_profile,
    next_round_repo_dir,
    run_cache_heavy_warm_download_case,
    run_hf_hub_download_cold_case,
    run_hf_hub_download_warm_case,
    run_threshold_sweep_case,
    section_size,
)


@pytest.mark.benchmark
class TestPhase9LargeBenchmarks:
    def test_phase9_benchmark_large_upload_end_to_end(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = next_round_repo_dir(tmp_path, "large-upload")
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

        def run_once():
            current = api.read_range(
                path_in_repo=path_in_repo,
                start=phase9_config.range_start,
                length=phase9_config.range_length,
            )
            assert current == expected
            return current

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
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_exact_duplicate_large_live_space(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = next_round_repo_dir(tmp_path, "exact-duplicates")
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
            repo_dir = next_round_repo_dir(tmp_path, "aligned-overlap")
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
            repo_dir = next_round_repo_dir(tmp_path, "shifted-overlap")
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

    def test_phase9_benchmark_hf_hub_download_cold_large_file(self, benchmark, tmp_path, phase9_config):
        reference = run_hf_hub_download_cold_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "hf_hub_download_cold_large_file"
        benchmark.pedantic(
            lambda: run_hf_hub_download_cold_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_hf_hub_download_warm_large_file(self, benchmark, tmp_path, phase9_config):
        reference = run_hf_hub_download_warm_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "hf_hub_download_warm_large_file"
        benchmark.pedantic(
            lambda: run_hf_hub_download_warm_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase12_benchmark_cache_heavy_warm_download(self, benchmark, tmp_path, phase9_config):
        reference = run_cache_heavy_warm_download_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "cache_heavy_warm_download"
        benchmark.pedantic(
            lambda: run_cache_heavy_warm_download_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_threshold_sweep_whole_file_vs_chunked_boundary(self, benchmark, tmp_path, phase9_config):
        reference = run_threshold_sweep_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "threshold_sweep_whole_file_vs_chunked_boundary"
        benchmark.pedantic(
            lambda: run_threshold_sweep_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )
