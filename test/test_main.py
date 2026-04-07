import runpy
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unittest
class TestMainModule:
    def test_runpy_main_help(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["hubvault", "--help"])

        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("hubvault.__main__", run_name="__main__")

        captured = capsys.readouterr()
        assert exc_info.value.code == 0
        assert "usage" in captured.out.lower()

    def test_runpy_main_version(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["hubvault", "--version"])

        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("hubvault.__main__", run_name="__main__")

        captured = capsys.readouterr()
        assert exc_info.value.code == 0
        assert "hubvault, version" in captured.out.lower()

    def test_python_module_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "hubvault", "--help"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "hubvault" in result.stdout.lower()

    def test_python_module_version(self):
        result = subprocess.run(
            [sys.executable, "-m", "hubvault", "--version"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "hubvault, version" in result.stdout.lower()
