from pathlib import Path

import pytest
from click.testing import CliRunner

from hubvault import HubVaultApi
from hubvault.entry.cli import cli


@pytest.mark.unittest
class TestPhase6IntegratedCliLifecycle:
    def test_phase6_cli_workflow_from_init_to_merge_download_and_verify(self, tmp_path):
        repo_dir = tmp_path / "repo"
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        config_file = source_dir / "config.json"
        model_file = source_dir / "model.bin"
        feature_file = source_dir / "feature.txt"
        main_file = source_dir / "main.txt"

        config_file.write_text('{"dtype":"float16"}', encoding="utf-8")
        model_file.write_bytes(b"A" * 48)
        feature_file.write_text("feature branch note", encoding="utf-8")
        main_file.write_text("main branch note", encoding="utf-8")

        runner = CliRunner()

        assert runner.invoke(cli, ["init", str(repo_dir)]).exit_code == 0
        assert runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "seed repository",
                "--add",
                "configs/config.json={path}".format(path=str(config_file)),
                "--add",
                "models/model.bin={path}".format(path=str(model_file)),
            ],
        ).exit_code == 0
        assert runner.invoke(cli, ["-C", str(repo_dir), "branch", "feature"]).exit_code == 0
        assert runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "--revision",
                "feature",
                "-m",
                "feature add note",
                "--add",
                "notes/feature.txt={path}".format(path=str(feature_file)),
            ],
        ).exit_code == 0
        assert runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "main add note",
                "--add",
                "notes/main.txt={path}".format(path=str(main_file)),
            ],
        ).exit_code == 0

        merge_result = runner.invoke(
            cli,
            ["-C", str(repo_dir), "merge", "feature", "-m", "merge feature"],
        )
        log_result = runner.invoke(cli, ["-C", str(repo_dir), "log", "--oneline"])
        download_result = runner.invoke(cli, ["-C", str(repo_dir), "download", "notes/feature.txt"])
        snapshot_result = runner.invoke(cli, ["-C", str(repo_dir), "snapshot"])
        verify_result = runner.invoke(cli, ["-C", str(repo_dir), "verify", "--full"])

        assert merge_result.exit_code == 0
        assert "Merge made by the 'hubvault' strategy." in merge_result.output

        assert log_result.exit_code == 0
        log_lines = [line for line in log_result.output.splitlines() if line.strip()]
        assert len(log_lines) == 5
        assert any("merge feature" in line for line in log_lines)
        assert any("Initial commit" in line for line in log_lines)

        assert download_result.exit_code == 0
        download_path = Path(download_result.output.strip())
        assert download_path.parts[-2:] == ("notes", "feature.txt")
        assert download_path.read_text(encoding="utf-8") == "feature branch note"

        assert snapshot_result.exit_code == 0
        snapshot_path = Path(snapshot_result.output.strip())
        assert snapshot_path.joinpath("configs", "config.json").read_text(encoding="utf-8") == '{"dtype":"float16"}'
        assert snapshot_path.joinpath("notes", "main.txt").read_text(encoding="utf-8") == "main branch note"
        assert snapshot_path.joinpath("notes", "feature.txt").read_text(encoding="utf-8") == "feature branch note"

        assert verify_result.exit_code == 0
        assert "Full verification OK" in verify_result.output

        api = HubVaultApi(repo_dir)
        assert sorted(api.list_repo_files(revision="main")) == [
            "configs/config.json",
            "models/model.bin",
            "notes/feature.txt",
            "notes/main.txt",
        ]
        assert api.read_bytes("notes/feature.txt", revision="main") == b"feature branch note"
