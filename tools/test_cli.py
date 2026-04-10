#!/usr/bin/env python
"""Smoke-test the built hubvault CLI executable."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Optional, Sequence


def _run(cli_path: str, args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [cli_path, *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _combined_output(result: subprocess.CompletedProcess) -> str:
    return f'{result.stdout}\n{result.stderr}'.strip()


def _assert_success(name: str, result: subprocess.CompletedProcess, needles: Iterable[str]) -> None:
    output = _combined_output(result)
    if result.returncode != 0:
        raise AssertionError(f'{name} failed with exit code {result.returncode}: {output}')

    lowered = output.lower()
    for needle in needles:
        if needle not in lowered:
            raise AssertionError(f'{name} output missing {needle!r}: {output}')


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Smoke test a built hubvault CLI executable.')
    parser.add_argument('cli_path', help='Path to the built CLI executable')
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parse_args(argv)

    cli_path = str(Path(args.cli_path))
    version_result = _run(cli_path, ['-v'])
    _assert_success('version', version_result, ['hubvault', 'version'])
    print('[OK] version')

    help_result = _run(cli_path, ['-h'])
    _assert_success('help', help_result, ['usage', '--version'])
    print('[OK] help')

    init_help_result = _run(cli_path, ['init', '--help'])
    _assert_success('init help', init_help_result, ['usage', '--initial-branch', '--large-file-threshold'])
    print('[OK] init help')

    branch_help_result = _run(cli_path, ['branch', '--help'])
    _assert_success('branch help', branch_help_result, ['usage', '--show-current', '--verbose'])
    print('[OK] branch help')

    verify_help_result = _run(cli_path, ['verify', '--help'])
    _assert_success('verify help', verify_help_result, ['usage', '--full'])
    print('[OK] verify help')

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        repo_dir = tmp_path / 'repo'
        payload_file = tmp_path / 'payload.bin'
        payload_file.write_bytes(b'hello')

        init_result = _run(cli_path, ['init', str(repo_dir)])
        _assert_success('init', init_result, ['initialized empty hubvault repository'])

        status_result = _run(cli_path, ['-C', str(repo_dir), 'status'])
        _assert_success('status', status_result, ['on branch main', 'repository clean'])

        branch_current_result = _run(cli_path, ['-C', str(repo_dir), 'branch', '--show-current'])
        _assert_success('branch --show-current', branch_current_result, ['main'])

        verify_result = _run(cli_path, ['-C', str(repo_dir), 'verify'])
        _assert_success('verify', verify_result, ['quick verification ok'])
        print('[OK] init/status/branch/verify')

        commit_result = _run(
            cli_path,
            [
                '-C',
                str(repo_dir),
                'commit',
                '-m',
                'seed',
                '--add',
                'artifacts/file.bin={path}'.format(path=str(payload_file)),
            ],
        )
        _assert_success('commit', commit_result, ['main', 'seed'])

        tree_result = _run(cli_path, ['-C', str(repo_dir), 'ls-tree'])
        _assert_success('ls-tree', tree_result, ['tree', 'artifacts'])

        download_result = _run(cli_path, ['-C', str(repo_dir), 'download', 'artifacts/file.bin'])
        _assert_success('download', download_result, ['artifacts', 'file.bin'])
        download_path = Path(download_result.stdout.strip() or download_result.stderr.strip())
        if not download_path.is_file():
            raise AssertionError(f'download output is not a file path: {_combined_output(download_result)}')
        if download_path.read_bytes() != b'hello':
            raise AssertionError('downloaded file content mismatch')

        log_result = _run(cli_path, ['-C', str(repo_dir), 'log', '--oneline', '-n', '1'])
        _assert_success('log', log_result, ['seed'])
        print('[OK] commit/ls-tree/download/log')


if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        print(f'[FAIL] {err}', file=sys.stderr)
        raise SystemExit(1)
