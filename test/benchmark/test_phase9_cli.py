import pytest
from click.testing import CliRunner

from hubvault.entry import hubvaultcli
from tools.benchmark.common import build_small_repo


@pytest.mark.benchmark
class TestPhase9CliBenchmarks:
    def test_phase9_benchmark_cli_read_only_status_log_ls_tree_verify(self, benchmark, tmp_path, phase9_config):
        repo_dir = tmp_path / "cli-read-only"
        _api, paths, _total_bytes = build_small_repo(repo_dir, phase9_config)
        runner = CliRunner()

        def run_once():
            env = {"NO_COLOR": "1", "HUBVAULT_NO_COLOR": "1"}
            status_result = runner.invoke(
                hubvaultcli,
                ["-C", str(repo_dir), "status", "--short", "--branch"],
                env=env,
            )
            log_result = runner.invoke(
                hubvaultcli,
                ["-C", str(repo_dir), "log", "-n", "3", "--oneline"],
                env=env,
            )
            tree_result = runner.invoke(
                hubvaultcli,
                ["-C", str(repo_dir), "ls-tree", "-r"],
                env=env,
            )
            verify_result = runner.invoke(
                hubvaultcli,
                ["-C", str(repo_dir), "verify"],
                env=env,
            )
            assert status_result.exit_code == 0
            assert log_result.exit_code == 0
            assert tree_result.exit_code == 0
            assert verify_result.exit_code == 0
            return {
                "processed_bytes": 0,
                "path_count": len(paths),
                "status_output_bytes": len(status_result.output.encode("utf-8")),
                "log_output_bytes": len(log_result.output.encode("utf-8")),
                "tree_output_bytes": len(tree_result.output.encode("utf-8")),
                "verify_output_bytes": len(verify_result.output.encode("utf-8")),
            }

        reference = run_once()
        benchmark.extra_info.update(reference)
        benchmark.extra_info["scenario"] = "cli_read_only_status_log_ls_tree_verify"
        benchmark.pedantic(
            run_once,
            rounds=phase9_config.rounds,
            warmup_rounds=phase9_config.warmup_rounds,
            iterations=1,
        )
