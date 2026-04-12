#!/usr/bin/env python
"""Smoke-test the built hubvault CLI executable."""

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence
from urllib.request import Request, urlopen


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


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_get(url: str, headers: Optional[dict] = None) -> tuple:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=5) as response:
        return int(response.status), response.read()


def _assert_frontend_server(cli_path: str, repo_dir: Path) -> None:
    token = "smoke-rw-token"
    port = _find_free_port()
    process = subprocess.Popen(
        [
            cli_path,
            "serve",
            str(repo_dir),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--mode",
            "frontend",
            "--token-rw",
            token,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.time() + 30.0
        last_error = ""
        while time.time() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"serve exited early with code {process.returncode}: {output}")
            try:
                root_status, root_body = _http_get(base_url + "/")
                if root_status == 200 and b"hubvault" in root_body.lower():
                    break
            except Exception as err:  # pragma: no cover - timing dependent
                last_error = str(err)
            time.sleep(0.5)
        else:  # pragma: no cover - timing dependent
            raise AssertionError(f"serve did not become ready in time: {last_error}")

        service_status, service_body = _http_get(
            base_url + "/api/v1/meta/service",
            headers={"Authorization": f"Bearer {token}"},
        )
        if service_status != 200:
            raise AssertionError(f"service endpoint returned unexpected status: {service_status}")

        payload = json.loads(service_body.decode("utf-8"))
        if payload.get("mode") != "frontend":
            raise AssertionError(f"service payload mode mismatch: {payload!r}")
        if not payload.get("ui_enabled"):
            raise AssertionError(f"service payload did not report ui_enabled: {payload!r}")

        print("[OK] serve frontend")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - best effort cleanup
                process.kill()
                process.wait(timeout=10)


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

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        repo_dir = tmp_path / 'repo'
        payload_file = tmp_path / 'payload.bin'
        payload_file.write_bytes(b'hello')

        init_result = _run(cli_path, ['init', str(repo_dir)])
        _assert_success('init', init_result, ['initialized empty hubvault repository'])
        print('[OK] init')

        status_result = _run(cli_path, ['-C', str(repo_dir), 'status'])
        _assert_success('status', status_result, ['on branch main', 'repository clean'])
        print('[OK] status')

        branch_current_result = _run(cli_path, ['-C', str(repo_dir), 'branch', '--show-current'])
        _assert_success('branch --show-current', branch_current_result, ['main'])
        if branch_current_result.stdout.strip() != 'main':
            raise AssertionError(f"branch --show-current returned unexpected output: {branch_current_result.stdout!r}")
        print('[OK] branch --show-current')

        verify_result = _run(cli_path, ['-C', str(repo_dir), 'verify'])
        _assert_success('verify', verify_result, ['quick verification ok'])
        print('[OK] verify')

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
        print('[OK] commit')

        create_branch_result = _run(cli_path, ['-C', str(repo_dir), 'branch', 'feature'])
        _assert_success('branch create', create_branch_result, [])

        list_branch_result = _run(cli_path, ['-C', str(repo_dir), 'branch'])
        _assert_success('branch list', list_branch_result, ['feature'])
        print('[OK] branch create/list')

        create_tag_result = _run(cli_path, ['-C', str(repo_dir), 'tag', 'smoke-tag'])
        _assert_success('tag create', create_tag_result, [])

        list_tag_result = _run(cli_path, ['-C', str(repo_dir), 'tag', '-l'])
        _assert_success('tag list', list_tag_result, ['smoke-tag'])
        print('[OK] tag create/list')

        tree_result = _run(cli_path, ['-C', str(repo_dir), 'ls-tree'])
        _assert_success('ls-tree', tree_result, ['tree', 'artifacts'])
        if '\tartifacts' not in tree_result.stdout:
            raise AssertionError(f"ls-tree output missing artifacts entry: {tree_result.stdout!r}")
        print('[OK] ls-tree')

        download_result = _run(cli_path, ['-C', str(repo_dir), 'download', 'artifacts/file.bin'])
        _assert_success('download', download_result, ['artifacts', 'file.bin'])
        download_path = Path(download_result.stdout.strip() or download_result.stderr.strip())
        if not download_path.is_file():
            raise AssertionError(f'download output is not a file path: {_combined_output(download_result)}')
        if download_path.read_bytes() != b'hello':
            raise AssertionError('downloaded file content mismatch')
        print('[OK] download')

        log_result = _run(cli_path, ['-C', str(repo_dir), 'log', '--oneline', '-n', '1'])
        _assert_success('log', log_result, ['seed'])
        log_lines = [line for line in log_result.stdout.splitlines() if line.strip()]
        if len(log_lines) != 1:
            raise AssertionError(f'log --oneline returned unexpected lines: {log_result.stdout!r}')
        print('[OK] log')

        _assert_frontend_server(cli_path, repo_dir)


if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        print(f'[FAIL] {err}', file=sys.stderr)
        raise SystemExit(1)
