#!/usr/bin/env python
"""Smoke-test the built hubvault CLI executable."""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def _run(cli_path: str, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [cli_path, *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f'{result.stdout}\n{result.stderr}'.strip()


def _assert_success(name: str, result: subprocess.CompletedProcess[str], needles) -> None:
    output = _combined_output(result)
    if result.returncode != 0:
        raise AssertionError(f'{name} failed with exit code {result.returncode}: {output}')

    lowered = output.lower()
    for needle in needles:
        if needle not in lowered:
            raise AssertionError(f'{name} output missing {needle!r}: {output}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Smoke test a built hubvault CLI executable.')
    parser.add_argument('cli_path', help='Path to the built CLI executable')
    parser.add_argument('--test-dsl', help='Reserved for future functional CLI checks')
    parser.add_argument('--template-dir', help='Reserved for future functional CLI checks')
    args = parser.parse_args()

    cli_path = str(Path(args.cli_path))
    version_result = _run(cli_path, ['-v'])
    _assert_success('version', version_result, ['hubvault'])
    print('[OK] version')

    help_result = _run(cli_path, ['-h'])
    _assert_success('help', help_result, ['usage'])
    print('[OK] help')

    if args.test_dsl or args.template_dir:
        print('[OK] extra CLI fixtures acknowledged')


if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        print(f'[FAIL] {err}', file=sys.stderr)
        raise SystemExit(1)
