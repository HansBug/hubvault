import pytest

from tools.benchmark.common import (
    run_history_listing_case,
    run_merge_non_fast_forward_case,
)


@pytest.mark.benchmark
class TestPhase9HistoryBenchmarks:
    def test_phase9_benchmark_history_listing_on_deep_repo(self, benchmark, tmp_path, phase9_config):
        reference = run_history_listing_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "history_listing_on_deep_repo"
        benchmark.pedantic(
            lambda: run_history_listing_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_merge_non_fast_forward_public_workflow(self, benchmark, tmp_path, phase9_config):
        reference = run_merge_non_fast_forward_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "merge_non_fast_forward_public_workflow"
        benchmark.pedantic(
            lambda: run_merge_non_fast_forward_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )
