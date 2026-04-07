import pytest
from click.testing import CliRunner

import hubvault.entry as entry
from hubvault.entry import hubvaultcli
from hubvault.entry.cli import cli


@pytest.mark.unittest
class TestEntryInit:
    def test_reexport_matches_cli_group(self):
        assert entry.__all__ == ["hubvaultcli"]
        assert hubvaultcli is cli

    def test_reexported_cli_help_runs(self):
        runner = CliRunner()
        result = runner.invoke(hubvaultcli, ["--help"])

        assert result.exit_code == 0
        assert "usage" in result.output.lower()

