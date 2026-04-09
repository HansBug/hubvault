import pytest

from tools.benchmark.common import (
    build_historical_duplicate_repo,
    build_maintenance_repo,
    collect_space_profile,
    next_round_repo_dir,
    run_squash_history_case,
    run_verify_heavy_case,
)


@pytest.mark.benchmark
class TestPhase9MaintenanceBenchmarks:
    def test_phase9_benchmark_full_verify_on_history_heavy_repo(self, benchmark, tmp_path, phase9_config):
        api, logical_live_total = build_maintenance_repo(tmp_path / "maintenance-verify", phase9_config)
        report = api.full_verify()

        benchmark.extra_info.update(
            {
                "scenario": "full_verify_history_heavy",
                "processed_bytes": logical_live_total,
                "verify_ok": bool(report.ok),
            }
        )
        benchmark.pedantic(
            api.full_verify,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_historical_duplicate_space_and_gc(self, benchmark, tmp_path, phase9_config):
        def run_once():
            repo_dir = next_round_repo_dir(tmp_path, "historical-duplicates")
            api, logical_live_total, logical_unique = build_historical_duplicate_repo(repo_dir, phase9_config)
            return collect_space_profile(api, logical_live_total, logical_unique)

        reference = run_once()
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "historical_duplicate_space_and_gc"
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase9_benchmark_squash_history_with_followup_gc(self, benchmark, tmp_path, phase9_config):
        reference = run_squash_history_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "squash_history_with_followup_gc"
        benchmark.pedantic(
            lambda: run_squash_history_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )

    def test_phase12_benchmark_verify_heavy_full_verify(self, benchmark, tmp_path, phase9_config):
        reference = run_verify_heavy_case(tmp_path, phase9_config)
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "verify_heavy_full_verify"
        benchmark.pedantic(
            lambda: run_verify_heavy_case(tmp_path, phase9_config),
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )
