import pytest
from click.testing import CliRunner

from hubvault.config.meta import __DESCRIPTION__
from hubvault.entry.cli import cli
from hubvault.entry.dispatch import hubvaultcli


@pytest.mark.unittest
class TestEntryCliModule:
    def test_cli_module_exposes_dispatch_group(self):
        assert cli is hubvaultcli

    def test_cli_help_uses_public_description(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert __DESCRIPTION__ in result.output

