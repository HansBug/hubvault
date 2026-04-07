import click
import pytest
from click.testing import CliRunner

from hubvault.entry.base import (
    ClickErrorException,
    ClickWarningException,
    KeyboardInterrupted,
    command_wrap,
    print_exception,
)


def _build_command(callback):
    @click.command()
    @command_wrap()
    def _command():
        return callback()

    return _command


@pytest.mark.unittest
class TestEntryBase:
    def test_print_exception_without_traceback_uses_exception_name_and_message(self):
        outputs = []

        print_exception(ValueError("invalid"), outputs.append)

        assert outputs == ["ValueError: invalid"]

    def test_print_exception_with_traceback_includes_traceback_header(self):
        outputs = []

        try:
            raise RuntimeError("boom")
        except RuntimeError as err:
            print_exception(err, outputs.append)

        assert outputs[0] == "Traceback (most recent call last):"
        assert outputs[-1] == "RuntimeError: boom"

    def test_click_warning_exception_show_writes_message(self, capsys):
        ClickWarningException("warning").show()

        captured = capsys.readouterr()
        assert "warning" in captured.err

    def test_click_error_exception_show_writes_message(self, capsys):
        ClickErrorException("error").show()

        captured = capsys.readouterr()
        assert "error" in captured.err

    def test_keyboard_interrupted_has_public_defaults(self):
        err = KeyboardInterrupted()

        assert err.exit_code == 0x7
        assert err.format_message() == "Interrupted."

    def test_command_wrap_allows_successful_command(self):
        runner = CliRunner()
        command = _build_command(lambda: click.echo("ok"))

        result = runner.invoke(command)

        assert result.exit_code == 0
        assert "ok" in result.output

    def test_command_wrap_converts_keyboard_interrupt(self):
        runner = CliRunner()
        command = _build_command(lambda: (_ for _ in ()).throw(KeyboardInterrupt()))

        result = runner.invoke(command)

        assert result.exit_code == KeyboardInterrupted.exit_code
        assert "Interrupted." in result.output

    def test_command_wrap_reraises_click_exception(self):
        runner = CliRunner()
        command = _build_command(lambda: (_ for _ in ()).throw(click.ClickException("bad command")))

        result = runner.invoke(command)

        assert result.exit_code == 1
        assert "bad command" in result.output

    def test_command_wrap_handles_unexpected_exception(self):
        runner = CliRunner()
        command = _build_command(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        result = runner.invoke(command)

        assert result.exit_code == 1
        assert "Unexpected error found when running hubvault!" in result.output
        assert "RuntimeError: boom" in result.output
