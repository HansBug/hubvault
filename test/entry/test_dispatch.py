import click
import pytest
from click.testing import CliRunner

from hubvault.config.meta import __TITLE__, __VERSION__
from hubvault.entry.dispatch import hubvaultcli, print_version


@pytest.mark.unittest
class TestEntryDispatch:
    def test_version_callback_prints_and_exits(self, capsys):
        ctx = click.Context(click.Command("demo"))
        option = click.Option(["--version"])

        with pytest.raises(click.exceptions.Exit):
            with ctx:
                print_version(ctx, option, True)

        captured = capsys.readouterr()
        assert __TITLE__ in captured.out.lower()
        assert __VERSION__ in captured.out

    def test_dispatch_group_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(hubvaultcli, ["-v"])

        assert result.exit_code == 0
        assert __VERSION__ in result.output

    def test_dispatch_group_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(hubvaultcli, ["-h"])

        assert result.exit_code == 0
        assert "usage" in result.output.lower()
